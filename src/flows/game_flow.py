"""High-level game flow orchestration for a single sub-agent.

Ties together LobbyPage and GameCanvas:
1. Context A (no video): Login -> save auth state (R1).
2. Context B (with video): Load auth state -> open game -> perform scenario.
3. Stabilized balance readings before/after.
4. Insufficient-funds warning detection at three locations (R11).
Money always in Decimal.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from src.browser.game_canvas import (
    CHROMIUM_GPU_ARGS,
    DEFAULT_VIEWPORT,
    GameCanvas,
    RelativeCoords,
)
from src.browser.lobby_page import LobbyPage
from src.browser.selectors import get_market_selectors
from src.browser.visual_debug import CURSOR_SCRIPT, read_visual_settings
from src.browser.iframe_finder import page_snapshot
from src.browser.session_watch import SessionWatch
from src.browser.session_state import apply_session_storage, find_reusable_session
from src.flows.spin_runner import SpinRun, run_spin_with_bonus_retry
from src.network.models import RoundResult, SpinAttempt, SpinAttemptStatus
from src.network.monitor import NetworkMonitor

logger = logging.getLogger(__name__)


class SpinStatus(Enum):
    """Outcome of attempting a spin."""
    COMPLETED = "completed"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    BONUS_TRIGGERED = "bonus_triggered"
    ERROR = "error"


class InsufficientFundsLocation(Enum):
    """Where the insufficient-funds warning was detected (R11)."""
    AT_GAME_OPEN = "at_game_open"
    IN_WRAPPER_OVERLAY = "in_wrapper_overlay"
    AFTER_SPIN_CLICK = "after_spin_click"
    NOT_DETECTED = "not_detected"


@dataclass
class SpinOutcome:
    """Result of a spin attempt, consumed by the e2e branch."""
    status: SpinStatus
    balance_before: Decimal = Decimal("0")
    balance_after: Decimal = Decimal("0")
    bet_amount: Decimal = Decimal("0")
    win_amount: Decimal = Decimal("0")
    hud_credit_before: Decimal = Decimal("0")
    hud_credit_after: Decimal = Decimal("0")
    currency_observed: str = ""
    insufficient_msg: str = ""
    insufficient_location: InsufficientFundsLocation = InsufficientFundsLocation.NOT_DETECTED
    screenshots: list[Path] = field(default_factory=list)
    video_path: Path | None = None
    # Network ground truth (zero-cost, deterministic). ``hud_credit_*`` are the in-game
    # balances as reported by the game server, not read from pixels.
    spin_attempt: SpinAttempt | None = None
    network_round: RoundResult | None = None
    final_screenshot: Path | None = None
    bonus_retries: int = 0
    network_evidence: Path | None = None


@dataclass
class FlowCallbacks:
    """Optional callbacks for e2e hooks."""
    on_login_complete: Callable[[], None] | None = None
    on_game_opened: Callable[[str], None] | None = None
    on_balance_read: Callable[[Decimal], None] | None = None
    on_spin_start: Callable[[], None] | None = None
    on_spin_end: Callable[[SpinOutcome], None] | None = None
    on_insufficient_funds: Callable[[str, InsufficientFundsLocation], None] | None = None


_RETRY_SPIN_ON_BONUS_MAX = 3
_S2_ROUND_TIMEOUT_S = 6.0  # a rejected spin never settles; do not wait the full round timeout
_NETWORK_EVIDENCE_REL = Path("network") / "game_transactions.json"
_VIDEO_DIR_NAME = "video"
_AUTH_STATE_DIR_NAME = "auth_state"


class GameFlow:
    """Orchestrates the full flow of a single sub-agent's test scenario."""

    def __init__(
        self,
        playwright: Playwright,
        market: str = "com",
        agent_id: str = "agent_com_s1",
        username: str = "",
        password: str = "",
        artifacts_dir: Path | None = None,
        headless: bool = True,
        callbacks: FlowCallbacks | None = None,
        monitor: NetworkMonitor | None = None,
    ) -> None:
        self._monitor = monitor or NetworkMonitor()
        self._watch = SessionWatch()
        self._pw = playwright
        self._market = market
        self._agent_id = agent_id
        self._username = username
        self._password = password
        self._artifacts_dir = artifacts_dir or Path(f"artifacts/{agent_id}")
        self._headless = headless
        self._callbacks = callbacks or FlowCallbacks()
        self._mkt_config = get_market_selectors(market)

        self._browser: Browser | None = None
        self._ctx_login: BrowserContext | None = None
        self._ctx_game: BrowserContext | None = None
        self._lobby: LobbyPage | None = None
        self._canvas: GameCanvas | None = None
        self._game_name: str = ""
        self._auth_state_path: Path | None = None
        self._reused_session = False
        self._visual = read_visual_settings(os.environ, headless)

    @property
    def monitor(self) -> NetworkMonitor:
        """Network monitor attached to the recorded game page."""
        return self._monitor

    def prepare(self) -> tuple[LobbyPage, GameCanvas]:
        """Phase 1: Login without recording + open game with video recording."""
        self._launch_browser()
        self._login_phase()
        self._game_phase()
        assert self._lobby is not None
        assert self._canvas is not None
        return self._lobby, self._canvas

    def execute_scenario_1(
        self,
        spin_coords_provider: Callable[[Path], RelativeCoords] | None = None,
    ) -> SpinOutcome:
        """Execute Scenario 1: Real Play spin + balance reconciliation.

        The spin is judged by the game server's own response (network monitor); the final
        screenshot is taken the moment the round settles, for the single visual verification.
        """
        assert self._lobby is not None and self._canvas is not None
        outcome = SpinOutcome(status=SpinStatus.ERROR)

        outcome.balance_before = self._lobby.read_balance_stable()
        if self._callbacks.on_balance_read:
            self._callbacks.on_balance_read(outcome.balance_before)

        pre_screenshot = self._canvas.take_game_screenshot("s1_pre_spin")
        outcome.screenshots.append(pre_screenshot)
        spin_coords = self._get_spin_coords(pre_screenshot, spin_coords_provider)

        if self._callbacks.on_spin_start:
            self._callbacks.on_spin_start()
        run = run_spin_with_bonus_retry(
            self._canvas, self._monitor, spin_coords, max_bonus_retries=_RETRY_SPIN_ON_BONUS_MAX
        )
        self._apply_spin_run(outcome, run)
        outcome.status = self._status_for_scenario_1(run)

        outcome.balance_after = self._lobby.read_balance_stable()
        outcome.currency_observed = self._lobby.read_currency_from_header()
        outcome.network_evidence = self._save_network_evidence()
        if self._callbacks.on_spin_end:
            self._callbacks.on_spin_end(outcome)
        outcome.video_path = self._get_video_path()
        return outcome

    def execute_scenario_2(
        self,
        spin_coords_provider: Callable[[Path], RelativeCoords] | None = None,
    ) -> SpinOutcome:
        """Execute Scenario 2: Insufficient funds check across 3 locations (R11)."""
        assert self._lobby is not None and self._canvas is not None
        outcome = SpinOutcome(status=SpinStatus.INSUFFICIENT_FUNDS)

        self._monitor.mark()  # drain pending responses so last_balance is current
        net_before = self._monitor.last_balance  # in-game balance per the server, BEFORE the attempt
        outcome.balance_before = self._lobby.read_balance_stable()
        if self._callbacks.on_balance_read:
            self._callbacks.on_balance_read(outcome.balance_before)

        pre_screenshot = self._canvas.take_game_screenshot("s2_pre_action")
        outcome.screenshots.append(pre_screenshot)

        # Location 1: at game open
        msg, location = self._check_insufficient_funds_at_open()
        if msg:
            outcome.insufficient_msg, outcome.insufficient_location = msg, location
            if self._callbacks.on_insufficient_funds:
                self._callbacks.on_insufficient_funds(msg, location)
        else:
            # Trigger by clicking spin; the monitor tells us whether the server accepted it.
            spin_coords = self._get_spin_coords(pre_screenshot, spin_coords_provider)
            run = run_spin_with_bonus_retry(
                self._canvas,
                self._monitor,
                spin_coords,
                round_timeout_s=_S2_ROUND_TIMEOUT_S,
                max_bonus_retries=1,
            )
            self._apply_spin_run(outcome, run)
            if run.attempt.status is SpinAttemptStatus.SETTLED:
                outcome.status = SpinStatus.COMPLETED  # a PAID spin went through: unexpected here

            # Location 2 & 3: wrapper or after click
            msg, location = self._check_insufficient_funds_wrapper()
            if not msg:
                msg, location = self._check_insufficient_funds_after_click()
            outcome.insufficient_msg, outcome.insufficient_location = msg, location

            if msg and self._callbacks.on_insufficient_funds:
                self._callbacks.on_insufficient_funds(msg, location)

        outcome.balance_after = self._lobby.read_balance_stable()
        outcome.currency_observed = self._lobby.read_currency_from_header()
        final_screenshot = self._canvas.take_game_screenshot("s2_final")
        outcome.screenshots.append(final_screenshot)
        outcome.final_screenshot = outcome.final_screenshot or final_screenshot
        self._monitor.mark()  # drain pending responses so last_balance is current
        net_after = self._monitor.last_balance
        if net_before is not None and net_after is not None:
            outcome.hud_credit_before, outcome.hud_credit_after = net_before, net_after
        outcome.bet_amount = outcome.bet_amount or self._monitor.last_bet or Decimal("0")
        outcome.network_evidence = self._save_network_evidence()

        if self._callbacks.on_spin_end:
            self._callbacks.on_spin_end(outcome)
        outcome.video_path = self._get_video_path()
        return outcome

    def _apply_spin_run(self, outcome: SpinOutcome, run: SpinRun) -> None:
        """Copy the server-side truth of a spin run into the outcome."""
        outcome.spin_attempt = run.attempt
        outcome.bonus_retries = run.bonus_retries
        if run.final_screenshot is not None:
            outcome.final_screenshot = run.final_screenshot
            outcome.screenshots.append(run.final_screenshot)
        rnd = run.attempt.round
        outcome.network_round = rnd
        if rnd is None:
            return
        outcome.bet_amount = rnd.bet or Decimal("0")
        outcome.win_amount = rnd.total_win or Decimal("0")
        outcome.hud_credit_before = rnd.balance_before or Decimal("0")
        outcome.hud_credit_after = rnd.balance_after or Decimal("0")

    @staticmethod
    def _status_for_scenario_1(run: SpinRun) -> SpinStatus:
        attempt = run.attempt
        if attempt.status is SpinAttemptStatus.REJECTED:
            return SpinStatus.INSUFFICIENT_FUNDS
        if attempt.status is not SpinAttemptStatus.SETTLED or attempt.round is None:
            return SpinStatus.ERROR
        return SpinStatus.BONUS_TRIGGERED if attempt.round.bonus_triggered else SpinStatus.COMPLETED

    def _save_network_evidence(self) -> Path | None:
        """Persist the sanitized game transactions next to the other evidence."""
        try:
            return self._monitor.save_evidence(self._artifacts_dir / _NETWORK_EVIDENCE_REL)
        except Exception as exc:
            logger.warning("[%s] Could not save network evidence: %s", self._agent_id, exc)
            return None

    def _launch_browser(self) -> None:
        """Launch browser engine (Firefox for antibot evasion, or Chromium)."""
        browser_type = os.getenv("PLAYWRIGHT_BROWSER") or os.getenv("BROWSER_TYPE") or "chromium"
        b_type = browser_type.strip().lower()

        slow_mo = self._visual.slow_mo_ms
        if b_type == "firefox":
            self._browser = self._pw.firefox.launch(headless=self._headless, slow_mo=slow_mo)
        elif b_type == "webkit":
            self._browser = self._pw.webkit.launch(headless=self._headless, slow_mo=slow_mo)
        else:
            launch_args = list(CHROMIUM_GPU_ARGS)
            if self._headless:
                launch_args.append("--headless=new")
            self._browser = self._pw.chromium.launch(headless=self._headless, args=launch_args, slow_mo=slow_mo)

        logger.info("[%s] Browser launched (%s, headless=%s)", self._agent_id, b_type, self._headless)

    def _login_phase(self) -> None:
        """Context A: login without video recording to protect secrets (R1)."""
        assert self._browser is not None
        auth_dir = self._artifacts_dir.parent / _AUTH_STATE_DIR_NAME
        auth_dir.mkdir(parents=True, exist_ok=True)

        reusable = find_reusable_session(self._artifacts_dir, self._agent_id)
        if reusable is not None:
            # A human logged in with scripts/save_session.py: skip the automated login, which
            # the site's antifraud rejects. The session is verified once the game page loads.
            self._auth_state_path = reusable
            self._reused_session = True
            logger.info("[%s] Reusing saved session %s (automated login skipped)", self._agent_id, reusable.name)
            return

        self._ctx_login = self._browser.new_context(
            viewport=DEFAULT_VIEWPORT,
            locale=self._mkt_config.locale,
        )
        if self._visual.show_cursor:
            self._ctx_login.add_init_script(CURSOR_SCRIPT)
        page = self._ctx_login.new_page()
        lobby = LobbyPage(page=page, market=self._market, agent_id=self._agent_id, auth_state_dir=auth_dir)
        lobby.login(self._username, self._password)

        if self._callbacks.on_login_complete:
            self._callbacks.on_login_complete()

        self._auth_state_path = lobby.get_auth_state_path()
        self._ctx_login.close()
        self._ctx_login = None
        logger.info("[%s] Login context closed, auth state saved", self._agent_id)

    def _game_phase(self) -> None:
        """Context B: load auth state and record video for game session."""
        assert self._browser is not None
        video_dir = self._artifacts_dir / _VIDEO_DIR_NAME
        video_dir.mkdir(parents=True, exist_ok=True)

        self._ctx_game = self._browser.new_context(
            viewport=DEFAULT_VIEWPORT,
            locale=self._mkt_config.locale,
            storage_state=str(self._auth_state_path),
            record_video_dir=str(video_dir),
            record_video_size=DEFAULT_VIEWPORT,
        )
        if self._visual.show_cursor:
            self._ctx_game.add_init_script(CURSOR_SCRIPT)  # the recorded video shows where the bot clicks
        if self._reused_session:
            apply_session_storage(self._ctx_game, self._auth_state_path)
        page = self._ctx_game.new_page()
        # Attach BEFORE navigating so the game's init response (starting balance) is captured.
        self._monitor.attach(page)
        auth_dir = self._artifacts_dir.parent / _AUTH_STATE_DIR_NAME
        self._lobby = LobbyPage(page=page, market=self._market, agent_id=self._agent_id, auth_state_dir=auth_dir)

        self._watch.attach(page)
        try:
            self._open_game(page)
        except Exception as exc:
            # Explain a lost session: recent navigations/HTTP errors (host/path only, no secrets).
            self._watch.checkpoint("failure", logged_out=self._lobby.is_logged_out())
            snapshot = page_snapshot(page)
            shot = self._save_failure_screenshot(page)
            detail = f"{self._watch.summary()} | On screen: {snapshot} | Screenshot: {shot}"
            logger.error("[%s] Game phase failed. %s", self._agent_id, detail)
            raise RuntimeError(f"{exc} | {detail}") from None

    def _save_failure_screenshot(self, page: Page) -> str:
        """Viewport screenshot of where the game phase failed (local evidence, gitignored)."""
        try:
            evidence = self._artifacts_dir / "evidence"
            evidence.mkdir(parents=True, exist_ok=True)
            path = evidence / "game_phase_failure.png"
            page.screenshot(path=str(path))
            return str(path)
        except Exception:
            return "<screenshot unavailable>"

    def _open_game(self, page: Page) -> None:
        assert self._lobby is not None
        self._lobby.navigate_to_casino()
        if self._reused_session:
            self._lobby.assert_logged_in()
        self._watch.checkpoint("casino loaded", self._lobby.is_logged_out())
        self._game_name = self._lobby.search_and_open_game()
        self._watch.checkpoint(f"after opening '{self._game_name}'", self._lobby.is_logged_out())
        if self._callbacks.on_game_opened:
            self._callbacks.on_game_opened(self._game_name)

        self._canvas = GameCanvas(
            page=page,
            market=self._market,
            agent_id=self._agent_id,
            artifacts_dir=self._artifacts_dir,
        )
        self._canvas.locate_iframe()
        self._canvas.dismiss_intros()
        self._lobby.dismiss_game_wrappers()
        self._watch.checkpoint("game frame ready", self._lobby.is_logged_out())
        logger.info("[%s] Game '%s' ready", self._agent_id, self._game_name)

    def _get_spin_coords(
        self,
        screenshot_path: Path,
        provider: Callable[[Path], RelativeCoords] | None,
    ) -> RelativeCoords:
        """Resolve spin button coordinates from vision provider or fallback."""
        if provider is not None:
            try:
                coords = provider(screenshot_path)
                logger.info("[%s] Spin coords from provider: (%.3f, %.3f)", self._agent_id, coords["x"], coords["y"])
                return coords
            except Exception as exc:
                logger.warning("[%s] Spin provider failed (%s), using fallback", self._agent_id, exc)

        fallback = RelativeCoords(x=0.5, y=0.92)
        logger.info("[%s] Using fallback Spin coords: (0.5, 0.92)", self._agent_id)
        return fallback

    def _check_insufficient_funds_at_open(self) -> tuple[str, InsufficientFundsLocation]:
        return self._scan_for_insufficient_message(InsufficientFundsLocation.AT_GAME_OPEN)

    def _check_insufficient_funds_wrapper(self) -> tuple[str, InsufficientFundsLocation]:
        return self._scan_for_insufficient_message(InsufficientFundsLocation.IN_WRAPPER_OVERLAY)

    def _check_insufficient_funds_after_click(self) -> tuple[str, InsufficientFundsLocation]:
        return self._scan_for_insufficient_message(InsufficientFundsLocation.AFTER_SPIN_CLICK)

    def _scan_for_insufficient_message(
        self,
        location: InsufficientFundsLocation,
    ) -> tuple[str, InsufficientFundsLocation]:
        """Scan DOM wrapper containers for insufficient-funds keywords."""
        assert self._canvas is not None
        keywords = self._mkt_config.keywords_insufficient
        try:
            page = self._canvas.page
            modal_selectors = [
                ".modal-body",
                ".alert-message",
                "[role='alert']",
                "[role='dialog']",
                ".notification-message",
                ".error-message",
                ".game-message",
                ".insufficient-funds",
            ]
            for sel in modal_selectors:
                loc = page.locator(sel)
                count = loc.count()
                for i in range(min(count, 5)):
                    try:
                        text = loc.nth(i).inner_text(timeout=1000)
                        if any(kw.lower() in text.lower() for kw in keywords):
                            logger.info("[%s] Insufficient funds at %s: %r", self._agent_id, location.value, text)
                            return text.strip(), location
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug("[%s] Error scanning insufficient msg: %s", self._agent_id, exc)

        return "", InsufficientFundsLocation.NOT_DETECTED

    def _get_video_path(self) -> Path | None:
        """Retrieve video path from recording context."""
        if self._ctx_game is None:
            return None
        try:
            pages = self._ctx_game.pages
            if pages and pages[0].video:
                path = pages[0].video.path()
                return Path(path) if path else None
        except Exception:
            pass
        return None

    def close(self) -> None:
        """Close browser contexts and browser (optionally after KEEP_OPEN_S so a human can look)."""
        if self._visual.keep_open_s and self._browser is not None:
            logger.info("[%s] Keeping the browser open for %ds (KEEP_OPEN_S)", self._agent_id, self._visual.keep_open_s)
            time.sleep(self._visual.keep_open_s)
        self._monitor.detach()
        self._watch.detach()
        for ctx in (self._ctx_game, self._ctx_login):
            if ctx is not None:
                try:
                    ctx.close()
                except Exception:
                    pass
        self._ctx_game = None
        self._ctx_login = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        logger.info("[%s] GameFlow closed", self._agent_id)

    def __enter__(self) -> GameFlow:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
