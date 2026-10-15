"""Game iframe finder and page snapshot against real Chromium (static HTML)."""

from __future__ import annotations

import pytest

from src.browser.iframe_finder import find_game_iframe, page_snapshot

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


def test_configured_selector_wins_when_present(page):
    page.set_content("<iframe class='game-iframe' width=500 height=300 srcdoc='a'></iframe>")
    loc = find_game_iframe(page, "iframe.game-iframe", timeout_ms=500)
    assert loc.get_attribute("class") == "game-iframe"


def test_falls_back_to_the_largest_visible_iframe_ignoring_tiny_trackers(page):
    page.set_content(
        "<iframe id='pixel' width=1 height=1 srcdoc='x'></iframe>"
        "<iframe id='ad' width=300 height=100 srcdoc='x'></iframe>"
        "<iframe id='game' width=900 height=500 srcdoc='x'></iframe>"
    )
    loc = find_game_iframe(page, "iframe.nope", timeout_ms=300)
    assert loc.get_attribute("id") == "game"


def test_iframe_inside_a_shadow_root_is_found(page):
    page.set_content(
        "<x-host></x-host><script>customElements.define('x-host', class extends HTMLElement {"
        "constructor(){super(); this.attachShadow({mode:'open'}).innerHTML="
        "\"<iframe id='shadow-game' width=800 height=450 srcdoc='x'></iframe>\";}});</script>"
    )
    assert find_game_iframe(page, "iframe.nope", timeout_ms=300).get_attribute("id") == "shadow-game"


def test_no_suitable_iframe_raises(page):
    page.set_content("<iframe width=1 height=1 srcdoc='x'></iframe><p>nothing</p>")
    with pytest.raises(LookupError):
        find_game_iframe(page, "iframe.nope", timeout_ms=300)


def test_snapshot_lists_iframes_dialogs_and_buttons_without_emails_or_queries(page):
    page.set_content(
        "<button>Jugar</button><button>user@mail.com</button>"
        "<div role='dialog'>Establece un límite de sesión</div>"
        "<iframe width=700 height=400 src='about:blank'></iframe>"
    )
    snap = page_snapshot(page)
    assert "Jugar" in snap["buttons"]
    assert all("@" not in b for b in snap["buttons"])
    assert any("límite de sesión" in d for d in snap["dialogs"])
    assert snap["iframes"] and snap["iframes"][0]["size"] in {"700x400", "704x404"}
