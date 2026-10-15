import json

import pytest

from src.browser.cookie_import import cookies_to_storage_state, load_cookie_file


def _export(**overrides) -> dict:
    base = {
        "name": "sid",
        "value": "abc",
        "domain": ".betsson.es",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "no_restriction",
        "expirationDate": 1893456000.5,
    }
    base.update(overrides)
    return base


def test_converts_a_cookie_editor_export_to_playwright_format():
    state = cookies_to_storage_state([_export()])

    assert state["origins"] == []
    assert state["cookies"] == [
        {
            "name": "sid",
            "value": "abc",
            "domain": ".betsson.es",
            "path": "/",
            "expires": 1893456000.5,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None",
        }
    ]


@pytest.mark.parametrize(
    "raw, expected",
    [("lax", "Lax"), ("strict", "Strict"), ("unspecified", "Lax"), (None, "Lax"), ("no_restriction", "None")],
)
def test_same_site_values_are_normalised(raw, expected):
    cookie = _export(sameSite=raw)
    assert cookies_to_storage_state([cookie])["cookies"][0]["sameSite"] == expected


def test_session_cookies_get_no_expiry():
    cookie = _export()
    del cookie["expirationDate"]
    assert cookies_to_storage_state([cookie])["cookies"][0]["expires"] == -1


def test_playwright_style_expires_is_accepted():
    cookie = _export(expires=1700000000)
    del cookie["expirationDate"]
    assert cookies_to_storage_state([cookie])["cookies"][0]["expires"] == 1700000000


def test_cookies_without_name_or_domain_are_skipped():
    state = cookies_to_storage_state([_export(name=""), _export(domain=""), _export()])
    assert len(state["cookies"]) == 1


def test_non_betsson_cookies_are_dropped_by_default():
    state = cookies_to_storage_state([_export(domain=".google.com"), _export()])
    assert [c["domain"] for c in state["cookies"]] == [".betsson.es"]


@pytest.mark.parametrize("name", ["aws-waf-token", "cfidsgib-w-betssones", "AWSWAF-token"])
def test_bot_check_cookies_are_never_imported(name):
    state = cookies_to_storage_state([_export(name=name), _export(name="gamewebauth")])
    assert [c["name"] for c in state["cookies"]] == ["gamewebauth"]


def test_load_cookie_file_accepts_a_bare_list_or_a_storage_state(tmp_path):
    bare = tmp_path / "a.json"
    bare.write_text(json.dumps([_export()]), encoding="utf-8")
    wrapped = tmp_path / "b.json"
    wrapped.write_text(json.dumps({"cookies": [_export()]}), encoding="utf-8")

    assert len(load_cookie_file(bare)["cookies"]) == 1
    assert len(load_cookie_file(wrapped)["cookies"]) == 1


def test_load_cookie_file_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"nope": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_cookie_file(bad)
