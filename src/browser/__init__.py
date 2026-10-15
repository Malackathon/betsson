"""Browser automation layer for Betsson lobby and game interaction.

Exports:
    - ``LobbyPage``: Login, navigation, and balance reading.
    - ``GameCanvas``: Game iframe interaction, screenshots, coordinate mapping.
    - ``get_market_selectors``, ``MarketSelectors``: Market config + selectors.
"""
from src.browser.game_canvas import (
    AbsoluteCoords,
    BoundingRect,
    GameCanvas,
    RelativeCoords,
)
from src.browser.lobby_page import LobbyPage
from src.browser.selectors import (
    MarketSelectors,
    SelectorSet,
    get_active_markets,
    get_market_selectors,
)

__all__ = [
    "AbsoluteCoords",
    "BoundingRect",
    "GameCanvas",
    "LobbyPage",
    "MarketSelectors",
    "RelativeCoords",
    "SelectorSet",
    "get_active_markets",
    "get_market_selectors",
]

