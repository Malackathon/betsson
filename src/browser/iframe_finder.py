"""Locate the game iframe robustly, and describe the page when it cannot be found.

The configured selector may not match the live site (the provider host changes, the launcher
wraps the game in its own frame). Fallback: the largest visible iframe, searched through open
shadow roots too, ignoring tiny tracking frames.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

GAME_ATTRIBUTE = "data-game-iframe"
MIN_WIDTH_PX = 320
MIN_HEIGHT_PX = 180
POLL_INTERVAL_S = 0.5

_FIND_JS = r"""
([attr, minW, minH]) => {
  const all = [];
  const walk = (root) => { for (const e of root.querySelectorAll('*')) { all.push(e); if (e.shadowRoot) walk(e.shadowRoot); } };
  walk(document);
  all.forEach(e => e.removeAttribute && e.removeAttribute(attr));
  const frames = all.filter(e => e.tagName === 'IFRAME').map(e => ({e, r: e.getBoundingClientRect()}))
    .filter(x => x.r.width >= minW && x.r.height >= minH);
  if (!frames.length) return false;
  frames.sort((a, b) => b.r.width * b.r.height - a.r.width * a.r.height);
  frames[0].e.setAttribute(attr, '1');
  return true;
}
"""

_SNAPSHOT_JS = r"""
() => {
  const all = [];
  const walk = (root) => { for (const e of root.querySelectorAll('*')) { all.push(e); if (e.shadowRoot) walk(e.shadowRoot); } };
  walk(document);
  const visible = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const clean = t => (t || '').trim().replace(/\s+/g, ' ');
  const safe = t => t && !t.includes('@');
  const uniq = (a) => a.filter((t, i) => a.indexOf(t) === i);
  const iframes = all.filter(e => e.tagName === 'IFRAME' && visible(e)).map(e => {
    const r = e.getBoundingClientRect();
    return {src: e.getAttribute('src') || '', size: Math.round(r.width) + 'x' + Math.round(r.height)};
  });
  const dialogs = uniq(all.filter(e => visible(e) && (e.matches('[role="dialog"], [aria-modal="true"], dialog') ||
      /modal|overlay|popup|dialog/i.test(e.getAttribute('class') || '')))
    .map(e => clean(e.innerText).slice(0, 160)).filter(safe)).slice(0, 8);
  const buttons = uniq(all.filter(e => visible(e) && e.matches('button, a, [role="button"], fdsp-button'))
    .map(e => clean(e.innerText || e.getAttribute('aria-label')).slice(0, 30)).filter(t => t && safe(t))).slice(0, 30);
  return {iframes, dialogs, buttons};
}
"""


def find_game_iframe(page: Any, configured_selector: str, timeout_ms: int = 30_000) -> Any:
    """Locator of the game iframe: the configured one, else the largest visible iframe.

    Raises ``LookupError`` when neither shows up within ``timeout_ms``.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    configured = page.locator(configured_selector).first
    while True:
        try:
            if configured.count() and configured.is_visible():
                return configured
        except Exception:
            pass
        if page.evaluate(_FIND_JS, [GAME_ATTRIBUTE, MIN_WIDTH_PX, MIN_HEIGHT_PX]):
            logger.info("Game iframe found by size (configured selector did not match)")
            return page.locator(f"iframe[{GAME_ATTRIBUTE}='1']").first
        if time.monotonic() >= deadline:
            raise LookupError("No game iframe found (configured selector absent, no large visible iframe)")
        page.wait_for_timeout(int(POLL_INTERVAL_S * 1000))


def page_snapshot(page: Any) -> dict:
    """What is on screen: iframes (host/path + size), dialog texts and button labels. No secrets."""
    try:
        data = page.evaluate(_SNAPSHOT_JS)
    except Exception as exc:  # page closed or navigating
        return {"error": str(exc)[:120], "iframes": [], "dialogs": [], "buttons": []}
    for frame in data["iframes"]:
        parts = urlsplit(frame["src"])
        frame["src"] = f"{parts.netloc}{parts.path}" if parts.netloc else (parts.path or "(no src)")
    url = urlsplit(page.url)
    data["page"] = f"{url.netloc}{url.path}"
    return data
