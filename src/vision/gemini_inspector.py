"""Gemini vision inspector for slot game HUD reading and UI element detection.

Uses Google Gemini (Flash primary, Pro escalation) to read game values,
detect error messages, and locate the spin button via screenshots.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TEMPORAL Pydantic models — will be replaced by src.models.schemas at integration
# ---------------------------------------------------------------------------


class GeminiBalanceReading(BaseModel):
    """Balance reading from lobby/header screenshot."""
    raw_text: str = ""
    amount: str | None = None
    currency: str | None = None
    legible: bool = False


class GeminiHudReading(BaseModel):
    """HUD reading (CREDIT/BET/WIN) from game screenshot."""
    credit_raw: str | None = None
    bet_raw: str | None = None
    win_raw: str | None = None
    currency: str | None = None
    legible: bool = False


class GeminiMessageReading(BaseModel):
    """Error/warning message extraction from screenshot."""
    raw_text: str = ""
    message_text: str | None = None
    detected_language: str | None = None
    is_error: bool = False
    legible: bool = False


class SpinButtonLocation(BaseModel):
    """Spin button coordinates relative to screenshot dimensions."""
    x_pct: float = 0.0
    y_pct: float = 0.0
    confidence: float = 0.0
    legible: bool = False


# ---------------------------------------------------------------------------
# Rate limiter (R12) — shared across parallel agents
# ---------------------------------------------------------------------------

_DEFAULT_MAX_CONCURRENT = 4
_MAX_RETRIES = 5
_BASE_DELAY = 1.0
_MAX_DELAY = 30.0


class RateLimiter:
    """Thread-safe rate limiter with semaphore + exponential backoff for 429s."""

    def __init__(self, max_concurrent: int = _DEFAULT_MAX_CONCURRENT) -> None:
        self._semaphore = threading.Semaphore(max_concurrent)
        self._lock = threading.Lock()

    def acquire(self) -> None:
        self._semaphore.acquire()

    def release(self) -> None:
        self._semaphore.release()

    @staticmethod
    def backoff_delay(attempt: int) -> float:
        """Exponential backoff with jitter."""
        delay = min(_BASE_DELAY * (2 ** attempt), _MAX_DELAY)
        jitter = random.uniform(0, delay * 0.5)
        return delay + jitter


# Module-level shared limiter
_shared_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# Spin button cache per market
# ---------------------------------------------------------------------------

_spin_cache: dict[str, SpinButtonLocation] = {}
_spin_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# GeminiInspector
# ---------------------------------------------------------------------------


class GeminiInspector:
    """Vision inspector powered by Google Gemini API.

    Uses ``gemini-2.5-flash`` by default and escalates to ``gemini-2.5-pro``
    only when legibility is low or readings are discrepant (never for
    reconciliation failures — R6).
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        fast_model: str | None = None,
        pro_model: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._fast = fast_model or os.getenv("GEMINI_FAST_MODEL", "gemini-2.5-flash")
        self._pro = pro_model or os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")
        self._limiter = rate_limiter or _shared_limiter
        self._client: Any = None  # lazy init

    def _get_client(self) -> Any:
        """Lazy-initialise the genai client."""
        if self._client is None:
            from google import genai  # type: ignore[import-untyped]
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    # ------------------------------------------------------------------
    # Internal call with retry + escalation
    # ------------------------------------------------------------------

    def _prepare_image(self, screenshot: Image.Image | Path | bytes) -> Image.Image:
        """Load and resize an image for the API."""
        from src.vision.image_utils import load_image, resize_for_api
        if isinstance(screenshot, Image.Image):
            img = screenshot
        else:
            img = load_image(screenshot)
        return resize_for_api(img)

    def _call_gemini(
        self,
        prompt: str,
        image: Image.Image,
        response_schema: type[BaseModel],
        *,
        escalate_on_low_legibility: bool = True,
    ) -> dict[str, Any]:
        """Call Gemini with retry/backoff and optional Flash→Pro escalation.

        Returns the parsed JSON dict from the model response.
        """
        import json
        from google import genai  # type: ignore[import-untyped]
        from src.vision.image_utils import image_to_bytes

        client = self._get_client()
        img_bytes = image_to_bytes(image, fmt="PNG")

        image_part = genai.types.Part.from_bytes(data=img_bytes, mime_type="image/png")

        models_to_try = [self._fast]
        if escalate_on_low_legibility:
            models_to_try.append(self._pro)

        last_error: Exception | None = None

        for model_name in models_to_try:
            for attempt in range(_MAX_RETRIES):
                self._limiter.acquire()
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[image_part, prompt],
                        config=genai.types.GenerateContentConfig(
                            temperature=0,
                            response_mime_type="application/json",
                            response_schema=response_schema,
                        ),
                    )
                    text = response.text or "{}"
                    parsed = json.loads(text)
                    # Check legibility for escalation
                    if (escalate_on_low_legibility
                            and model_name == self._fast
                            and not parsed.get("legible", True)):
                        logger.info("Low legibility on Flash, escalating to Pro")
                        break  # break retry loop to try Pro
                    return parsed

                except Exception as exc:
                    last_error = exc
                    exc_str = str(exc)
                    if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                        delay = self._limiter.backoff_delay(attempt)
                        logger.warning(
                            "Rate limited (429) on %s, attempt %d/%d, "
                            "backing off %.1fs",
                            model_name, attempt + 1, _MAX_RETRIES, delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error("Gemini error on %s: %s", model_name, exc)
                        if attempt < _MAX_RETRIES - 1:
                            time.sleep(self._limiter.backoff_delay(attempt))
                        else:
                            break
                finally:
                    self._limiter.release()

        logger.error("All Gemini attempts exhausted: %s", last_error)
        return {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_hud(self, screenshot: Image.Image | Path | bytes) -> GeminiHudReading:
        """Read CREDIT/BET/WIN values from the game HUD.

        Returns raw text for post-processing (R5).
        """
        img = self._prepare_image(screenshot)
        prompt = (
            "Look at this slot game screenshot. Read the HUD values displayed on screen. "
            "Return the RAW TEXT exactly as shown for each field:\n"
            "- credit_raw: the CREDIT or BALANCE value shown (exact text including currency symbol)\n"
            "- bet_raw: the BET or STAKE value shown (exact text)\n"
            "- win_raw: the WIN value shown (exact text, '0' or '0.00' if no win)\n"
            "- currency: the currency symbol or code visible (€, S/, PEN, EUR, etc.)\n"
            "- legible: true if the text is clearly readable, false if blurry/obscured\n"
            "Return ONLY the raw text as displayed, do not parse or convert numbers."
        )
        data = self._call_gemini(prompt, img, GeminiHudReading)
        return GeminiHudReading.model_validate(data) if data else GeminiHudReading()

    def read_balance(self, screenshot: Image.Image | Path | bytes) -> GeminiBalanceReading:
        """Read balance from the lobby/header area.

        Returns raw text for post-processing (R5).
        """
        img = self._prepare_image(screenshot)
        prompt = (
            "Look at this screenshot of a betting website lobby or header area. "
            "Find and read the player's account balance displayed in the header/toolbar. "
            "Return:\n"
            "- raw_text: the complete balance text exactly as shown on screen\n"
            "- amount: just the numeric part as a string (e.g. '1,234.56' or '1.234,56')\n"
            "- currency: the currency symbol or code (€, S/, PEN, EUR)\n"
            "- legible: true if clearly readable\n"
            "Return the RAW TEXT as displayed, do not normalize the number format."
        )
        data = self._call_gemini(prompt, img, GeminiBalanceReading)
        return GeminiBalanceReading.model_validate(data) if data else GeminiBalanceReading()

    def read_message(self, screenshot: Image.Image | Path | bytes) -> GeminiMessageReading:
        """Extract error/warning messages from the screenshot.

        Detects insufficient funds messages, popups, and modals (R5).
        """
        img = self._prepare_image(screenshot)
        prompt = (
            "Look at this slot game or betting site screenshot. "
            "Check if there is any error message, warning, or popup visible. "
            "Focus on messages about insufficient funds/balance. Return:\n"
            "- raw_text: the complete message text exactly as displayed\n"
            "- message_text: the key message content\n"
            "- detected_language: 'EN' for English, 'ES' for Spanish\n"
            "- is_error: true if this is an error/warning about funds/balance\n"
            "- legible: true if the text is clearly readable\n"
            "If no message is visible, set raw_text to empty and is_error to false."
        )
        data = self._call_gemini(prompt, img, GeminiMessageReading)
        return GeminiMessageReading.model_validate(data) if data else GeminiMessageReading()

    def locate_spin_button(
        self,
        screenshot: Image.Image | Path | bytes,
        *,
        market: str = "",
    ) -> SpinButtonLocation:
        """Find the spin button coordinates relative to the screenshot.

        Uses a per-market cache to avoid redundant API calls (R9).
        """
        # Check cache
        with _spin_cache_lock:
            if market and market in _spin_cache:
                cached = _spin_cache[market]
                logger.debug("Spin button cache hit for market=%s", market)
                return cached

        img = self._prepare_image(screenshot)
        prompt = (
            "Look at this slot game screenshot. Locate the SPIN button "
            "(the main round button to start spinning the reels). "
            "Return its center position as percentages of the image dimensions:\n"
            "- x_pct: horizontal position (0.0 = left edge, 1.0 = right edge)\n"
            "- y_pct: vertical position (0.0 = top edge, 1.0 = bottom edge)\n"
            "- confidence: how confident you are (0.0-1.0)\n"
            "- legible: true if the button is clearly visible"
        )
        data = self._call_gemini(prompt, img, SpinButtonLocation)
        result = SpinButtonLocation.model_validate(data) if data else SpinButtonLocation()

        # Cache on success
        if result.confidence > 0.5 and market:
            with _spin_cache_lock:
                _spin_cache[market] = result
                logger.info("Cached spin button for market=%s: (%.2f, %.2f)",
                            market, result.x_pct, result.y_pct)

        return result

