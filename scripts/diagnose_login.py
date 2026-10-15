"""Diagnose why login / the post-login balance is not found (run by hand; never prints credentials).

Usage:  python scripts/diagnose_login.py agent_com_s1
Prints the login page structure BEFORE typing, how many elements each configured selector
matches, and any error/alert text AFTER submitting. Input VALUES are never printed; no
screenshots, no cookies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import Page, sync_playwright  # noqa: E402

from config.settings import get_settings  # noqa: E402
from src.browser.lobby_page import LobbyPage  # noqa: E402
from src.browser.selectors import get_market_selectors  # noqa: E402

SETTLE_MS = 12_000
PAGE_WAIT_MS = 6_000
BALANCE_LIKE = (
    "[data-testid*='balance' i], [class*='balance' i], [id*='balance' i], "
    "[data-testid*='wallet' i], [class*='wallet' i], [class*='saldo' i]"
)
ALERTS = "[role='alert'], [class*='error' i], [class*='invalid' i], [class*='alert' i], [class*='captcha' i]"
JS_INPUTS = """els => els.filter(e => e.offsetWidth || e.offsetHeight).slice(0, 12).map(e => ({
  type: e.type, name: e.name, id: e.id, placeholder: e.placeholder,
  autocomplete: e.autocomplete, aria: e.getAttribute('aria-label')}))"""
JS_BUTTONS = """els => els.filter(e => e.offsetWidth || e.offsetHeight).slice(0, 15).map(e => ({
  tag: e.tagName.toLowerCase(), testid: e.getAttribute('data-testid'),
  text: ((e.innerText || e.getAttribute('label') || '')).trim().slice(0, 40)}))"""
JS_TEXTS = "els => els.filter(e => e.offsetWidth || e.offsetHeight).slice(0, 8).map(e => (e.innerText || '').trim().slice(0, 120))"
JS_DESCRIBE = """els => els.slice(0, 15).map(e => ({
  tag: e.tagName.toLowerCase(), testid: e.getAttribute('data-testid'),
  cls: (e.getAttribute('class') || '').slice(0, 70),
  visible: !!(e.offsetWidth || e.offsetHeight), text: (e.innerText || '').trim().slice(0, 40)}))"""


def _where(page: Page) -> str:
    url = urlsplit(page.url)
    return f"{url.scheme}://{url.netloc}{url.path}  title={page.title()!r}"


AUTH_URL_HINTS = ("login", "auth", "session", "signin", "token", "authenticate")
ERROR_KEYS = ("error", "errors", "message", "msg", "code", "status", "reason", "type", "title")


def _report_auth_response(response) -> None:
    """Print status + error-like fields of login-ish POSTs. Request bodies are never read."""
    request = response.request
    path = urlsplit(response.url).path.lower()
    if request.method != "POST" or not any(hint in path for hint in AUTH_URL_HINTS):
        return
    summary = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            summary = {k: str(data[k])[:120] for k in ERROR_KEYS if k in data}
            summary = f" keys={sorted(data)[:10]} error-like={summary}"
    except Exception:
        summary = " (non-JSON body)"
    print(f"  [auth POST] {urlsplit(response.url).netloc}{path} -> HTTP {response.status}{summary}")


def _click_submit(page: Page) -> None:
    buttons = page.locator("fdsp-button:has-text('Iniciar sesión'), fdsp-button:has-text('Log in')")
    visible = [buttons.nth(i) for i in range(buttons.count()) if buttons.nth(i).is_visible()]
    if visible:
        visible[-1].click(timeout=5_000)
    else:
        print("  no visible submit button found")


def _dump_structure(page: Page, label: str) -> None:
    print(f"\n[{label}] {_where(page)}")
    print("  frames :", [urlsplit(f.url).netloc or "(inline)" for f in page.frames][:8])
    print("  inputs :", page.locator("input").evaluate_all(JS_INPUTS))
    print("  buttons:", page.locator("button, fdsp-button, a[role='button']").evaluate_all(JS_BUTTONS))


def main(agent_id: str) -> None:
    _, market, _scenario = agent_id.split("_")
    settings = get_settings()
    creds = settings.get_credentials(agent_id)
    mkt = get_market_selectors(market)
    sel = mkt.selectors
    browser_name = (os.getenv("PLAYWRIGHT_BROWSER") or "chromium").lower()

    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch(headless=settings.headless)
        page = browser.new_context().new_page()
        lobby = LobbyPage(page=page, market=market, agent_id=agent_id)
        print(f"browser={browser_name} base_url={mkt.url}")
        page.goto(mkt.url, timeout=45_000)
        lobby._dismiss_overlays()
        page.locator(sel.login_button).first.click(timeout=15_000)
        page.wait_for_timeout(PAGE_WAIT_MS)
        _dump_structure(page, "login page, before typing")
        for name in ("username_input", "password_input", "submit_login"):
            print(f"  selector {name}: {page.locator(getattr(sel, name)).count()} match(es)")

        page.on("response", _report_auth_response)
        page.locator(sel.username_input).first.fill(creds.username)
        page.locator(sel.password_input).first.fill(creds.password)
        page.locator(sel.password_input).first.press("Enter")
        page.wait_for_timeout(PAGE_WAIT_MS)
        if page.locator(sel.password_input).first.is_visible():
            print("\n  Enter did not leave the login page; clicking the visible 'Iniciar sesión' button")
            _click_submit(page)
        page.wait_for_timeout(SETTLE_MS)

        _dump_structure(page, "after submit")
        print("  alert/error texts:", page.locator(ALERTS).evaluate_all(JS_TEXTS))
        print("  password field still visible:", page.locator(sel.password_input).first.is_visible())
        print("  configured balance selector visible:", page.locator(sel.balance_display).first.is_visible())
        print("  balance-like elements:", page.locator(BALANCE_LIKE).evaluate_all(JS_DESCRIBE))
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "agent_com_s1")
