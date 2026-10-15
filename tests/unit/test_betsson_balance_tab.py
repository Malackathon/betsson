"""GameFlow reads the Betsson balance from a fresh lobby tab (the in-game header hides the amount)."""

from __future__ import annotations

from decimal import Decimal

import pytest

import src.flows.game_flow as game_flow
from src.flows.game_flow import GameFlow


class FakeTab:
    def __init__(self) -> None:
        self.visited: list[str] = []
        self.closed = False

    def goto(self, url: str, timeout: int = 0) -> None:
        self.visited.append(url)

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self) -> None:
        self.tabs: list[FakeTab] = []

    def new_page(self) -> FakeTab:
        tab = FakeTab()
        self.tabs.append(tab)
        return tab


class FakeGamePage:
    def __init__(self) -> None:
        self.brought_to_front = 0

    def bring_to_front(self) -> None:
        self.brought_to_front += 1


class FakeCanvas:
    def __init__(self) -> None:
        self.page = FakeGamePage()


class FakeReader:
    fail = False

    def __init__(self, page, market, agent_id, auth_state_dir=None, **kwargs) -> None:
        self.page = page

    def _dismiss_overlays(self) -> None:
        pass

    def read_balance_stable(self) -> Decimal:
        if FakeReader.fail:
            raise LookupError("no balance")
        return Decimal("99.80")

    def read_currency_from_header(self) -> str:
        return "€"


@pytest.fixture
def flow(monkeypatch):
    monkeypatch.setattr(game_flow, "LobbyPage", FakeReader)
    FakeReader.fail = False
    f = GameFlow(playwright=None, market="com", agent_id="agent_com_s1")
    f._ctx_game = FakeContext()
    f._canvas = FakeCanvas()
    return f


def test_reads_balance_and_currency_from_a_separate_lobby_tab(flow):
    balance, currency = flow._read_betsson()

    assert (balance, currency) == (Decimal("99.80"), "€")
    tab = flow._ctx_game.tabs[0]
    assert tab.visited and tab.visited[0].startswith("http")
    assert tab.closed is True


def test_game_tab_is_brought_back_to_the_front(flow):
    flow._read_betsson()
    assert flow._canvas.page.brought_to_front == 1


def test_tab_is_closed_and_game_refocused_even_when_reading_fails(flow):
    FakeReader.fail = True
    with pytest.raises(LookupError):
        flow._read_betsson()

    assert flow._ctx_game.tabs[0].closed is True
    assert flow._canvas.page.brought_to_front == 1
