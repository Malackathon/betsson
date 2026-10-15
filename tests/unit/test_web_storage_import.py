import json

import pytest

from src.browser.cookie_import import (
    WebStorage,
    add_local_storage,
    build_session_storage_script,
    load_web_storage_file,
)
from src.browser.session_state import session_storage_sidecar

ORIGIN = "https://www.betsson.es"


def _export(**overrides) -> dict:
    base = {
        "origin": ORIGIN,
        "localStorage": {"obg-token": "t1", "lang": "es"},
        "sessionStorage": {"tab-session": "s1"},
    }
    base.update(overrides)
    return base


def _write(tmp_path, payload) -> str:
    path = tmp_path / "storage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_web_storage_file_reads_origin_and_both_stores(tmp_path):
    ws = load_web_storage_file(_write(tmp_path, _export()))
    assert ws.origin == ORIGIN
    assert ws.local == {"obg-token": "t1", "lang": "es"}
    assert ws.session == {"tab-session": "s1"}


def test_bot_check_keys_are_dropped_from_both_stores(tmp_path):
    payload = _export(
        localStorage={"aws-waf-token": "x", "cfidsgib-w": "y", "obg-token": "t1"},
        sessionStorage={"awswaf-session": "z", "tab-session": "s1"},
    )
    ws = load_web_storage_file(_write(tmp_path, payload))
    assert ws.local == {"obg-token": "t1"}
    assert ws.session == {"tab-session": "s1"}


def test_non_betsson_origin_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_web_storage_file(_write(tmp_path, _export(origin="https://example.com")))


def test_missing_origin_is_rejected(tmp_path):
    payload = _export()
    del payload["origin"]
    with pytest.raises(ValueError):
        load_web_storage_file(_write(tmp_path, payload))


def test_add_local_storage_adds_an_origin_entry_without_mutating_the_input():
    state = {"cookies": [], "origins": []}
    updated = add_local_storage(state, WebStorage(ORIGIN, {"k": "v"}, {}))

    assert updated["origins"] == [{"origin": ORIGIN, "localStorage": [{"name": "k", "value": "v"}]}]
    assert state["origins"] == []


def test_session_storage_script_is_origin_guarded_and_escapes_values():
    script = build_session_storage_script(WebStorage(ORIGIN, {}, {"k": 'va"l</script>'}))

    assert f"location.origin !== {json.dumps(ORIGIN)}" in script
    assert "sessionStorage.setItem" in script
    assert 'va\\"l' in script


def test_session_storage_sidecar_sits_next_to_the_auth_state(tmp_path):
    path = tmp_path / "auth_state_agent_x.json"
    assert session_storage_sidecar(path) == tmp_path / "auth_state_agent_x.session.json"
