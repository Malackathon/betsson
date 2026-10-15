"""Configuration settings for Betsson Game Validation.

Manages application settings loaded from environment variables and .env file,
including Betsson credentials for all 4 test agents, Playwright options,
and Google Gemini API configuration.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, NamedTuple

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ensure .env located at project root is loaded into environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = PROJECT_ROOT / ".env"
if _ENV_FILE.is_file():
    load_dotenv(dotenv_path=_ENV_FILE, override=False)


class Credentials(NamedTuple):
    """Account credentials container for a Betsson agent.

    Attributes:
        username: The account username.
        password: The account secret password.
    """

    username: str
    password: str

    def __repr__(self) -> str:
        """Return safe string representation masking secret values."""
        masked_pwd = "***" if self.password else ""
        return f"Credentials(username={self.username!r}, password={masked_pwd!r})"

    def __str__(self) -> str:
        """Return safe string representation masking secret values."""
        return self.__repr__()


class Settings(BaseSettings):
    """Betsson Game Validation application configuration.

    Reads configuration from environment variables and project root .env file.
    Case-insensitive matching is supported for all environment variable names.
    Sensitive credentials are never exposed via string representation.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    gemini_api_key: str = Field(
        default="",
        alias="GEMINI_API_KEY",
        description="Google Gemini API key for multimodal validation.",
    )
    betsson_com_s1_user: str = Field(
        default="",
        alias="BETSSON_COM_S1_USER",
        description="Username for Betsson .com Scenario 1 (funded account).",
    )
    betsson_com_s1_pass: str = Field(
        default="",
        alias="BETSSON_COM_S1_PASS",
        description="Password for Betsson .com Scenario 1 (funded account).",
    )
    betsson_com_s2_user: str = Field(
        default="",
        alias="BETSSON_COM_S2_USER",
        description="Username for Betsson .com Scenario 2 (unfunded account).",
    )
    betsson_com_s2_pass: str = Field(
        default="",
        alias="BETSSON_COM_S2_PASS",
        description="Password for Betsson .com Scenario 2 (unfunded account).",
    )
    betsson_pe_s1_user: str = Field(
        default="",
        alias="BETSSON_PE_S1_USER",
        description="Username for Betsson .pe Scenario 1 (funded account).",
    )
    betsson_pe_s1_pass: str = Field(
        default="",
        alias="BETSSON_PE_S1_PASS",
        description="Password for Betsson .pe Scenario 1 (funded account).",
    )
    betsson_pe_s2_user: str = Field(
        default="",
        alias="BETSSON_PE_S2_USER",
        description="Username for Betsson .pe Scenario 2 (unfunded account).",
    )
    betsson_pe_s2_pass: str = Field(
        default="",
        alias="BETSSON_PE_S2_PASS",
        description="Password for Betsson .pe Scenario 2 (unfunded account).",
    )
    headless: bool = Field(
        default=True,
        alias="HEADLESS",
        description="Whether to run Playwright browser in headless mode.",
    )
    gemini_fast_model: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_FAST_MODEL",
        description="Gemini fast model name for quick vision/HUD checks.",
    )
    gemini_pro_model: str = Field(
        default="gemini-2.5-pro",
        alias="GEMINI_PRO_MODEL",
        description="Gemini pro model name for complex reasoning checks.",
    )

    def get_credentials(self, agent_id: Any) -> Credentials:
        """Retrieve credentials for the specified agent.

        Maps agent IDs to credential pairs:
            - 'agent_com_s1' -> COM_S1 user/pass
            - 'agent_com_s2' -> COM_S2 user/pass
            - 'agent_pe_s1' -> PE_S1 user/pass
            - 'agent_pe_s2' -> PE_S2 user/pass

        Args:
            agent_id: The identifier of the agent (string or Enum with .value).

        Returns:
            Credentials: A named tuple with the username and password.

        Raises:
            ValueError: If the agent_id is not recognized.
        """
        raw_id = agent_id.value if hasattr(agent_id, "value") else str(agent_id)
        normalized = raw_id.strip().lower()

        mapping: dict[str, tuple[str, str]] = {
            "agent_com_s1": (self.betsson_com_s1_user, self.betsson_com_s1_pass),
            "agent_com_s2": (self.betsson_com_s2_user, self.betsson_com_s2_pass),
            "agent_pe_s1": (self.betsson_pe_s1_user, self.betsson_pe_s1_pass),
            "agent_pe_s2": (self.betsson_pe_s2_user, self.betsson_pe_s2_pass),
        }

        if normalized not in mapping:
            supported = ", ".join(f"'{k}'" for k in sorted(mapping.keys()))
            raise ValueError(
                f"Unknown agent_id: {agent_id!r}. Supported agents are: {supported}"
            )

        user, pwd = mapping[normalized]
        return Credentials(username=user, password=pwd)

    def has_credentials(self, agent_id: Any) -> bool:
        """Check if both username and password are provided and non-empty for the agent.

        Args:
            agent_id: The identifier of the agent to check.

        Returns:
            bool: True if the agent is known and both username and password
                contain non-empty values; False otherwise.
        """
        try:
            creds = self.get_credentials(agent_id)
        except ValueError:
            return False
        return bool(
            creds.username
            and creds.password
            and creds.username.strip()
            and creds.password.strip()
        )

    def __repr__(self) -> str:
        """Return safe string representation masking sensitive values."""
        sensitive_fields = {
            "gemini_api_key",
            "betsson_com_s1_pass",
            "betsson_com_s2_pass",
            "betsson_pe_s1_pass",
            "betsson_pe_s2_pass",
        }
        parts: list[str] = []
        for field_name in self.__class__.model_fields:
            val = getattr(self, field_name)
            if field_name in sensitive_fields:
                display_val = "'***'" if val else "''"
            else:
                display_val = repr(val)
            parts.append(f"{field_name}={display_val}")
        return f"Settings({', '.join(parts)})"

    def __str__(self) -> str:
        """Return safe string representation masking sensitive values."""
        return self.__repr__()


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton instance of Settings.

    The instance is created once and subsequent calls return the cached object.
    Use `get_settings.cache_clear()` in tests if you need to reload configuration.

    Returns:
        Settings: The loaded application configuration.
    """
    return Settings()


def get_credentials(agent_id: Any) -> Credentials:
    """Retrieve credentials for the specified agent using cached settings.

    Args:
        agent_id: The identifier of the agent.

    Returns:
        Credentials: A named tuple with username and password.

    Raises:
        ValueError: If agent_id is not recognized.
    """
    return get_settings().get_credentials(agent_id)


def has_credentials(agent_id: Any) -> bool:
    """Check if credentials are configured for the specified agent.

    Args:
        agent_id: The identifier of the agent.

    Returns:
        bool: True if the agent is known and has non-empty credentials; False otherwise.
    """
    return get_settings().has_credentials(agent_id)
