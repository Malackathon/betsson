"""Find the wallet balance in the Betsson header even when the configured selector is off.

The configured selector (``balance_display``) comes from the spike and may not match the live
site. When it does not appear, look in the header strip for a short element that looks like
money WITH a currency symbol, mark it, and return a locator for it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PROBE_ATTRIBUTE = "data-balance-probe"
HEADER_MAX_TOP_PX = 110
HEADER_MAX_HEIGHT_PX = 70
MAX_TEXT_LENGTH = 24

_PROBE_JS = """
([attr, maxTop, maxHeight, maxText]) => {
  const symbol = /€|S\\/|\\bEUR\\b|\\bPEN\\b/i;
  const money = /^\\s*(?:€|S\\/\\.?|EUR|PEN)?\\s*\\d{1,3}(?:[.,\\s]\\d{3})*(?:[.,]\\d{1,2})?\\s*(?:€|S\\/\\.?|EUR|PEN)?\\s*$/i;
  document.querySelectorAll('[' + attr + ']').forEach(e => e.removeAttribute(attr));
  const found = [...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect();
    if (!r.width || !r.height || r.top > maxTop || r.bottom < 0 || r.height > maxHeight) return false;
    const text = (e.innerText || '').trim();
    return text.length > 0 && text.length <= maxText && symbol.test(text) && money.test(text);
  });
  if (!found.length) return false;
  found.sort((a, b) => (a.innerText.length - b.innerText.length) ||
    (a.getBoundingClientRect().left - b.getBoundingClientRect().left));
  found[0].setAttribute(attr, '1');
  return true;
}
"""


_HEADER_TEXTS_JS = r"""
([maxTop, maxHeight, limit]) => [...document.querySelectorAll('body *')]
  .filter(e => { const r = e.getBoundingClientRect();
    return r.width && r.height && r.top <= maxTop && r.bottom >= 0 && r.height <= maxHeight; })
  .map(e => (e.innerText || '').trim().replace(/\s+/g, ' '))
  .filter(t => t && t.length <= 30 && /[0-9€]/.test(t) && !t.includes('@'))
  .filter((t, i, all) => all.indexOf(t) === i)
  .slice(0, limit)
"""


_HEADER_CONTROLS_JS = r"""
([maxTop, maxHeight, limit]) => [...document.querySelectorAll('button, a, [role="button"], fdsp-button, [aria-label]')]
  .filter(e => { const r = e.getBoundingClientRect();
    return r.width && r.height && r.top <= maxTop && r.bottom >= 0 && r.height <= maxHeight; })
  .map(e => ({
    tag: e.tagName.toLowerCase(),
    aria: e.getAttribute('aria-label'), title: e.getAttribute('title'), testid: e.getAttribute('data-testid'),
    text: (e.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 30)}))
  .filter(c => !JSON.stringify(c).includes('@') && (c.aria || c.title || c.testid || c.text))
  .slice(0, limit)
"""


def _header_controls_sample(page: Any, limit: int = 15) -> list[dict]:
    """Clickable header controls (labels only): the balance may sit behind one of them."""
    try:
        return page.evaluate(_HEADER_CONTROLS_JS, [HEADER_MAX_TOP_PX, HEADER_MAX_HEIGHT_PX, limit])
    except Exception:
        return []


def _header_text_sample(page: Any, limit: int = 12) -> list[str]:
    """Short header strings with digits/currency, e-mail-like ones excluded (privacy)."""
    try:
        return page.evaluate(_HEADER_TEXTS_JS, [HEADER_MAX_TOP_PX, HEADER_MAX_HEIGHT_PX, limit])
    except Exception:
        return []


def find_balance_locator(page: Any, configured_selector: str, timeout_ms: int = 15_000) -> Any:
    """Locator of the balance element: the configured one if visible, else a header heuristic.

    Raises ``LookupError`` when neither is found.
    """
    configured = page.locator(configured_selector).first
    try:
        configured.wait_for(state="visible", timeout=timeout_ms)
        return configured
    except Exception:
        logger.info("Configured balance selector not visible; probing the header for a money-like element")

    if page.evaluate(_PROBE_JS, [PROBE_ATTRIBUTE, HEADER_MAX_TOP_PX, HEADER_MAX_HEIGHT_PX, MAX_TEXT_LENGTH]):
        probed = page.locator(f"[{PROBE_ATTRIBUTE}='1']").first
        logger.info("Balance found by header probe (update 'balance_display' in config/markets.json)")
        return probed
    raise LookupError(
        "No balance element found: configured selector absent and no money-like element in the header. "
        f"Header strings with digits/currency: {_header_text_sample(page)}. "
        f"Header controls: {_header_controls_sample(page)}"
    )
