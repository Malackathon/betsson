"""Save a session that a HUMAN logged into, so the automation can reuse it.

Usage:  python scripts/save_session.py agent_com_s1

1. A visible browser opens on the market's site.
2. YOU log in with the matching test account (type the credentials yourself, solve anything
   the site asks) and make sure the header shows the balance.
3. Back in this terminal press Enter: the cookies/storage are saved to
   artifacts/auth_state/auth_state_<agent>.json (gitignored, never uploaded, expires in 4h).

This script never reads or prints credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from src.browser.game_canvas import DEFAULT_VIEWPORT  # noqa: E402
from src.browser.selectors import get_market_selectors  # noqa: E402
from src.browser.session_state import saved_session_path  # noqa: E402

BALANCE_LIKE = (
    "[data-testid*='balance' i], [class*='balance' i], [id*='balance' i], "
    "[data-testid*='wallet' i], [class*='wallet' i], [class*='saldo' i]"
)
JS_DESCRIBE = """els => els.filter(e => e.offsetWidth || e.offsetHeight).slice(0, 10).map(e => ({
  tag: e.tagName.toLowerCase(), testid: e.getAttribute('data-testid'),
  cls: (e.getAttribute('class') || '').slice(0, 70), text: (e.innerText || '').trim().slice(0, 30)}))"""


def main(agent_id: str) -> None:
    _, market, _scenario = agent_id.split("_")
    mkt = get_market_selectors(market)
    target = saved_session_path(Path("artifacts") / agent_id, agent_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    browser_name = (os.getenv("PLAYWRIGHT_BROWSER") or "chromium").lower()

    with sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=False)
        context = browser.new_context(viewport=DEFAULT_VIEWPORT, locale=mkt.locale)
        page = context.new_page()
        page.goto(mkt.url, timeout=60_000)
        print(f"\nBrowser open on {mkt.url} ({browser_name}).")
        print(f"Log in YOURSELF with the account for {agent_id} and wait until you see the balance.")
        input("When you are logged in, press Enter here to save the session... ")

        configured = page.locator(mkt.selectors.balance_display).first
        print("configured balance selector visible:", configured.is_visible())
        print("balance-like elements:", page.locator(BALANCE_LIKE).evaluate_all(JS_DESCRIBE))
        context.storage_state(path=str(target))
        browser.close()
    print(f"\nSession saved to {target} (gitignored). Now run the scenario, for example:")
    print('  python -m pytest tests/test_scenario_1_spin.py -k com_s1 -o addopts=""')


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "agent_com_s1")
