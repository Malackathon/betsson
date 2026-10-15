"""Unit tests for src.vision.gemini_inspector.

Tests response parsing, schema validation, rate limiter logic,
spin button caching, and low-legibility escalation using mocks.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest

from src.vision.gemini_inspector import (
    GeminiBalanceReading,
    GeminiHudReading,
    GeminiInspector,
    GeminiMessageReading,
    RateLimiter,
    SpinButtonLocation,
    _spin_cache,
    _spin_cache_lock,
)


@pytest.fixture
def dummy_image() -> Image.Image:
    return Image.new("RGB", (200, 100), (40, 40, 40))


class TestRateLimiter:
    def test_backoff_delay_exponential(self) -> None:
        delay_0 = RateLimiter.backoff_delay(0)
        delay_2 = RateLimiter.backoff_delay(2)
        assert delay_0 >= 1.0
        assert delay_2 >= 4.0

    def test_acquire_and_release(self) -> None:
        limiter = RateLimiter(max_concurrent=2)
        limiter.acquire()
        limiter.release()


class TestGeminiInspector:
    def test_read_hud_mocked(self, dummy_image: Image.Image) -> None:
        inspector = GeminiInspector(api_key="test-key")

        mock_payload = {
            "credit_raw": "100.50 €",
            "bet_raw": "0.20 €",
            "win_raw": "0.00 €",
            "currency": "€",
            "legible": True,
        }

        with patch.object(inspector, "_call_gemini", return_value=mock_payload) as mock_call:
            reading = inspector.read_hud(dummy_image)
            assert isinstance(reading, GeminiHudReading)
            assert reading.credit_raw == "100.50 €"
            assert reading.currency == "€"
            assert reading.legible is True
            mock_call.assert_called_once()

    def test_read_balance_mocked(self, dummy_image: Image.Image) -> None:
        inspector = GeminiInspector(api_key="test-key")

        mock_payload = {
            "raw_text": "S/ 1,250.00",
            "amount": "1,250.00",
            "currency": "S/",
            "legible": True,
        }

        with patch.object(inspector, "_call_gemini", return_value=mock_payload):
            reading = inspector.read_balance(dummy_image)
            assert isinstance(reading, GeminiBalanceReading)
            assert reading.amount == "1,250.00"
            assert reading.currency == "S/"
            assert reading.legible is True

    def test_read_message_mocked(self, dummy_image: Image.Image) -> None:
        inspector = GeminiInspector(api_key="test-key")

        mock_payload = {
            "raw_text": "Fondos insuficientes para realizar la apuesta",
            "message_text": "Fondos insuficientes",
            "detected_language": "ES",
            "is_error": True,
            "legible": True,
        }

        with patch.object(inspector, "_call_gemini", return_value=mock_payload):
            reading = inspector.read_message(dummy_image)
            assert isinstance(reading, GeminiMessageReading)
            assert reading.detected_language == "ES"
            assert reading.is_error is True

    def test_locate_spin_button_and_cache(self, dummy_image: Image.Image) -> None:
        market = "betsson_com_test"
        with _spin_cache_lock:
            _spin_cache.pop(market, None)

        inspector = GeminiInspector(api_key="test-key")

        mock_payload = {
            "x_pct": 0.85,
            "y_pct": 0.75,
            "confidence": 0.95,
            "legible": True,
        }

        with patch.object(inspector, "_call_gemini", return_value=mock_payload) as mock_call:
            loc1 = inspector.locate_spin_button(dummy_image, market=market)
            assert isinstance(loc1, SpinButtonLocation)
            assert loc1.x_pct == 0.85
            assert mock_call.call_count == 1

            # Second call should use cache
            loc2 = inspector.locate_spin_button(dummy_image, market=market)
            assert loc2.x_pct == 0.85
            assert mock_call.call_count == 1  # No additional API call

