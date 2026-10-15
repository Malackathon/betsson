"""Is the saved session still usable? Prints cookie NAMES and time left, never values.

Usage:  python scripts/check_session.py agent_com_s1
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.browser.session_state import DEFAULT_MAX_AGE_S, saved_session_path, session_storage_sidecar  # noqa: E402


def main(agent_id: str) -> None:
    path = saved_session_path(Path("artifacts") / agent_id, agent_id)
    if not path.is_file():
        sys.exit(f"No saved session at {path}. Run scripts/import_cookies.py first.")
    age_min = (time.time() - path.stat().st_mtime) / 60
    state = json.loads(path.read_text(encoding="utf-8"))
    now = time.time()
    print(f"file: {path}  (imported {age_min:.0f} min ago; the flow ignores it after {DEFAULT_MAX_AGE_S // 60} min)")
    expired = 0
    for cookie in sorted(state.get("cookies", []), key=lambda c: c.get("expires", -1)):
        exp = cookie.get("expires", -1)
        if exp is None or exp < 0:
            left = "session cookie"
        else:
            minutes = (exp - now) / 60
            left = f"EXPIRED {-minutes:.0f} min ago" if minutes < 0 else f"{minutes:.0f} min left"
            expired += minutes < 0
            left += f" (until {datetime.fromtimestamp(exp, timezone.utc):%H:%M} UTC)"
        print(f"  cookie {cookie['name']:<28} {cookie['domain']:<18} {left}")
    local = sum(len(o.get("localStorage", [])) for o in state.get("origins", []))
    sidecar = session_storage_sidecar(path)
    session_keys = len(json.loads(sidecar.read_text(encoding="utf-8")).get("session", {})) if sidecar.is_file() else 0
    print(f"localStorage keys: {local} | sessionStorage keys: {session_keys}")
    print("VERDICT:", "some cookies already expired -> export a fresh session" if expired else "no cookie expired by date")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "agent_com_s1")
