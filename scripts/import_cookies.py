"""Import the cookies of a session YOU opened in your normal browser.

Usage:  python scripts/import_cookies.py agent_com_s1 cookies.json [storage.json]

storage.json (optional but usually REQUIRED for SPAs): the origin's localStorage/sessionStorage,
where the login token often lives. In the logged-in tab open DevTools > Console and run:
    copy(JSON.stringify({origin: location.origin, localStorage: {...localStorage}, sessionStorage: {...sessionStorage}}))
then paste the clipboard into storage.json (repo root, gitignored). Treat it like a password.

How to export (in the browser where you are logged in to the test account):
  - Install a cookie manager extension (e.g. Cookie-Editor), open betsson.es, Export -> JSON,
    save the file OUTSIDE the repository.
Then run this script. It converts the file to artifacts/auth_state/auth_state_<agent>.json
(gitignored, expires in 4h in the flow) and prints only cookie COUNTS, never values.
Afterwards DELETE the exported file: it is equivalent to your session password.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.browser.cookie_import import add_local_storage, load_cookie_file, load_web_storage_file  # noqa: E402
from src.browser.session_state import saved_session_path, session_storage_sidecar  # noqa: E402


def main(agent_id: str, cookie_file: str, storage_file: str | None = None) -> None:
    state = load_cookie_file(cookie_file)
    if not state["cookies"]:
        sys.exit("No Betsson cookies found in that file (export while on betsson.es).")
    target = saved_session_path(Path("artifacts") / agent_id, agent_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    sidecar = session_storage_sidecar(target)
    sidecar.unlink(missing_ok=True)
    if storage_file:
        web = load_web_storage_file(storage_file)
        state = add_local_storage(state, web)
        if web.session:
            sidecar.write_text(json.dumps({"origin": web.origin, "session": web.session}), encoding="utf-8")
        print(f"Web storage: {len(web.local)} localStorage and {len(web.session)} sessionStorage keys imported")
    target.write_text(json.dumps(state), encoding="utf-8")
    names = sorted({c["domain"] for c in state["cookies"]})
    print(f"Imported {len(state['cookies'])} cookies for domains {names} -> {target}")
    print("Now delete the exported file, then run:")
    print('  python -m pytest tests/test_scenario_1_spin.py -k com_s1 -o addopts=""')


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit("Usage: python scripts/import_cookies.py <agent_id> <cookies.json> [storage.json]")
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
