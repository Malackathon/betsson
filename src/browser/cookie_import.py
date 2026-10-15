"""Turn a cookie export from a normal browser into a Playwright storage state.

The cookies are the account's session credentials: handle the exported file like a password
(never commit or share it). Only Betsson-domain cookies are kept.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SAME_SITE = {"no_restriction": "None", "none": "None", "lax": "Lax", "strict": "Strict"}
KEPT_DOMAIN_FRAGMENT = "betsson"
SESSION_COOKIE_EXPIRES = -1
# Proofs that a browser passed the site's bot checks (AWS WAF / Group-IB). They belong to the
# human's browser: replaying them in an automated one would bypass bot detection, so they are
# never imported. Only the account's login session is carried over.
BOT_CHECK_COOKIE_PREFIXES = ("aws-waf-token", "cfid", "awswaf")


def cookies_to_storage_state(
    cookies: Iterable[dict[str, Any]],
    domain_fragment: str = KEPT_DOMAIN_FRAGMENT,
) -> dict[str, Any]:
    """Playwright ``storage_state`` dict from Cookie-Editor / EditThisCookie / Playwright cookies."""
    converted = [
        c
        for c in (_convert(raw) for raw in cookies)
        if c and domain_fragment in c["domain"] and not _is_bot_check_cookie(c["name"])
    ]
    return {"cookies": converted, "origins": []}


def _is_bot_check_cookie(name: str) -> bool:
    return name.lower().startswith(BOT_CHECK_COOKIE_PREFIXES)


def _convert(raw: dict[str, Any]) -> dict[str, Any] | None:
    name, domain = raw.get("name"), raw.get("domain")
    if not name or not domain:
        return None
    expires = raw.get("expirationDate", raw.get("expires", SESSION_COOKIE_EXPIRES))
    return {
        "name": name,
        "value": str(raw.get("value", "")),
        "domain": domain,
        "path": raw.get("path") or "/",
        "expires": expires if expires is not None else SESSION_COOKIE_EXPIRES,
        "httpOnly": bool(raw.get("httpOnly", False)),
        "secure": bool(raw.get("secure", False)),
        "sameSite": SAME_SITE.get(str(raw.get("sameSite") or "").lower(), "Lax"),
    }


def load_cookie_file(path: Path | str) -> dict[str, Any]:
    """Read a JSON export (a bare cookie list, or an object with a ``cookies`` list)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cookies = data if isinstance(data, list) else data.get("cookies") if isinstance(data, dict) else None
    if not isinstance(cookies, list):
        raise ValueError("Expected a JSON list of cookies or an object with a 'cookies' list")
    return cookies_to_storage_state(cookies)


@dataclass(frozen=True)
class WebStorage:
    """localStorage / sessionStorage of the logged-in origin (token holders in many SPAs)."""

    origin: str
    local: dict[str, str]
    session: dict[str, str]


def load_web_storage_file(path: Path | str, domain_fragment: str = KEPT_DOMAIN_FRAGMENT) -> WebStorage:
    """Read ``{"origin", "localStorage", "sessionStorage"}`` exported from the browser console."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    origin = data.get("origin") if isinstance(data, dict) else None
    if not origin or domain_fragment not in origin:
        raise ValueError(f"Expected a Betsson 'origin' in the storage export, got {origin!r}")
    return WebStorage(
        origin=origin,
        local=_clean_items(data.get("localStorage")),
        session=_clean_items(data.get("sessionStorage")),
    )


def _clean_items(items: Any) -> dict[str, str]:
    if not isinstance(items, dict):
        return {}
    return {str(k): str(v) for k, v in items.items() if not _is_bot_check_cookie(str(k))}


def add_local_storage(state: dict[str, Any], web: WebStorage) -> dict[str, Any]:
    """New storage_state with the origin's localStorage added (the input is not modified)."""
    entry = {"origin": web.origin, "localStorage": [{"name": k, "value": v} for k, v in web.local.items()]}
    return {**state, "origins": [*state.get("origins", []), entry]}


def build_session_storage_script(web: WebStorage) -> str:
    """Init script restoring sessionStorage (Playwright's storage_state does not cover it)."""
    return (
        "(() => {"
        f" if (location.origin !== {json.dumps(web.origin)}) return;"
        f" const items = {json.dumps(web.session)};"
        " for (const [k, v] of Object.entries(items)) {"
        " if (sessionStorage.getItem(k) === null) sessionStorage.setItem(k, v); }"
        " })();"
    )
