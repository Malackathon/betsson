"""Unit tests for src.browser.selectors — pure logic, no network.

Tests:
- Loading market config from markets.json.
- SelectorSet game_card template substitution.
- Cache clearing.
- Error on unknown market.
- MarketSelectors field integrity.
"""
from __future__ import annotations

import pytest

from src.browser.selectors import (
    MarketSelectors,
    SelectorSet,
    clear_cache,
    get_active_markets,
    get_market_selectors,
)


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    """Ensure each test starts with a clean selector cache."""
    clear_cache()
    yield  # type: ignore[misc]
    clear_cache()


class TestGetMarketSelectors:
    """Tests for ``get_market_selectors()``."""

    def test_load_com_market(self) -> None:
        """Loading 'com' market should return valid MarketSelectors."""
        mkt = get_market_selectors("com")
        assert isinstance(mkt, MarketSelectors)
        assert mkt.market == "com"
        assert mkt.locale == "en"
        assert mkt.currency == "EUR"
        assert mkt.currency_symbol == "€"
        assert mkt.active is True
        assert "betsson.com" in mkt.url

    def test_default_market_is_com(self) -> None:
        """Calling get_market_selectors() without args defaults to 'com'."""
        mkt = get_market_selectors()
        assert mkt.market == "com"

    def test_get_active_markets(self) -> None:
        """get_active_markets() returns only currently active markets (com)."""
        active = get_active_markets()
        assert active == ["com"]

    def test_pe_market_is_inactive(self) -> None:
        """PE market is loaded but marked active=False."""
        mkt = get_market_selectors("pe")
        assert mkt.active is False

    def test_load_pe_market(self) -> None:
        """Loading 'pe' market should return valid MarketSelectors."""
        mkt = get_market_selectors("pe")
        assert isinstance(mkt, MarketSelectors)
        assert mkt.market == "pe"
        assert mkt.locale == "es"
        assert mkt.currency == "PEN"
        assert mkt.currency_symbol == "S/"
        assert "betsson.pe" in mkt.url

    def test_unknown_market_raises_key_error(self) -> None:
        """Unknown market key should raise KeyError."""
        with pytest.raises(KeyError, match="not found"):
            get_market_selectors("xx")

    def test_cache_returns_same_object(self) -> None:
        """Second call should return the same cached object."""
        mkt1 = get_market_selectors("com")
        mkt2 = get_market_selectors("com")
        assert mkt1 is mkt2

    def test_clear_cache_reloads(self) -> None:
        """After clearing cache, objects should be fresh (equal but not identical)."""
        mkt1 = get_market_selectors("com")
        clear_cache()
        mkt2 = get_market_selectors("com")
        assert mkt1 == mkt2
        assert mkt1 is not mkt2


class TestMarketSelectorsFields:
    """Tests for ``MarketSelectors`` field integrity."""

    def test_game_candidates_non_empty(self) -> None:
        """Each market must have at least one game candidate."""
        for market in ("com", "pe"):
            mkt = get_market_selectors(market)
            assert len(mkt.game_candidates) > 0, f"{market}: no game candidates"

    def test_keywords_insufficient_non_empty(self) -> None:
        """Each market must have keywords for insufficient-funds detection."""
        for market in ("com", "pe"):
            mkt = get_market_selectors(market)
            assert len(mkt.keywords_insufficient) > 0

    def test_com_keywords_english(self) -> None:
        """COM market keywords should be in English."""
        mkt = get_market_selectors("com")
        kw_lower = [k.lower() for k in mkt.keywords_insufficient]
        assert any("insufficient" in k or "funds" in k or "balance" in k for k in kw_lower)

    def test_pe_keywords_spanish(self) -> None:
        """PE market keywords should be in Spanish."""
        mkt = get_market_selectors("pe")
        kw_lower = [k.lower() for k in mkt.keywords_insufficient]
        assert any("insuficiente" in k or "fondos" in k or "saldo" in k for k in kw_lower)

    def test_number_format_present(self) -> None:
        """Number format config should be present for both markets."""
        for market in ("com", "pe"):
            mkt = get_market_selectors(market)
            assert "decimal_sep" in mkt.number_format
            assert "thousands_sep" in mkt.number_format

    def test_casino_url_present(self) -> None:
        """Casino URL should be a valid-looking URL for both markets."""
        for market in ("com", "pe"):
            mkt = get_market_selectors(market)
            assert mkt.casino_url.startswith("https://")
            assert "casino" in mkt.casino_url.lower()

    def test_notes_present(self) -> None:
        """Spike notes must be documented for each market."""
        for market in ("com", "pe"):
            mkt = get_market_selectors(market)
            assert isinstance(mkt.notes, list)
            assert len(mkt.notes) > 0, f"{market} missing spike notes"


class TestSelectorSet:
    """Tests for ``SelectorSet`` and selector patterns."""

    def test_game_card_substitution(self) -> None:
        """``game_card()`` should substitute the game name placeholder."""
        mkt = get_market_selectors("com")
        selector = mkt.selectors.game_card("Sweet Bonanza")
        assert "Sweet Bonanza" in selector
        assert "{game_name}" not in selector

    def test_all_selectors_non_empty(self) -> None:
        """All selectors in SelectorSet should be non-empty strings."""
        for market in ("com", "pe"):
            mkt = get_market_selectors(market)
            sel = mkt.selectors
            for field_name in [
                "login_button",
                "username_input",
                "password_input",
                "submit_login",
                "balance_display",
                "currency_display",
                "search_input",
                "game_card_template",
                "play_real_button",
                "game_iframe",
                "close_modal",
                "cookie_accept",
            ]:
                value = getattr(sel, field_name)
                assert isinstance(value, str) and len(value) > 0, (
                    f"{market}.{field_name} is empty or not a string"
                )

    def test_selectors_frozen(self) -> None:
        """SelectorSet should be frozen (immutable)."""
        mkt = get_market_selectors("com")
        with pytest.raises(AttributeError):
            mkt.selectors.login_button = "modified"  # type: ignore[misc]

    def test_market_selectors_frozen(self) -> None:
        """MarketSelectors should be frozen (immutable)."""
        mkt = get_market_selectors("com")
        with pytest.raises(AttributeError):
            mkt.market = "modified"  # type: ignore[misc]

