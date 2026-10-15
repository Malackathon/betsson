"""Reusable authenticated session (saved by a human with scripts/save_session.py).

The session file holds cookies and storage of a logged-in account: it lives under
``artifacts/auth_state/`` (gitignored), is never uploaded, and expires after a few hours.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

AUTH_STATE_DIR_NAME = "auth_state"
DEFAULT_MAX_AGE_S = 4 * 3600


def saved_session_path(artifacts_dir: Path, agent_id: str) -> Path:
    """Same location GameFlow/LobbyPage use: ``<artifacts>/auth_state/auth_state_<agent>.json``."""
    return Path(artifacts_dir).parent / AUTH_STATE_DIR_NAME / f"auth_state_{agent_id}.json"


def find_reusable_session(
    artifacts_dir: Path,
    agent_id: str,
    max_age_s: float | None = None,
) -> Path | None:
    """The saved session if it exists, is recent enough and reuse is not disabled."""
    if os.getenv("REUSE_SAVED_SESSION", "true").strip().lower() == "false":
        return None
    path = saved_session_path(artifacts_dir, agent_id)
    if not path.is_file():
        return None
    limit = max_age_s if max_age_s is not None else float(os.getenv("SAVED_SESSION_MAX_AGE_S", DEFAULT_MAX_AGE_S))
    return path if time.time() - path.stat().st_mtime <= limit else None


def session_storage_sidecar(auth_state_path: Path) -> Path:
    """File next to the auth state holding the sessionStorage items to restore."""
    return auth_state_path.with_suffix(".session.json")


def apply_session_storage(context, auth_state_path: Path) -> bool:
    """Restore the saved sessionStorage into a Playwright context. True when something was applied."""
    from src.browser.cookie_import import WebStorage, build_session_storage_script

    sidecar = session_storage_sidecar(auth_state_path)
    if not sidecar.is_file():
        return False
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    web = WebStorage(origin=data["origin"], local={}, session=data.get("session", {}))
    if not web.session:
        return False
    context.add_init_script(build_session_storage_script(web))
    return True


LOGIN_COOKIE_HINT = "auth"


def expired_login_cookies(auth_state_path: Path, now: float | None = None) -> list[tuple[str, int]]:
    """Login-looking cookies (name contains 'auth') whose expiry date has passed: (name, minutes ago)."""
    try:
        cookies = json.loads(Path(auth_state_path).read_text(encoding="utf-8")).get("cookies", [])
    except (OSError, ValueError):
        return []
    moment = time.time() if now is None else now
    expired = []
    for cookie in cookies:
        expires = cookie.get("expires", -1)
        if LOGIN_COOKIE_HINT in str(cookie.get("name", "")).lower() and expires and expires > 0 and expires < moment:
            expired.append((cookie["name"], int((moment - expires) // 60)))
    return expired
