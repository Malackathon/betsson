"""Network interception: read the game's own server traffic as mathematical ground truth.

Exports:
    - ``NetworkMonitor``: attaches to a Playwright page and tracks game transactions.
    - ``SpinAttempt``, ``RoundResult``, ``GameTransaction`` and the enums.
"""

from src.network.models import (
    GameTransaction,
    RoundResult,
    SpinAttempt,
    SpinAttemptStatus,
    TxKind,
)
from src.network.monitor import NetworkMonitor
from src.network.parser import DEFAULT_FIELDS, FieldMap

__all__ = [
    "DEFAULT_FIELDS",
    "FieldMap",
    "GameTransaction",
    "NetworkMonitor",
    "RoundResult",
    "SpinAttempt",
    "SpinAttemptStatus",
    "TxKind",
]
