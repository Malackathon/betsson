"""Betsson lobby page automation — login, navigation and balance reading.

Handles:
- Login in a non-recording context (credentials never appear in video/trace).
- Saving / restoring auth_state_{agent_id}.json for the recording context.
- Navigating to casino lobby, searching Pragmatic Play game, opening in Real Play.
- Stabilized reading of Betsson balance from DOM header (polling - R10).
- Currency detection from the header.
"""
from __future__ import annotations

import logging
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol, runtime_checkable

from playwright.sync_api import Locator, Page

from src.browser.balance_probe import PROBE_ATTRIBUTE, find_balance_locator
from src.browser.selectors import (
    GAME_WRAPPER_DISMISS_SELECTORS,
    OVERLAY_DISMISS_SELECTORS,
    MarketSelectors,
    get_market_selectors,
)

logger = logging.getLogger(__name__)

# Temporary Protocol for money parsing (replaced at integration with core)
# TODO(integration): Replace with ``from src.core.money import parse_money``


@runtime_checkable
class MoneyParser(Protocol):
    """Minimal contract expected from core.money.parse_money."""

    def __call__(self, raw: str, currency_hint: str | None = None) -> Decimal: ...


def _default_parse_money(raw: str, currency_hint: str | None = None) -> Decimal:
    """Fallback money parser until core branch is integrated. Always Decimal."""
    cleaned = raw.strip()
    for symbol in ("€", "S/", "PEN", "EUR", "\u00a0", "\u202f"):
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.strip()
    if not cleaned:
        raise ValueError(f"Cannot parse money from empty string (raw={raw!r})")

    # Detect ES format: 1.234,56 vs EN format: 1,234.56
    if re.search(r"\d\.\d{3},\d{1,2}$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        cleaned = cleaned.replace(",", ".") if len(parts) == 2 and len(parts[1]) <= 2 else cleaned.replace(",", "")

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse money: raw={raw!r}, cleaned={cleaned!r}") from exc


_BALANCE_POLL_INTERVAL_S = 0.5
_BALANCE_POLL_TIMEOUT_S = 15.0
_BALANCE_STABILITY_READS = 3
_PAGE_LOAD_TIMEOUT_MS = 30_000
_NAV_TIMEOUT_MS = 15_000
_OVERLAY_APPEAR_TIMEOUT_MS = 6_000
_PROBED_RECHECK_MS = 1_500


class LobbyPage:
    """Playwright-based interaction with the Betsson lobby and header."""

    def __init__(
        self,
        page: Page,
        market: str = "com",
        agent_id: str = "agent_com_s1",
        auth_state_dir: Path | None = None,
        money_parser: MoneyParser | None = None,
    ) -> None:
        self._page = page
        self._agent_id = agent_id
        self._auth_state_dir = auth_state_dir or Path("auth_state")
        self._mkt: MarketSelectors = get_market_selectors(market)
        self._sel = self._mkt.selectors
        self._parse_money = money_parser or _default_parse_money
        self._logged_in = False
        self._balance_probed = False

    def login(self, username: str, password: str) -> None:
        """Log in to Betsson using a non-recording context to protect credentials (R1)."""
        logger.info("[%s] Navigating to %s for login", self._agent_id, self._mkt.url)
        self._page.goto(self._mkt.url, timeout=_PAGE_LOAD_TIMEOUT_MS)
        self._dismiss_overlays()

        # Open login form
        login_btn = self._page.locator(self._sel.login_button).first
        login_btn.wait_for(state="visible", timeout=_NAV_TIMEOUT_MS)
        try:
            login_btn.click(timeout=5000)
        except Exception:
            login_btn.click(force=True)
        logger.info("[%s] Login form opened", self._agent_id)

        # Fill credentials
        usr_input = self._page.locator(self._sel.username_input).first
        usr_input.wait_for(state="visible", timeout=_NAV_TIMEOUT_MS)
        usr_input.fill(username)

        pwd_input = self._page.locator(self._sel.password_input).first
        pwd_input.wait_for(state="visible", timeout=_NAV_TIMEOUT_MS)
        pwd_input.fill(password)

        # Submit login via Enter key press (universal standard) + fallback click
        pwd_input.press("Enter")
        try:
            submit_btn = self._page.locator(self._sel.submit_login).last
            if submit_btn.count() > 0:
                submit_btn.click(force=True, timeout=3000)
        except Exception:
            pass

        # Wait for login completion indicated by balance display
        self._balance_locator(_PAGE_LOAD_TIMEOUT_MS)
        self._logged_in = True
        logger.info("[%s] Login successful", self._agent_id)
        self._save_auth_state()

    def _save_auth_state(self) -> None:
        """Persist storage state for reuse in video recording context."""
        self._auth_state_dir.mkdir(parents=True, exist_ok=True)
        state_path = self._auth_state_dir / f"auth_state_{self._agent_id}.json"
        self._page.context.storage_state(path=str(state_path))
        logger.info("[%s] Auth state saved to %s", self._agent_id, state_path)

    def get_auth_state_path(self) -> Path:
        """Return the path to saved auth state."""
        return self._auth_state_dir / f"auth_state_{self._agent_id}.json"

    def assert_logged_in(self, timeout_ms: int = _PAGE_LOAD_TIMEOUT_MS) -> None:
        """Fail fast, with the fix, when a reused saved session turned out expired or rejected."""
        try:
            self._balance_locator(timeout_ms)
        except Exception as exc:
            raise RuntimeError(
                f"[{self._agent_id}] Logged-in header (balance) not found with the saved session: it may be "
                f"expired/rejected, or the 'balance_display' selector in config/markets.json does not match this "
                f"site. Re-save the session with: python scripts/save_session.py {self._agent_id}. "
                f"Detail: {str(exc)[:600]}"
            ) from None
        self._logged_in = True

    def navigate_to_casino(self) -> None:
        """Navigate to casino lobby page."""
        logger.info("[%s] Navigating to casino: %s", self._agent_id, self._mkt.casino_url)
        self._page.goto(self._mkt.casino_url, timeout=_PAGE_LOAD_TIMEOUT_MS)
        self._dismiss_overlays()
        logger.info("[%s] Casino lobby loaded", self._agent_id)

    def search_and_open_game(self, game_name: str | None = None) -> str:
        """Search for and open a Pragmatic Play game in Real Play from candidates."""
        candidates = [game_name] if game_name else self._mkt.game_candidates
        last_error: Exception | None = None

        for candidate in candidates:
            try:
                self._try_open_game(candidate)
                logger.info("[%s] Game '%s' opened successfully", self._agent_id, candidate)
                return candidate
            except Exception as exc:
                logger.warning("[%s] Failed to open game '%s': %s", self._agent_id, candidate, exc)
                last_error = exc
                continue

        raise RuntimeError(
            f"[{self._agent_id}] Could not open any game from candidates {candidates}. "
            f"Last error: {last_error}"
        )

    def _try_open_game(self, game_name: str) -> None:
        """Search for and open a single game candidate."""
        search_input = self._page.locator(self._sel.search_input).first
        if search_input.count() > 0 and search_input.is_visible():
            search_input.fill("")
            search_input.fill(game_name)
            self._page.wait_for_timeout(1500)

        game_card = self._page.locator(self._sel.game_card(game_name)).first
        game_card.wait_for(state="visible", timeout=_NAV_TIMEOUT_MS)
        game_card.click()

        # If a modal opens with a Play button, click it
        play_btn = self._page.locator(self._sel.play_real_button).first
        if play_btn.count() > 0 and play_btn.is_visible():
            play_btn.click()

        # Wait for game iframe to be attached
        self._page.locator(self._sel.game_iframe).first.wait_for(
            state="attached", timeout=_PAGE_LOAD_TIMEOUT_MS
        )
        logger.info("[%s] Game iframe detected for '%s'", self._agent_id, game_name)

    def _balance_locator(self, timeout_ms: int = _NAV_TIMEOUT_MS) -> Locator:
        """Configured balance element, or the header probe when the selector does not match."""
        wait = _PROBED_RECHECK_MS if self._balance_probed else timeout_ms
        locator = find_balance_locator(self._page, self._sel.balance_display, wait)
        self._balance_probed = locator.get_attribute(PROBE_ATTRIBUTE) == "1"
        return locator

    def read_balance_raw(self) -> str:
        """Read raw balance text from the Betsson header."""
        bal_el = self._balance_locator()
        raw = bal_el.inner_text()
        logger.debug("[%s] Raw balance read: %r", self._agent_id, raw)
        return raw.strip()

    def read_balance_stable(self) -> Decimal:
        """Read Betsson balance, polling until value stabilizes (R10)."""
        logger.info("[%s] Polling balance until stable...", self._agent_id)
        start = time.monotonic()
        stable_count = 0
        last_value: Decimal | None = None

        while (time.monotonic() - start) < _BALANCE_POLL_TIMEOUT_S:
            raw = self.read_balance_raw()
            try:
                current = self._parse_money(raw, self._mkt.currency)
            except (ValueError, InvalidOperation) as exc:
                logger.warning("[%s] Balance parse retry (%s)", self._agent_id, exc)
                stable_count = 0
                last_value = None
                time.sleep(_BALANCE_POLL_INTERVAL_S)
                continue

            if current == last_value:
                stable_count += 1
            else:
                stable_count = 1
                last_value = current

            if stable_count >= _BALANCE_STABILITY_READS:
                logger.info("[%s] Balance stable at %s (%d reads)", self._agent_id, last_value, stable_count)
                return last_value

            time.sleep(_BALANCE_POLL_INTERVAL_S)

        raise TimeoutError(
            f"[{self._agent_id}] Balance did not stabilize within {_BALANCE_POLL_TIMEOUT_S}s. "
            f"Last value: {last_value}"
        )

    def read_currency_from_header(self) -> str:
        """Read currency symbol/code displayed in the Betsson header."""
        cur_el = self._page.locator(self._sel.currency_display)
        if cur_el.count() > 0 and cur_el.first.is_visible():
            text = cur_el.first.inner_text().strip()
            if text:
                return text

        raw_balance = self.read_balance_raw()
        for symbol in ("€", "S/", "PEN", "EUR"):
            if symbol in raw_balance:
                return symbol

        return self._mkt.currency_symbol

    def _dismiss_overlays(self) -> None:
        """Dismiss overlay popups (cookies, promos, banners).

        The cookie banner is rendered after hydration, so wait for it to show up instead of
        sleeping a fixed second: otherwise it appears later and intercepts the login click.
        """
        self._page.wait_for_timeout(1000)
        try:
            self._page.locator(", ".join(OVERLAY_DISMISS_SELECTORS[:5])).first.wait_for(
                state="visible", timeout=_OVERLAY_APPEAR_TIMEOUT_MS
            )
        except Exception:
            logger.debug("[%s] No cookie/overlay appeared within %d ms", self._agent_id, _OVERLAY_APPEAR_TIMEOUT_MS)
        for selector in OVERLAY_DISMISS_SELECTORS:
            try:
                loc = self._page.locator(selector)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=3000)
                    logger.debug("[%s] Dismissed overlay: %s", self._agent_id, selector)
                    self._page.wait_for_timeout(500)
            except Exception:
                continue

    def dismiss_game_wrappers(self) -> None:
        """Dismiss game wrapper popups (responsible gaming, intro overlays)."""
        self._page.wait_for_timeout(1500)
        for selector in GAME_WRAPPER_DISMISS_SELECTORS:
            try:
                loc = self._page.locator(selector)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=3000)
                    logger.debug("[%s] Dismissed game wrapper: %s", self._agent_id, selector)
                    self._page.wait_for_timeout(500)
            except Exception:
                continue

    @property
    def page(self) -> Page:
        """The underlying Playwright page."""
        return self._page

    @property
    def market_config(self) -> MarketSelectors:
        """The loaded market configuration."""
        return self._mkt
