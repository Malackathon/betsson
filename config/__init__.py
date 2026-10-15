"""Configuration package for Betsson Game Validation.

Exports Settings, Credentials, and configuration helpers.
"""

from __future__ import annotations

from config.settings import (
    Credentials,
    Settings,
    get_credentials,
    get_settings,
    has_credentials,
)

__all__ = [
    "Credentials",
    "Settings",
    "get_credentials",
    "get_settings",
    "has_credentials",
]
