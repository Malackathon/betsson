"""Unit tests for config/settings.py.

Verifies:
- Default values and environment variable alias parsing.
- Secret masking in __repr__ and __str__ for Settings and Credentials.
- Credentials retrieval for valid and invalid agent IDs.
- Credential presence checks via has_credentials.
- Cached singleton behavior of get_settings().
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import (
    Credentials,
    Settings,
    get_credentials,
    get_settings,
    has_credentials,
)


def test_credentials_namedtuple_access_and_unpacking() -> None:
    """Credentials should support attribute access and tuple unpacking."""
    creds = Credentials(username="player1", password="super_secret_password")
    assert creds.username == "player1"
    assert creds.password == "super_secret_password"

    user, pwd = creds
    assert user == "player1"
    assert pwd == "super_secret_password"


def test_credentials_repr_and_str_mask_secret() -> None:
    """Credentials string representations must NEVER show the actual password."""
    creds = Credentials(username="player1", password="super_secret_password")
    assert "super_secret_password" not in repr(creds)
    assert "super_secret_password" not in str(creds)
    assert "***" in repr(creds)
    assert "player1" in repr(creds)


def test_credentials_empty_password_repr() -> None:
    """Credentials with empty password mask appropriately."""
    creds = Credentials(username="empty_user", password="")
    assert repr(creds) == "Credentials(username='empty_user', password='')"


def test_settings_default_values() -> None:
    """Settings should initialize with safe defaults."""
    s = Settings(
        _env_file=None,  # Do not load .env file for isolated test
        gemini_api_key="",
        betsson_com_s1_user="",
        betsson_com_s1_pass="",
        betsson_com_s2_user="",
        betsson_com_s2_pass="",
        betsson_pe_s1_user="",
        betsson_pe_s1_pass="",
        betsson_pe_s2_user="",
        betsson_pe_s2_pass="",
    )
    assert s.headless is True
    assert s.gemini_fast_model == "gemini-2.5-flash"
    assert s.gemini_pro_model == "gemini-2.5-pro"
    assert s.gemini_api_key == ""


def test_settings_alias_population() -> None:
    """Settings should accept environment variable aliases."""
    s = Settings(
        _env_file=None,
        GEMINI_API_KEY="test-key-123",
        BETSSON_COM_S1_USER="com_s1_user",
        BETSSON_COM_S1_PASS="com_s1_pass",
        HEADLESS=False,
        GEMINI_FAST_MODEL="gemini-custom-flash",
    )
    assert s.gemini_api_key == "test-key-123"
    assert s.betsson_com_s1_user == "com_s1_user"
    assert s.betsson_com_s1_pass == "com_s1_pass"
    assert s.headless is False
    assert s.gemini_fast_model == "gemini-custom-flash"


def test_settings_repr_and_str_mask_secrets() -> None:
    """Settings repr and str must NEVER reveal passwords or API keys."""
    s = Settings(
        _env_file=None,
        gemini_api_key="secret-gemini-key",
        betsson_com_s1_user="test_u1",
        betsson_com_s1_pass="secret_p1",
        betsson_com_s2_user="test_u2",
        betsson_com_s2_pass="secret_p2",
        betsson_pe_s1_user="test_u3",
        betsson_pe_s1_pass="secret_p3",
        betsson_pe_s2_user="test_u4",
        betsson_pe_s2_pass="secret_p4",
    )
    r = repr(s)
    text = str(s)

    # Sensitive values must NOT appear
    assert "secret-gemini-key" not in r
    assert "secret_p1" not in r
    assert "secret_p2" not in r
    assert "secret_p3" not in r
    assert "secret_p4" not in r

    assert "secret-gemini-key" not in text
    assert "secret_p1" not in text
    assert "secret_p2" not in text

    # Mask marker must appear for populated sensitive fields
    assert "gemini_api_key='***'" in r
    assert "betsson_com_s1_pass='***'" in r
    assert "test_u1" in r


def test_get_credentials_all_agents() -> None:
    """get_credentials should map all four agent IDs correctly."""
    s = Settings(
        _env_file=None,
        betsson_com_s1_user="u_com_1",
        betsson_com_s1_pass="p_com_1",
        betsson_com_s2_user="u_com_2",
        betsson_com_s2_pass="p_com_2",
        betsson_pe_s1_user="u_pe_1",
        betsson_pe_s1_pass="p_pe_1",
        betsson_pe_s2_user="u_pe_2",
        betsson_pe_s2_pass="p_pe_2",
    )

    c1 = s.get_credentials("agent_com_s1")
    assert c1.username == "u_com_1"
    assert c1.password == "p_com_1"

    c2 = s.get_credentials("agent_com_s2")
    assert c2.username == "u_com_2"
    assert c2.password == "p_com_2"

    c3 = s.get_credentials("agent_pe_s1")
    assert c3.username == "u_pe_1"
    assert c3.password == "p_pe_1"

    c4 = s.get_credentials("agent_pe_s2")
    assert c4.username == "u_pe_2"
    assert c4.password == "p_pe_2"


def test_get_credentials_case_insensitive_and_whitespace() -> None:
    """get_credentials should handle casing and surrounding whitespace."""
    s = Settings(
        _env_file=None,
        betsson_com_s1_user="u1",
        betsson_com_s1_pass="p1",
    )
    c = s.get_credentials("  AGENT_COM_S1  ")
    assert c.username == "u1"
    assert c.password == "p1"


def test_get_credentials_invalid_agent_raises_value_error() -> None:
    """get_credentials should raise ValueError without leaking secrets for invalid agent."""
    s = Settings(
        _env_file=None,
        betsson_com_s1_user="u1",
        betsson_com_s1_pass="super_secret",
    )
    with pytest.raises(ValueError) as exc_info:
        s.get_credentials("invalid_agent_name")

    err = str(exc_info.value)
    assert "invalid_agent_name" in err
    assert "Supported agents" in err
    assert "super_secret" not in err


def test_has_credentials() -> None:
    """has_credentials returns True only if both username and password are non-empty."""
    s = Settings(
        _env_file=None,
        betsson_com_s1_user="user1",
        betsson_com_s1_pass="pass1",
        betsson_com_s2_user="user2",
        betsson_com_s2_pass="",  # Empty pass
        betsson_pe_s1_user="   ",  # Whitespace only user
        betsson_pe_s1_pass="pass3",
        betsson_pe_s2_user="",
        betsson_pe_s2_pass="",
    )

    assert s.has_credentials("agent_com_s1") is True
    assert s.has_credentials("agent_com_s2") is False
    assert s.has_credentials("agent_pe_s1") is False
    assert s.has_credentials("agent_pe_s2") is False
    assert s.has_credentials("unknown_agent") is False


def test_get_settings_cached_singleton() -> None:
    """get_settings should return the same singleton instance across calls."""
    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_module_level_helpers() -> None:
    """Module-level helpers get_credentials and has_credentials should function."""
    # Unknown agent should raise ValueError on module-level get_credentials
    with pytest.raises(ValueError):
        get_credentials("unknown_agent_xyz")

    # Unknown agent should return False on module-level has_credentials
    assert has_credentials("unknown_agent_xyz") is False
