"""Unit tests for the Pragmatic gameService payload parser.

The payloads below are SYNTHETIC samples built from the documented gs2c
key/value format. Field names must be re-validated against live traffic with
the calibration capture (see NetworkMonitor.save_evidence).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.network.models import TxKind
from src.network.parser import (
    FieldMap,
    build_transaction,
    classify,
    parse_payload,
    redact,
)

INIT_RESP = "balance=100.00&balance_cash=100.00&balance_bonus=0.00&c=0.01&l=20&na=s&stime=1760000000"
SPIN_REQ = "action=doSpin&symbol=vs20fruitsw&c=0.01&l=20&index=2&counter=3&mgckey=SECRET-TOKEN-123"
SPIN_RESP_LOSS = "tw=0.00&balance=99.80&c=0.01&l=20&index=2&counter=4&na=s&w=0.00"
SPIN_RESP_COLLECT = "tw=1.50&balance=99.80&c=0.01&l=20&index=2&counter=4&na=c&w=1.50"
GATEWAY = "https://demogamesfree.pragmaticplay.net/gs2c/ge/v4/gameService"


def test_parse_payload_reads_form_encoded_pairs():
    parsed = parse_payload("a=1&b=two&empty=")
    assert parsed == {"a": "1", "b": "two", "empty": ""}


def test_parse_payload_reads_flat_json_object():
    parsed = parse_payload('{"balance": 12.5, "na": "s", "nested": {"x": 1}}')
    assert parsed["balance"] == "12.5"
    assert parsed["na"] == "s"
    assert "nested" not in parsed  # only scalar top-level values are kept


@pytest.mark.parametrize("text", ["", "   ", None, "not a payload at all"])
def test_parse_payload_returns_empty_for_unusable_input(text):
    assert parse_payload(text) == {}


@pytest.mark.parametrize(
    "url, request_params, expected",
    [
        (GATEWAY, {"action": "doInit"}, TxKind.INIT),
        (GATEWAY, {"action": "doSpin"}, TxKind.SPIN),
        (GATEWAY, {"action": "doCollect"}, TxKind.COLLECT),
        (GATEWAY, {"action": "doBonus"}, TxKind.BONUS),
        (GATEWAY, {"action": "doFSOption"}, TxKind.BONUS),
        ("https://x.test/api/spin", {}, TxKind.SPIN),
        ("https://x.test/api/balance", {}, TxKind.BALANCE),
        ("https://x.test/analytics", {}, TxKind.OTHER),
    ],
)
def test_classify(url, request_params, expected):
    assert classify(url, request_params) is expected


def test_build_transaction_spin_loss_derives_bet_from_coin_and_lines():
    tx = build_transaction(
        seq=1,
        url=GATEWAY,
        http_status=200,
        request_body=SPIN_REQ,
        response_body=SPIN_RESP_LOSS,
    )
    assert tx.kind is TxKind.SPIN
    assert tx.balance == Decimal("99.80")
    assert tx.bet == Decimal("0.20")
    assert tx.total_win == Decimal("0.00")
    assert tx.next_action == "s"
    assert tx.error is None
    assert tx.bonus is False


def test_build_transaction_flags_pending_collect():
    tx = build_transaction(
        seq=2, url=GATEWAY, http_status=200, request_body=SPIN_REQ, response_body=SPIN_RESP_COLLECT
    )
    assert tx.total_win == Decimal("1.50")
    assert tx.next_action == "c"


def test_build_transaction_init_has_balance_but_no_bet_requirement():
    tx = build_transaction(
        seq=0,
        url=GATEWAY,
        http_status=200,
        request_body="action=doInit&symbol=vs20fruitsw",
        response_body=INIT_RESP,
    )
    assert tx.kind is TxKind.INIT
    assert tx.balance == Decimal("100.00")


def test_build_transaction_detects_free_spin_keys_as_bonus():
    tx = build_transaction(
        seq=3,
        url=GATEWAY,
        http_status=200,
        request_body=SPIN_REQ,
        response_body="tw=0.00&balance=99.80&c=0.01&l=20&na=s&fs=1&fsmax=10",
    )
    assert tx.bonus is True


def test_build_transaction_flags_http_error_as_rejected():
    tx = build_transaction(
        seq=4, url=GATEWAY, http_status=500, request_body=SPIN_REQ, response_body=""
    )
    assert tx.error is not None
    assert "500" in tx.error


def test_build_transaction_flags_error_keys_in_payload():
    tx = build_transaction(
        seq=5,
        url=GATEWAY,
        http_status=200,
        request_body=SPIN_REQ,
        response_body="error=1&msg=Insufficient%20funds&balance=0.05",
    )
    assert tx.error is not None
    assert "insufficient" in tx.error.lower()


def test_build_transaction_keeps_unparseable_numbers_as_none():
    tx = build_transaction(
        seq=6,
        url=GATEWAY,
        http_status=200,
        request_body=SPIN_REQ,
        response_body="balance=NaN?&tw=&c=0.01&l=20&na=s",
    )
    assert tx.balance is None
    assert tx.total_win is None


def test_custom_field_map_overrides_keys():
    fields = FieldMap(balance="bal", total_win="win_total", next_action="next")
    tx = build_transaction(
        seq=7,
        url=GATEWAY,
        http_status=200,
        request_body="action=doSpin&c=0.10&l=10",
        response_body="bal=50.00&win_total=2.00&next=s",
        fields=fields,
    )
    assert tx.balance == Decimal("50.00")
    assert tx.total_win == Decimal("2.00")
    assert tx.bet == Decimal("1.00")


def test_redact_hides_session_tokens_but_keeps_game_values():
    safe = redact(parse_payload(SPIN_REQ))
    assert safe["mgckey"] == "<redacted>"
    assert safe["action"] == "doSpin"
    assert safe["c"] == "0.01"
