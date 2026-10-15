"""Unit tests for NetworkMonitor state tracking and round settlement (no browser)."""

from __future__ import annotations

import json
from decimal import Decimal

from src.network.models import SpinAttemptStatus
from src.network.monitor import NetworkMonitor

GATEWAY = "https://games.pragmaticplay.net/gs2c/ge/v4/gameService"
INIT_REQ = "action=doInit&symbol=vs20fruitsw"
SPIN_REQ = "action=doSpin&symbol=vs20fruitsw&c=0.01&l=20&counter=3&mgckey=SECRET"
COLLECT_REQ = "action=doCollect&symbol=vs20fruitsw&counter=5&mgckey=SECRET"


def _monitor() -> NetworkMonitor:
    return NetworkMonitor()


def _feed(mon: NetworkMonitor, req: str, resp: str, status: int = 200) -> None:
    mon.ingest(url=GATEWAY, method="POST", http_status=status, request_body=req, response_body=resp)


def test_init_response_sets_last_known_balance():
    mon = _monitor()
    _feed(mon, INIT_REQ, "balance=100.00&c=0.01&l=20&na=s")
    assert mon.last_balance == Decimal("100.00")


def test_irrelevant_traffic_is_ignored():
    mon = _monitor()
    mon.ingest(
        url="https://cdn.example.com/app.js",
        method="GET",
        http_status=200,
        request_body=None,
        response_body="console.log(1)",
    )
    assert mon.transaction_count == 0


def test_settled_losing_spin_reconciles_on_the_server_side():
    mon = _monitor()
    _feed(mon, INIT_REQ, "balance=100.00&c=0.01&l=20&na=s")
    mark = mon.mark()
    _feed(mon, SPIN_REQ, "tw=0.00&balance=99.80&c=0.01&l=20&na=s&w=0.00")

    attempt = mon.evaluate_round(since=mark)

    assert attempt.status is SpinAttemptStatus.SETTLED
    rnd = attempt.round
    assert rnd is not None
    assert rnd.balance_before == Decimal("100.00")
    assert rnd.balance_after == Decimal("99.80")
    assert rnd.bet == Decimal("0.20")
    assert rnd.total_win == Decimal("0.00")
    assert rnd.server_reconciles is True
    assert rnd.bonus_triggered is False


def test_winning_spin_waits_for_collect_before_settling():
    mon = _monitor()
    _feed(mon, INIT_REQ, "balance=100.00&c=0.01&l=20&na=s")
    mark = mon.mark()
    _feed(mon, SPIN_REQ, "tw=1.50&balance=99.80&c=0.01&l=20&na=c")

    pending = mon.evaluate_round(since=mark)
    assert pending.status is SpinAttemptStatus.PENDING

    _feed(mon, COLLECT_REQ, "tw=1.50&balance=101.30&na=s")
    settled = mon.evaluate_round(since=mark)

    assert settled.status is SpinAttemptStatus.SETTLED
    assert settled.round.balance_after == Decimal("101.30")
    assert settled.round.total_win == Decimal("1.50")
    assert settled.round.server_reconciles is True


def test_server_mismatch_is_reported_not_hidden():
    mon = _monitor()
    _feed(mon, INIT_REQ, "balance=100.00&c=0.01&l=20&na=s")
    mark = mon.mark()
    _feed(mon, SPIN_REQ, "tw=0.00&balance=100.00&c=0.01&l=20&na=s")  # bet never debited

    attempt = mon.evaluate_round(since=mark)

    assert attempt.status is SpinAttemptStatus.SETTLED
    assert attempt.round.server_reconciles is False


def test_bonus_round_is_flagged():
    mon = _monitor()
    _feed(mon, INIT_REQ, "balance=100.00&c=0.01&l=20&na=s")
    mark = mon.mark()
    _feed(mon, SPIN_REQ, "tw=0.00&balance=99.80&c=0.01&l=20&na=s&fs=1&fsmax=10")

    attempt = mon.evaluate_round(since=mark)

    assert attempt.round.bonus_triggered is True


def test_rejected_spin_when_server_returns_error():
    mon = _monitor()
    _feed(mon, INIT_REQ, "balance=0.05&c=0.01&l=20&na=s")
    mark = mon.mark()
    _feed(mon, SPIN_REQ, "error=1&msg=Insufficient%20funds&balance=0.05")

    attempt = mon.evaluate_round(since=mark)

    assert attempt.status is SpinAttemptStatus.REJECTED
    assert "insufficient" in attempt.error.lower()
    assert attempt.round is None


def test_no_traffic_when_nothing_arrives_after_mark():
    mon = _monitor()
    _feed(mon, INIT_REQ, "balance=0.05&c=0.01&l=20&na=s")
    attempt = mon.evaluate_round(since=mon.mark())
    assert attempt.status is SpinAttemptStatus.NO_TRAFFIC


def test_last_bet_comes_from_server_coin_and_lines():
    mon = _monitor()
    assert mon.last_bet is None
    _feed(mon, INIT_REQ, "balance=0.05&c=0.01&l=20&na=s")
    assert mon.last_bet == Decimal("0.20")


class _FakeRequest:
    def __init__(self, resource_type: str, method: str = "POST", post_data: str | None = None) -> None:
        self.resource_type, self.method, self.post_data = resource_type, method, post_data


class _FakeResponse:
    def __init__(self, url: str, body: str, request: _FakeRequest, status: int = 200) -> None:
        self.url, self.status, self.request, self._body = url, status, request, body

    def text(self) -> str:
        return self._body


class _FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.waited_ms = 0

    def on(self, event: str, handler) -> None:
        self.handlers[event] = handler

    def remove_listener(self, event: str, handler) -> None:
        self.handlers.pop(event, None)

    def wait_for_timeout(self, ms: int) -> None:
        self.waited_ms += ms


def test_attached_monitor_reads_xhr_bodies_lazily_and_ignores_static_assets():
    page, mon = _FakePage(), _monitor()
    mon.attach(page)

    page.handlers["response"](
        _FakeResponse(GATEWAY, "balance=100.00&c=0.01&l=20&na=s", _FakeRequest("xhr", post_data=INIT_REQ))
    )
    page.handlers["response"](
        _FakeResponse("https://cdn.example.com/sprite.png", "x", _FakeRequest("image", "GET"))
    )

    assert mon.transaction_count == 0  # bodies are only read when asked
    mon.mark()
    assert mon.transaction_count == 1
    assert mon.last_balance == Decimal("100.00")


def test_wait_for_round_pumps_events_and_returns_no_traffic_on_timeout():
    page, mon = _FakePage(), _monitor()
    mon.attach(page)
    attempt = mon.wait_for_round(since=0, timeout_s=0.05)

    assert attempt.status is SpinAttemptStatus.NO_TRAFFIC
    assert page.waited_ms > 0


def test_detach_removes_listeners():
    page, mon = _FakePage(), _monitor()
    mon.attach(page)
    mon.detach()
    assert page.handlers == {}


def test_evidence_json_redacts_tokens_and_has_no_headers(tmp_path):
    mon = _monitor()
    _feed(mon, INIT_REQ, "balance=100.00&c=0.01&l=20&na=s")
    _feed(mon, SPIN_REQ, "tw=0.00&balance=99.80&c=0.01&l=20&na=s")

    out = mon.save_evidence(tmp_path / "network.json")
    text = out.read_text(encoding="utf-8")

    assert "SECRET" not in text
    data = json.loads(text)
    assert data[1]["request"]["mgckey"] == "<redacted>"
    assert data[1]["response"]["balance"] == "99.80"
