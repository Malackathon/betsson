"""Import the cookies of a session YOU opened in your normal browser.

Usage:  python scripts/import_cookies.py agent_com_s1 path/to/cookies.json

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

from src.browser.cookie_import import load_cookie_file  # noqa: E402
from src.browser.session_state import saved_session_path  # noqa: E402


def main(agent_id: str, cookie_file: str) -> None:
    state = load_cookie_file(cookie_file)
    if not state["cookies"]:
        sys.exit("No Betsson cookies found in that file (export while on betsson.es).")
    target = saved_session_path(Path("artifacts") / agent_id, agent_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state), encoding="utf-8")
    names = sorted({c["domain"] for c in state["cookies"]})
    print(f"Imported {len(state['cookies'])} cookies for domains {names} -> {target}")
    print("Now delete the exported file, then run:")
    print('  python -m pytest tests/test_scenario_1_spin.py -k com_s1 -o addopts=""')


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python scripts/import_cookies.py <agent_id> <cookies.json>")
    main(sys.argv[1], sys.argv[2])
