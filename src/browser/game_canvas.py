"""Game canvas interaction — iframe location, coordinate mapping, and screenshots.

Handles:
- Locating the game iframe and computing its bounding rectangle.
- Converting relative coordinates (from vision/Gemini) to absolute page coords (R9).
- Clicking at coordinates (e.g. Spin button located by vision).
- Capturing screenshots of the game area for vision analysis.
- Dismissing intro/overlay popups inside the game wrapper.

The game runs inside a cross-origin iframe with NO DOM access permitted.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from playwright.sync_api import ElementHandle, FrameLocator, Page

from src.browser.iframe_finder import find_game_iframe
from src.browser.selectors import (
    GAME_WRAPPER_DISMISS_SELECTORS,
    MarketSelectors,
    get_market_selectors,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoundingRect:
    """Bounding rectangle of the game iframe on the page."""

    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


class RelativeCoords(TypedDict):
    """Coordinates relative to the game screenshot (0.0–1.0 normalized)."""

    x: float
    y: float


class AbsoluteCoords(TypedDict):
    """Absolute page coordinates for Playwright click actions."""

    x: float
    y: float


CHROMIUM_GPU_ARGS: list[str] = [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--disable-gpu-sandbox",
    "--disable-software-rasterizer",
]

DEFAULT_VIEWPORT = {"width": 1280, "height": 720}

_IFRAME_WAIT_TIMEOUT_MS = 30_000
_SCREENSHOT_SETTLING_MS = 500
_CLICK_SETTLING_MS = 200


class GameCanvas:
    """Interaction layer for the game running inside a cross-origin iframe."""

    def __init__(
        self,
        page: Page,
        market: str = "com",
        agent_id: str = "agent_com_s1",
        artifacts_dir: Path | None = None,
    ) -> None:
        self._page = page
        self._agent_id = agent_id
        self._artifacts_dir = artifacts_dir or Path(f"artifacts/{agent_id}")
        self._mkt: MarketSelectors = get_market_selectors(market)
        self._iframe_rect: BoundingRect | None = None
        self._iframe_handle: ElementHandle | None = None

    def locate_iframe(self) -> BoundingRect:
        """Find the game iframe and cache its bounding rectangle."""
        logger.info("[%s] Locating game iframe...", self._agent_id)
        iframe_locator = find_game_iframe(self._page, self._mkt.selectors.game_iframe, _IFRAME_WAIT_TIMEOUT_MS)

        handle = iframe_locator.element_handle()
        if handle is None:
            raise RuntimeError(f"[{self._agent_id}] Game iframe element handle is None")
        self._iframe_handle = handle

        box = handle.bounding_box()
        if box is None:
            raise RuntimeError(f"[{self._agent_id}] Game iframe bounding box is None")

        self._iframe_rect = BoundingRect(
            x=box["x"],
            y=box["y"],
            width=box["width"],
            height=box["height"],
        )
        logger.info(
            "[%s] Iframe located at (%.1f, %.1f) size %.1fx%.1f",
            self._agent_id,
            self._iframe_rect.x,
            self._iframe_rect.y,
            self._iframe_rect.width,
            self._iframe_rect.height,
        )
        return self._iframe_rect

    def refresh_iframe_rect(self) -> BoundingRect:
        """Re-read the iframe bounding rectangle."""
        return self.locate_iframe()

    @property
    def iframe_rect(self) -> BoundingRect:
        """Cached iframe bounding rectangle."""
        if self._iframe_rect is None:
            raise RuntimeError(f"[{self._agent_id}] Iframe not located yet — call locate_iframe() first")
        return self._iframe_rect

    def relative_to_absolute(self, rel: RelativeCoords) -> AbsoluteCoords:
        """Convert relative game coords (0.0-1.0) to absolute page coords (R9)."""
        rect = self.iframe_rect
        return AbsoluteCoords(
            x=rect.x + rel["x"] * rect.width,
            y=rect.y + rel["y"] * rect.height,
        )

    def pixel_to_absolute(self, px_x: int, px_y: int, img_w: int, img_h: int) -> AbsoluteCoords:
        """Convert screenshot pixel coords to absolute page coords."""
        return self.relative_to_absolute(RelativeCoords(x=px_x / img_w, y=px_y / img_h))

    def click_at_relative(self, rel: RelativeCoords) -> None:
        """Click at relative coordinates within game iframe."""
        abs_coords = self.relative_to_absolute(rel)
        logger.info(
            "[%s] Clicking relative (%.3f, %.3f) -> absolute (%.1f, %.1f)",
            self._agent_id,
            rel["x"],
            rel["y"],
            abs_coords["x"],
            abs_coords["y"],
        )
        self._page.mouse.click(abs_coords["x"], abs_coords["y"])
        self._page.wait_for_timeout(_CLICK_SETTLING_MS)

    def click_at_absolute(self, abs_coords: AbsoluteCoords) -> None:
        """Click at absolute page coordinates."""
        logger.info("[%s] Clicking absolute (%.1f, %.1f)", self._agent_id, abs_coords["x"], abs_coords["y"])
        self._page.mouse.click(abs_coords["x"], abs_coords["y"])
        self._page.wait_for_timeout(_CLICK_SETTLING_MS)

    def click_spin(self, spin_coords: RelativeCoords) -> None:
        """Click the Spin button using coordinates supplied by vision."""
        logger.info("[%s] Clicking SPIN button", self._agent_id)
        self.click_at_relative(spin_coords)

    def take_screenshot(self, name: str = "game") -> Path:
        """Capture screenshot of the full page."""
        evidence_dir = self._artifacts_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / f"{name}_{int(time.time() * 1000)}.png"

        self._page.wait_for_timeout(_SCREENSHOT_SETTLING_MS)
        self._page.screenshot(path=str(path), full_page=False)
        logger.info("[%s] Screenshot saved: %s", self._agent_id, path)
        return path

    def take_game_screenshot(self, name: str = "game_area") -> Path:
        """Capture screenshot clipped exactly to the game iframe area."""
        rect = self.iframe_rect
        evidence_dir = self._artifacts_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / f"{name}_{int(time.time() * 1000)}.png"

        self._page.wait_for_timeout(_SCREENSHOT_SETTLING_MS)
        self._page.screenshot(
            path=str(path),
            clip={
                "x": rect.x,
                "y": rect.y,
                "width": rect.width,
                "height": rect.height,
            },
        )
        logger.info("[%s] Game screenshot saved: %s", self._agent_id, path)
        return path

    def take_fullpage_screenshot(self, name: str = "fullpage") -> Path:
        """Capture a full-page scroll screenshot for evidence."""
        evidence_dir = self._artifacts_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / f"{name}_{int(time.time() * 1000)}.png"

        self._page.wait_for_timeout(_SCREENSHOT_SETTLING_MS)
        self._page.screenshot(path=str(path), full_page=True)
        logger.info("[%s] Full-page screenshot saved: %s", self._agent_id, path)
        return path

    def dismiss_intros(self) -> None:
        """Dismiss intro screens or responsible gaming popups in game wrapper."""
        logger.info("[%s] Dismissing intro overlays...", self._agent_id)
        self._page.wait_for_timeout(2000)

        for selector in GAME_WRAPPER_DISMISS_SELECTORS:
            try:
                loc = self._page.locator(selector)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=3000)
                    logger.debug("[%s] Dismissed intro: %s", self._agent_id, selector)
                    self._page.wait_for_timeout(500)
            except Exception:
                continue

        logger.info("[%s] Intro dismissal complete", self._agent_id)

    def get_frame_locator(self) -> FrameLocator:
        """Get FrameLocator for wrapper elements inside iframe container."""
        return self._page.frame_locator(self._mkt.selectors.game_iframe)

    @property
    def page(self) -> Page:
        return self._page

    @property
    def market_config(self) -> MarketSelectors:
        return self._mkt
