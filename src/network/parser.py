"""Pure parsing of Pragmatic Play ``gameService`` style payloads.

Responses are ``&``-separated ``key=value`` text (sometimes JSON). The key names
live in :class:`FieldMap` so they can be corrected after calibrating against live
traffic without touching the logic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping
from urllib.parse import parse_qsl, urlsplit

from src.network.models import GameTransaction, TxKind

REDACTED = "<redacted>"
_SENSITIVE_KEY = re.compile(r"(key|token|session|auth|cookie|pass|user|player|mgc|secret|jwt|login)", re.I)

_ACTION_KINDS: dict[str, TxKind] = {
    "doinit": TxKind.INIT,
    "dospin": TxKind.SPIN,
    "docollect": TxKind.COLLECT,
}
_BONUS_ACTION_PREFIXES = ("dobonus", "docollectbonus", "dofs", "domystery")
_URL_KINDS: tuple[tuple[str, TxKind], ...] = (
    ("/spin", TxKind.SPIN),
    ("/balance", TxKind.BALANCE),
    ("/init", TxKind.INIT),
)


@dataclass(frozen=True)
class FieldMap:
    """Names of the interesting keys in the game server payload."""

    balance: str = "balance"
    total_win: str = "tw"
    win: str = "w"
    coin: str = "c"
    lines: str = "l"
    next_action: str = "na"
    total_bet: str | None = None  # use when the server sends the full bet directly
    action: str = "action"
    bonus_keys: frozenset[str] = frozenset({"fs", "fsmax", "fsres", "fswin", "fs_total"})
    error_keys: tuple[str, ...] = ("error", "err", "errorcode", "error_code")
    message_keys: tuple[str, ...] = ("msg", "message", "errormsg", "error_msg")


DEFAULT_FIELDS = FieldMap()


def parse_payload(text: str | None) -> dict[str, str]:
    """Parse a form-encoded or flat-JSON body into ``{key: str}``; ``{}`` if unusable."""
    if not text or not text.strip():
        return {}
    body = text.strip()
    if body.startswith("{"):
        return _parse_flat_json(body)
    if "=" not in body:
        return {}
    return dict(parse_qsl(body, keep_blank_values=True))


def _parse_flat_json(body: str) -> dict[str, str]:
    try:
        data = json.loads(body)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float, bool))}


def classify(url: str, request_params: Mapping[str, str], fields: FieldMap = DEFAULT_FIELDS) -> TxKind:
    action = request_params.get(fields.action, "").strip().lower()
    if action:
        if action in _ACTION_KINDS:
            return _ACTION_KINDS[action]
        if action.startswith(_BONUS_ACTION_PREFIXES):
            return TxKind.BONUS
        return TxKind.OTHER
    path = urlsplit(url).path.lower()
    for fragment, kind in _URL_KINDS:
        if fragment in path:
            return kind
    return TxKind.OTHER


def to_decimal(value: str | None) -> Decimal | None:
    """Machine-format number (``99.80``) -> Decimal, or None when absent/invalid."""
    if value is None or not value.strip():
        return None
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def build_transaction(
    seq: int,
    url: str,
    http_status: int | None,
    request_body: str | None,
    response_body: str | None,
    fields: FieldMap = DEFAULT_FIELDS,
) -> GameTransaction:
    request = parse_payload(request_body)
    response = parse_payload(response_body)
    kind = classify(url, request, fields)
    next_action = response.get(fields.next_action)
    return GameTransaction(
        seq=seq,
        kind=kind,
        url=_safe_url(url),
        http_status=http_status,
        request=redact(request),
        response=redact(response),
        balance=to_decimal(response.get(fields.balance)),
        total_win=to_decimal(response.get(fields.total_win)),
        win=to_decimal(response.get(fields.win)),
        bet=_derive_bet(request, response, fields),
        next_action=next_action or None,
        error=_detect_error(http_status, response, fields),
        bonus=_detect_bonus(response, next_action, fields),
    )


def _derive_bet(request: Mapping[str, str], response: Mapping[str, str], fields: FieldMap) -> Decimal | None:
    if fields.total_bet:
        direct = to_decimal(response.get(fields.total_bet) or request.get(fields.total_bet))
        if direct is not None:
            return direct
    coin = to_decimal(response.get(fields.coin) or request.get(fields.coin))
    lines = to_decimal(response.get(fields.lines) or request.get(fields.lines))
    if coin is None or lines is None:
        return None
    return coin * lines


def _detect_error(http_status: int | None, response: Mapping[str, str], fields: FieldMap) -> str | None:
    if http_status is not None and http_status >= 400:
        return f"HTTP {http_status}"
    flagged = [k for k in fields.error_keys if response.get(k, "0").strip() not in ("", "0")]
    if not flagged:
        return None
    for key in fields.message_keys:
        if response.get(key):
            return response[key]
    return f"{flagged[0]}={response[flagged[0]]}"


def _detect_bonus(response: Mapping[str, str], next_action: str | None, fields: FieldMap) -> bool:
    if fields.bonus_keys & set(response):
        return True
    return bool(next_action) and next_action.lower().startswith("fs")


def redact(params: Mapping[str, str]) -> dict[str, str]:
    """Hide session/credential-like values; game numbers stay readable."""
    return {k: (REDACTED if _SENSITIVE_KEY.search(k) else v) for k, v in params.items()}


def _safe_url(url: str) -> str:
    """scheme://host/path only: query strings can carry session tokens."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"
