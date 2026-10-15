"""Immutable data models for game-server traffic observed through Playwright."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Mapping


class TxKind(StrEnum):
    INIT = "init"
    SPIN = "spin"
    COLLECT = "collect"
    BONUS = "bonus"
    BALANCE = "balance"
    OTHER = "other"


class SpinAttemptStatus(StrEnum):
    SETTLED = "settled"  # round finished and the server is ready for the next spin
    PENDING = "pending"  # spin answered but the round is not settled yet
    REJECTED = "rejected"  # the server (or HTTP layer) refused the spin
    NO_TRAFFIC = "no_traffic"  # no spin request reached the server


@dataclass(frozen=True)
class GameTransaction:
    """One request/response exchange with the game server (secrets already excluded)."""

    seq: int
    kind: TxKind
    url: str
    http_status: int | None
    request: Mapping[str, str]
    response: Mapping[str, str]
    balance: Decimal | None = None
    total_win: Decimal | None = None
    win: Decimal | None = None
    bet: Decimal | None = None
    next_action: str | None = None
    error: str | None = None
    bonus: bool = False


@dataclass(frozen=True)
class RoundResult:
    """Server-side truth of a settled spin round."""

    balance_before: Decimal | None
    balance_after: Decimal | None
    bet: Decimal | None
    total_win: Decimal | None
    bonus_triggered: bool
    server_reconciles: bool | None
    transactions: tuple[GameTransaction, ...] = field(default_factory=tuple)

    @property
    def is_complete(self) -> bool:
        """All four numbers the reconciliation formula needs are known."""
        return None not in (self.balance_before, self.balance_after, self.bet, self.total_win)


@dataclass(frozen=True)
class SpinAttempt:
    status: SpinAttemptStatus
    round: RoundResult | None = None
    error: str | None = None
    detail: str = ""
