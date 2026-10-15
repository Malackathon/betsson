"""Reusable authenticated session (saved by a human with scripts/save_session.py).

The session file holds cookies and storage of a logged-in account: it lives under
``artifacts/auth_state/`` (gitignored), is never uploaded, and expires after a few hours.
"""

from __future__ import annotations

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
