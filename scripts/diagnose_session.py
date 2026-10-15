"""Is the saved/imported session actually logged in? And where is the balance in the page?

Usage:  python scripts/diagnose_session.py agent_com_s1
Loads artifacts/auth_state/auth_state_<agent>.json, opens the casino, and prints whether the
header still offers "Iniciar sesión" (NOT logged in) or shows account elements, plus balance-like
elements and any non-200 API calls (path + status only). No cookies, values or credentials printed.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from config.settings import get_settings  # noqa: E402
from src.browser.game_canvas import DEFAULT_VIEWPORT  # noqa: E402
from src.browser.lobby_page import LobbyPage  # noqa: E402
from src.browser.selectors import get_market_selectors  # noqa: E402
from src.browser.session_state import saved_session_path  # noqa: E402

SETTLE_MS = 10_000
BALANCE_LIKE = (
    "[data-testid*='balance' i], [class*='balance' i], [id*='balance' i], [data-testid*='wallet' i], "
    "[class*='wallet' i], [class*='saldo' i], [class*='account' i], [data-testid*='user' i]"
)
JS_DESCRIBE = """els => els.filter(e => e.offsetWidth || e.offsetHeight).slice(0, 15).map(e => ({
  tag: e.tagName.toLowerCase(), testid: e.getAttribute('data-testid'),
  cls: (e.getAttribute('class') || '').slice(0, 60), text: (e.innerText || '').trim().slice(0, 30)}))"""
JS_BUTTONS = """els => els.filter(e => e.offsetWidth || e.offsetHeight).slice(0, 20)
  .map(e => (e.innerText || e.getAttribute('label') || '').trim().slice(0, 30)).filter(Boolean)"""


def main(agent_id: str) -> None:
    _, market, _scenario = agent_id.split("_")
    mkt = get_market_selectors(market)
    sel = mkt.selectors
    session = saved_session_path(Path("artifacts") / agent_id, agent_id)
    if not session.is_file():
        sys.exit(f"No saved session at {session}. Run scripts/import_cookies.py first.")
    browser_name = (os.getenv("PLAYWRIGHT_BROWSER") or "chromium").lower()

    with sync_playwright() as pw:
        browser = getattr(pw, browser_name).launch(headless=get_settings().headless)
        context = browser.new_context(viewport=DEFAULT_VIEWPORT, locale=mkt.locale, storage_state=str(session))
        page = context.new_page()
        failures: Counter[str] = Counter()
        page.on(
            "response",
            lambda r: failures.update([f"{r.request.method} {r.status} {urlsplit(r.url).path}"])
            if "/api/" in r.url and r.status >= 400
            else None,
        )
        print(f"browser={browser_name} casino_url={mkt.casino_url}")
        page.goto(mkt.casino_url, timeout=60_000)
        LobbyPage(page=page, market=market, agent_id=agent_id)._dismiss_overlays()
        page.wait_for_timeout(SETTLE_MS)

        url = urlsplit(page.url)
        print(f"final url: {url.scheme}://{url.netloc}{url.path}  title={page.title()!r}")
        login_btn = page.locator(sel.login_button).first
        print("login button still visible (=> NOT logged in):", login_btn.is_visible())
        print("configured balance selector visible:", page.locator(sel.balance_display).first.is_visible())
        print("visible header buttons:", page.locator("button, fdsp-button, a[role='button']").evaluate_all(JS_BUTTONS))
        print("balance/account-like elements:", page.locator(BALANCE_LIKE).evaluate_all(JS_DESCRIBE))
        print("API calls with status >= 400:", dict(failures) or "none")
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "agent_com_s1")
