"""Make the bot watchable: visible cursor and click ripples, optional slow motion and end pause.

Environment (only applies when the browser is visible, i.e. HEADLESS=false):
    SLOW_MO_MS     delay in ms added to every Playwright action (e.g. 400)
    SHOW_CURSOR    "false" to hide the red cursor/click ripple (default: shown)
    KEEP_OPEN_S    seconds to keep the window open at the end/failure so you can look at it
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

CURSOR_SCRIPT = """
(() => {
  if (window.__botCursor) return;
  window.__botCursor = true;
  const install = () => {
    const dot = document.createElement('div');
    dot.style.cssText = 'position:fixed;z-index:2147483647;width:18px;height:18px;border-radius:50%;' +
      'background:rgba(255,0,0,.75);border:2px solid #fff;pointer-events:none;left:-50px;top:-50px;' +
      'transform:translate(-50%,-50%)';
    document.documentElement.appendChild(dot);
    addEventListener('mousemove', e => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', e => {
      const ring = document.createElement('div');
      ring.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;border-radius:50%;' +
        'border:3px solid red;width:10px;height:10px;transform:translate(-50%,-50%);transition:all .5s;' +
        'left:' + e.clientX + 'px;top:' + e.clientY + 'px;opacity:1';
      document.documentElement.appendChild(ring);
      requestAnimationFrame(() => { ring.style.width = '70px'; ring.style.height = '70px'; ring.style.opacity = '0'; });
      setTimeout(() => ring.remove(), 600);
    }, true);
  };
  if (document.documentElement) install(); else addEventListener('DOMContentLoaded', install);
})();
"""


@dataclass(frozen=True)
class VisualSettings:
    slow_mo_ms: int
    show_cursor: bool
    keep_open_s: int


def _non_negative_int(raw: str | None) -> int:
    try:
        return max(int(raw or 0), 0)
    except ValueError:
        return 0


def read_visual_settings(env: Mapping[str, str], headless: bool) -> VisualSettings:
    """Visual options from the environment; everything is off when running headless."""
    if headless:
        return VisualSettings(slow_mo_ms=0, show_cursor=False, keep_open_s=0)
    return VisualSettings(
        slow_mo_ms=_non_negative_int(env.get("SLOW_MO_MS")),
        show_cursor=env.get("SHOW_CURSOR", "true").strip().lower() != "false",
        keep_open_s=_non_negative_int(env.get("KEEP_OPEN_S")),
    )
