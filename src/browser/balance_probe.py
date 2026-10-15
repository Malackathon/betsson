"""Find the wallet balance in the Betsson header even when the configured selector is off.

The configured selector (``balance_display``) comes from the spike and may not match the live
site. When it does not appear, look in the header strip for a short element that looks like
money WITH a currency symbol, mark it, and return a locator for it.

Betsson renders its header with web components (shadow DOM), which ``document.querySelectorAll``
cannot see, so every script below walks open shadow roots recursively.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PROBE_ATTRIBUTE = "data-balance-probe"
HEADER_MAX_TOP_PX = 110
HEADER_MAX_HEIGHT_PX = 70
MAX_TEXT_LENGTH = 24

# Shared JS helpers: every element of the document, including those inside open shadow roots.
_ALL_ELEMENTS_JS = r"""
const allElements = () => {
  const out = [];
  const walk = (root) => {
    for (const e of root.querySelectorAll('*')) {
      out.push(e);
      if (e.shadowRoot) walk(e.shadowRoot);
    }
  };
  walk(document);
  return out;
};
const inHeader = (e, maxTop, maxHeight) => {
  const r = e.getBoundingClientRect();
  return r.width && r.height && r.top <= maxTop && r.bottom >= 0 && r.height <= maxHeight;
};
"""

_PROBE_JS = (
    "([attr, maxTop, maxHeight, maxText]) => {"
    + _ALL_ELEMENTS_JS
    + r"""
  const symbol = /€|S\/|\bEUR\b|\bPEN\b/i;
  const money = /^\s*(?:€|S\/\.?|EUR|PEN)?\s*\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})?\s*(?:€|S\/\.?|EUR|PEN)?\s*$/i;
  const all = allElements();
  all.forEach(e => e.removeAttribute(attr));
  const found = all.filter(e => {
    if (!inHeader(e, maxTop, maxHeight)) return false;
    const text = (e.innerText || '').trim();
    return text.length > 0 && text.length <= maxText && symbol.test(text) && money.test(text);
  });
  if (!found.length) return false;
  found.sort((a, b) => (a.innerText.length - b.innerText.length) ||
    (a.getBoundingClientRect().left - b.getBoundingClientRect().left));
  found[0].setAttribute(attr, '1');
  return true;
}"""
)

_HEADER_TEXTS_JS = (
    "([maxTop, maxHeight, limit]) => {"
    + _ALL_ELEMENTS_JS
    + r"""
  return allElements()
    .filter(e => inHeader(e, maxTop, maxHeight))
    .map(e => (e.innerText || '').trim().replace(/\s+/g, ' '))
    .filter(t => t && t.length <= 30 && /[0-9€]/.test(t) && !t.includes('@'))
    .filter((t, i, all) => all.indexOf(t) === i)
    .slice(0, limit);
}"""
)

_HEADER_CONTROLS_JS = (
    "([maxTop, maxHeight, limit]) => {"
    + _ALL_ELEMENTS_JS
    + r"""
  return allElements()
    .filter(e => e.matches('button, a, [role="button"], fdsp-button, [aria-label]') && inHeader(e, maxTop, maxHeight))
    .map(e => ({
      tag: e.tagName.toLowerCase(),
      aria: e.getAttribute('aria-label'), title: e.getAttribute('title'), testid: e.getAttribute('data-testid'),
      text: (e.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 30)}))
    .filter(c => !JSON.stringify(c).includes('@') && (c.aria || c.title || c.testid || c.text))
    .slice(0, limit);
}"""
)


def _evaluate_list(page: Any, script: str, limit: int) -> list:
    try:
        return page.evaluate(script, [HEADER_MAX_TOP_PX, HEADER_MAX_HEIGHT_PX, limit])
    except Exception:
        return []


def _header_controls_sample(page: Any, limit: int = 15) -> list[dict]:
    """Clickable header controls (labels only): the balance may sit behind one of them."""
    return _evaluate_list(page, _HEADER_CONTROLS_JS, limit)


def _header_text_sample(page: Any, limit: int = 12) -> list[str]:
    """Short header strings with digits/currency, e-mail-like ones excluded (privacy)."""
    return _evaluate_list(page, _HEADER_TEXTS_JS, limit)


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
