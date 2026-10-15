"""Spin runner tests with a fake canvas that feeds the real NetworkMonitor."""

from __future__ import annotations

from pathlib import Path

from src.flows.spin_runner import run_spin_with_bonus_retry
from src.network.models import SpinAttemptStatus
from src.network.monitor import NetworkMonitor

GATEWAY = "https://games.pragmaticplay.net/gs2c/ge/v4/gameService"
SPIN_REQ = "action=doSpin&symbol=x&c=0.01&l=20&mgckey=SECRET"
INIT_REQ = "action=doInit&symbol=x"


class FakeCanvas:
    """Each click delivers the next scripted server response to the monitor."""

    def __init__(self, monitor: NetworkMonitor, responses: list[str | None], tmp: Path) -> None:
        self._monitor = monitor
        self._responses = list(responses)
        self._tmp = tmp
        self.clicks = 0
        self.screenshots: list[str] = []

    def click_spin(self, coords) -> None:
        self.clicks += 1
        response = self._responses.pop(0) if self._responses else None
        if response is not None:
            self._monitor.ingest(GATEWAY, "POST", 200, SPIN_REQ, response)

    def take_game_screenshot(self, name: str) -> Path:
        self.screenshots.append(name)
        path = self._tmp / f"{name}.png"
        path.write_bytes(b"png")
        return path


def _monitor_with_balance(balance: str = "100.00") -> NetworkMonitor:
    monitor = NetworkMonitor()
    monitor.ingest(GATEWAY, "POST", 200, INIT_REQ, f"balance={balance}&c=0.01&l=20&na=s")
    return monitor


def _run(monitor, responses, tmp_path, **kwargs):
    canvas = FakeCanvas(monitor, responses, tmp_path)
    run = run_spin_with_bonus_retry(
        canvas, monitor, {"x": 0.5, "y": 0.9}, round_timeout_s=0.3, post_settle_ms=0, **kwargs
    )
    return canvas, run


def test_settled_spin_captures_screenshot_after_server_response(tmp_path):
    monitor = _monitor_with_balance()
    canvas, run = _run(monitor, ["tw=0.00&balance=99.80&c=0.01&l=20&na=s"], tmp_path)

    assert run.attempt.status is SpinAttemptStatus.SETTLED
    assert run.final_screenshot is not None
    assert run.bonus_retries == 0
    assert canvas.clicks == 1
    assert canvas.screenshots == ["final_after_round"]


def test_bonus_round_triggers_a_retry_until_a_clean_spin(tmp_path):
    monitor = _monitor_with_balance()
    responses = [
        "tw=0.00&balance=99.80&c=0.01&l=20&na=s&fs=1&fsmax=10",
        "tw=0.00&balance=99.60&c=0.01&l=20&na=s",
    ]
    canvas, run = _run(monitor, responses, tmp_path, max_bonus_retries=3)

    assert canvas.clicks == 2
    assert run.bonus_retries == 1
    assert run.attempt.round.bonus_triggered is False
    assert run.attempt.round.balance_before == run.attempt.round.balance_after + run.attempt.round.bet


def test_bonus_retries_are_bounded(tmp_path):
    monitor = _monitor_with_balance()
    bonus = "tw=0.00&balance=99.80&c=0.01&l=20&na=s&fs=1"
    canvas, run = _run(monitor, [bonus, bonus, bonus, bonus], tmp_path, max_bonus_retries=2)

    assert canvas.clicks == 2
    assert run.attempt.round.bonus_triggered is True


def test_click_without_server_traffic_reports_no_traffic_and_still_screenshots(tmp_path):
    monitor = _monitor_with_balance("0.05")
    canvas, run = _run(monitor, [None], tmp_path)

    assert run.attempt.status is SpinAttemptStatus.NO_TRAFFIC
    assert run.final_screenshot is not None
    assert canvas.clicks == 1


def test_server_rejection_is_not_retried(tmp_path):
    monitor = _monitor_with_balance("0.05")
    canvas, run = _run(monitor, ["error=1&msg=Insufficient%20funds&balance=0.05"], tmp_path)

    assert run.attempt.status is SpinAttemptStatus.REJECTED
    assert canvas.clicks == 1
