"""Balance probe against real Chromium with static HTML (no network)."""

from __future__ import annotations

import pytest

from src.browser.balance_probe import find_balance_locator

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


def _page_with(page, header: str, body: str = "") -> None:
    page.set_content(
        f"<html><body style='margin:0'><header style='height:60px'>{header}</header>"
        f"<main style='margin-top:300px'>{body}</main></body></html>"
    )


def test_configured_selector_wins_when_it_matches(page):
    _page_with(page, "<span class='my-balance'>12,34 €</span><span>99,99 €</span>")
    loc = find_balance_locator(page, ".my-balance", timeout_ms=500)
    assert loc.inner_text() == "12,34 €"


def test_falls_back_to_a_money_looking_header_element(page):
    _page_with(page, "<nav>Casino</nav><div class='wallet'>99,80 €</div>")
    loc = find_balance_locator(page, ".does-not-exist", timeout_ms=300)
    assert loc.inner_text() == "99,80 €"


def test_fallback_handles_symbol_and_number_in_separate_spans(page):
    _page_with(page, "<div><span>€</span><span>1,234.50</span></div>")
    loc = find_balance_locator(page, ".nope", timeout_ms=300)
    assert "1,234.50" in loc.inner_text()


def test_fallback_handles_sol_symbol(page):
    _page_with(page, "<div>S/ 250.00</div>")
    assert "250.00" in find_balance_locator(page, ".nope", timeout_ms=300).inner_text()


def test_fallback_ignores_money_below_the_header(page):
    _page_with(page, "<nav>Casino</nav>", body="<div>Jackpot 5.000 €</div>")
    with pytest.raises(LookupError):
        find_balance_locator(page, ".nope", timeout_ms=300)


def test_fallback_ignores_numbers_without_a_currency(page):
    _page_with(page, "<span>12</span><span>Casino 2026</span>")
    with pytest.raises(LookupError):
        find_balance_locator(page, ".nope", timeout_ms=300)


def test_failure_message_lists_header_strings_but_never_emails(page):
    _page_with(page, "<span>Casino 2026</span><span>player42@mail.com</span><span>Bonus 5</span>")
    with pytest.raises(LookupError) as exc:
        find_balance_locator(page, ".nope", timeout_ms=300)
    message = str(exc.value)
    assert "Casino 2026" in message
    assert "@" not in message
