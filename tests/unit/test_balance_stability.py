"""LobbyPage.read_balance_stable against real Chromium with a static or moving balance."""

from __future__ import annotations

from decimal import Decimal

import pytest

import src.browser.lobby_page as lobby_page
from src.browser.lobby_page import LobbyPage

pytestmark = pytest.mark.slow


@pytest.fixture
def page():
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Error:
            pytest.skip("Chromium is not installed")
        yield browser.new_page(viewport={"width": 1280, "height": 720})
        browser.close()


def _lobby(page) -> LobbyPage:
    return LobbyPage(page=page, market="com", agent_id="agent_com_s1")


def test_static_balance_is_read_and_stabilises(page):
    page.set_content("<header style='height:60px'><span>Saldo</span><span>71,08 €</span></header>")
    assert _lobby(page).read_balance_stable() == Decimal("71.08")


def test_probed_element_is_reused_instead_of_searched_again(page):
    page.set_content("<header style='height:60px'><span>71,08 €</span></header>")
    lobby = _lobby(page)
    lobby.read_balance_raw()
    assert lobby._balance_probed is True
    # The second read must take the fast path: no configured-selector wait.
    import time
    t0 = time.monotonic()
    lobby.read_balance_raw()
    assert time.monotonic() - t0 < 1.0


def test_unstable_balance_error_lists_the_raw_reads(page, monkeypatch):
    monkeypatch.setattr(lobby_page, "_BALANCE_POLL_TIMEOUT_S", 3.0)
    page.set_content(
        "<header style='height:60px'><span id='b'>1,00 €</span></header>"
        "<script>let n=1; setInterval(()=>{n++; document.getElementById('b').textContent=n+',00 €'}, 150)</script>"
    )
    with pytest.raises(TimeoutError) as exc:
        _lobby(page).read_balance_stable()
    assert "Raw reads" in str(exc.value)
    assert "€" in str(exc.value)
