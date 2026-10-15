import os
import time
from pathlib import Path

from src.browser.session_state import (
    DEFAULT_MAX_AGE_S,
    find_reusable_session,
    saved_session_path,
)


def test_saved_session_path_matches_gameflow_auth_dir(tmp_path):
    artifacts_dir = tmp_path / "artifacts" / "agent_com_s1"
    path = saved_session_path(artifacts_dir, "agent_com_s1")
    assert path == tmp_path / "artifacts" / "auth_state" / "auth_state_agent_com_s1.json"


def test_missing_session_is_not_reusable(tmp_path):
    assert find_reusable_session(tmp_path / "a" / "agent_x", "agent_x") is None


def test_fresh_session_is_reusable(tmp_path):
    artifacts_dir = tmp_path / "artifacts" / "agent_x"
    path = saved_session_path(artifacts_dir, "agent_x")
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    assert find_reusable_session(artifacts_dir, "agent_x") == path


def test_stale_session_is_ignored(tmp_path):
    artifacts_dir = tmp_path / "artifacts" / "agent_x"
    path = saved_session_path(artifacts_dir, "agent_x")
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    old = time.time() - DEFAULT_MAX_AGE_S - 60
    os.utime(path, (old, old))

    assert find_reusable_session(artifacts_dir, "agent_x") is None


def test_max_age_can_be_overridden(tmp_path):
    artifacts_dir = tmp_path / "artifacts" / "agent_x"
    path = saved_session_path(artifacts_dir, "agent_x")
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    old = time.time() - 600
    os.utime(path, (old, old))

    assert find_reusable_session(artifacts_dir, "agent_x", max_age_s=300) is None
    assert find_reusable_session(artifacts_dir, "agent_x", max_age_s=3600) == path


def test_reuse_can_be_disabled_with_env(tmp_path, monkeypatch):
    artifacts_dir = tmp_path / "artifacts" / "agent_x"
    path = saved_session_path(artifacts_dir, "agent_x")
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("REUSE_SAVED_SESSION", "false")

    assert find_reusable_session(artifacts_dir, "agent_x") is None
