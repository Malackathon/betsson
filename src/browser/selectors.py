"""Centralized selectors for Betsson lobby and game wrapper.

All selectors used by lobby_page.py and game_canvas.py are defined here.
Never hardcode selectors inline — import from this module.

Selector strategy (in order of preference):
1. data-testid attributes
2. ARIA roles + accessible names
3. Semantic HTML + text content
4. CSS class patterns (last resort, with fallbacks)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Path to the spike-documented market config
_MARKETS_JSON = Path(__file__).resolve().parent.parent.parent / "config" / "markets.json"


@dataclass(frozen=True)
class SelectorSet:
    """Collection of selectors for a single market, loaded from markets.json.

    Each field maps to a Playwright-compatible selector string.  Fields may
    contain comma-separated fallbacks (Playwright tries them left-to-right when
    the ``first``/``locator`` helpers are used with ``,`` syntax).

    Attributes:
        login_button: Opens the login modal / form.
        username_input: Username / email field inside the login form.
        password_input: Password field inside the login form.
        submit_login: Submit button for the login form.
        balance_display: Element showing the player's current balance.
        currency_display: Element showing the currency code or symbol.
        search_input: Game search box in the casino lobby.
        game_card_template: Game card selector with ``{game_name}`` placeholder.
        play_real_button: "Play for real" CTA on the game detail overlay.
        game_iframe: The ``<iframe>`` hosting the game provider content.
        close_modal: Generic close-modal button.
        cookie_accept: Cookie-consent accept button.
    """

    # --- Authentication ---
    login_button: str
    username_input: str
    password_input: str
    submit_login: str

    # --- Lobby / Header ---
    balance_display: str
    currency_display: str
    search_input: str
    game_card_template: str  # contains {game_name} placeholder
    play_real_button: str

    # --- Game ---
    game_iframe: str

    # --- Overlays ---
    close_modal: str
    cookie_accept: str

    def game_card(self, game_name: str) -> str:
        """Return the game card selector for a specific game title.

        Replaces the ``{game_name}`` placeholder in :pyattr:`game_card_template`
        with the actual game title.

        Args:
            game_name: Human-readable game title, e.g. ``"Sweet Bonanza"``.

        Returns:
            Ready-to-use selector string.
        """
        return self.game_card_template.replace("{game_name}", game_name)


@dataclass(frozen=True)
class MarketSelectors:
    """Selectors + market metadata loaded from the spike config.

    Bundles everything the automation layer needs to interact with a
    specific Betsson market (``com`` or ``pe``).

    Attributes:
        market: Short market identifier — ``'com'`` or ``'pe'``.
        url: Base URL of the market site.
        casino_url: Direct URL to the casino lobby.
        locale: BCP-47 language tag (``'en'``, ``'es'``).
        currency: ISO-4217 currency code (``'EUR'``, ``'PEN'``).
        currency_symbol: Display symbol (``'€'``, ``'S/'``).
        game_candidates: Ordered list of Pragmatic Play game titles to try.
        keywords_insufficient: Locale-aware keywords indicating insufficient
            funds, used by the vision / AI layer.
        selectors: The :class:`SelectorSet` for this market.
        number_format: Mapping with ``decimal_sep`` and ``thousands_sep`` keys,
            used when parsing displayed monetary amounts.
    """

    market: str  # 'com' or 'pe'
    url: str
    casino_url: str
    locale: str
    currency: str
    currency_symbol: str
    game_candidates: list[str]
    keywords_insufficient: list[str]
    selectors: SelectorSet
    number_format: dict[str, str]  # {"decimal_sep": ".", "thousands_sep": ","}
    notes: list[str] = field(default_factory=list)
    active: bool = True


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def _load_markets() -> dict[str, Any]:
    """Load and return the raw contents of ``markets.json``.

    Returns:
        Parsed JSON as a nested dict.

    Raises:
        FileNotFoundError: If the spike config has not been created yet.
    """
    with open(_MARKETS_JSON, encoding="utf-8") as f:
        return json.load(f)


_cache: dict[str, MarketSelectors] | None = None


def get_market_selectors(market: str = "com") -> MarketSelectors:
    """Get selectors and config for a market (defaults to 'com').

    Loads from ``config/markets.json`` on first call; cached thereafter.
    Use :func:`clear_cache` to force a reload (handy in tests).

    Args:
        market: Market identifier — ``'com'`` or ``'pe'``.

    Returns:
        :class:`MarketSelectors` with all selectors and market metadata.

    Raises:
        KeyError: If *market* not found in config.
        FileNotFoundError: If ``markets.json`` doesn't exist (spike not done).
    """
    global _cache  # noqa: PLW0603  — module-level cache is intentional
    if _cache is None:
        data = _load_markets()
        _cache = {}
        for mkt_key, mkt_data in data.items():
            sel_data: dict[str, str] = mkt_data["selectors"]
            selector_set = SelectorSet(
                login_button=sel_data["login_button"],
                username_input=sel_data["username_input"],
                password_input=sel_data["password_input"],
                submit_login=sel_data["submit_login"],
                balance_display=sel_data["balance_display"],
                currency_display=sel_data["currency_display"],
                search_input=sel_data["search_input"],
                game_card_template=sel_data["game_card"],
                play_real_button=sel_data["play_real_button"],
                game_iframe=sel_data["game_iframe"],
                close_modal=sel_data["close_modal"],
                cookie_accept=sel_data["cookie_accept"],
            )
            _cache[mkt_key] = MarketSelectors(
                market=mkt_key,
                url=mkt_data["url"],
                casino_url=mkt_data["casino_url"],
                locale=mkt_data["locale"],
                currency=mkt_data["currency"],
                currency_symbol=mkt_data["currency_symbol"],
                game_candidates=mkt_data["game_candidates"],
                keywords_insufficient=mkt_data["keywords_insufficient"],
                selectors=selector_set,
                number_format=mkt_data["number_format"],
                notes=mkt_data.get("notes", []),
                active=mkt_data.get("active", True),
            )
    if market not in _cache:
        raise KeyError(
            f"Market '{market}' not found in {_MARKETS_JSON}. "
            f"Available: {list(_cache.keys())}"
        )
    return _cache[market]


def get_active_markets() -> list[str]:
    """Return the list of active market identifiers (e.g. ['com'])."""
    global _cache
    if _cache is None:
        get_market_selectors("com")
    assert _cache is not None
    return [k for k, v in _cache.items() if v.active]


def clear_cache() -> None:
    """Clear the cached selectors (useful for tests)."""
    global _cache
    _cache = None


# ---------------------------------------------------------------------------
# Convenience: common compound selectors
# ---------------------------------------------------------------------------

# Overlay / popup dismiss patterns (tried in order).
# These cover cookie banners, promo popups, and generic modals that may appear
# at any point during navigation.
OVERLAY_DISMISS_SELECTORS: list[str] = [
    "#onetrust-accept-btn-handler",                    # OneTrust cookie banner
    "button[data-testid='cookie-accept']",             # Alternative cookie
    ".cookie-consent button.accept",                   # Generic cookie
    "button:has-text('Accept')",                       # EN text
    "button:has-text('Aceptar')",                      # ES text
    "button[aria-label='Close']",                      # Generic close
    "button[data-testid='close-modal']",               # Modal close
    ".modal-close",                                    # CSS class close
    "[data-testid='promotion-close']",                 # Promo popup
    ".popup-overlay button.close",                     # Generic popup
]

# Game wrapper dismiss patterns (Betsson wraps games with its own UI).
# These selectors target the informational / responsible-gaming overlays that
# Betsson shows *before* or *on top of* the game iframe.
GAME_WRAPPER_DISMISS_SELECTORS: list[str] = [
    "button[data-testid='close-game-info']",
    ".game-info-overlay button.close",
    "button:has-text('Got it')",
    "button:has-text('Entendido')",
    ".responsible-gaming-overlay button",
    "button:has-text('Continue')",
    "button:has-text('Continuar')",
]
