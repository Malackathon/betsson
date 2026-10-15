"""NetworkMonitor against a REAL Chromium and a local mock game server (localhost only)."""

from __future__ import annotations

import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest

from src.flows.spin_runner import run_spin_with_bonus_retry
from src.network.models import SpinAttemptStatus
from src.network.monitor import NetworkMonitor

pytestmark = pytest.mark.slow

PAGE = """<html><body><button id="spin" onclick="spin()">spin</button><script>
const post = (b) => fetch('/gs2c/ge/v4/gameService', {method:'POST',
  headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:b}).then(r => r.text());
post('action=doInit&symbol=mock');
async function spin() {
  const r = await post('action=doSpin&symbol=mock&c=0.01&l=20&mgckey=SECRET');
  if (r.includes('na=c')) { await post('action=doCollect&symbol=mock&mgckey=SECRET'); }
}
</script></body></html>"""


class MockGame(BaseHTTPRequestHandler):
    balance = "100.00"
    mode = "lose"  # lose | win | reject

    def log_message(self, *args) -> None:  # keep test output quiet
        pass

    def _send(self, body: str, ctype: str = "text/plain") -> None:
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._send(PAGE, "text/html")

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers["Content-Length"])).decode()
        action = parse_qs(raw).get("action", [""])[0]
        cls = type(self)
        if action == "doInit":
            self._send(f"balance={cls.balance}&c=0.01&l=20&na=s")
        elif action == "doSpin" and cls.mode == "reject":
            self._send(f"error=1&msg=Insufficient%20funds&balance={cls.balance}")
        elif action == "doSpin" and cls.mode == "win":
            self._send("tw=1.50&balance=99.80&c=0.01&l=20&na=c")
        elif action == "doSpin":
            self._send("tw=0.00&balance=99.80&c=0.01&l=20&na=s")
        else:  # doCollect
            self._send("tw=1.50&balance=101.30&na=s")


@pytest.fixture
def game_server():
    server = HTTPServer(("127.0.0.1", 0), MockGame)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


@pytest.fixture
def page():
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Error:
            pytest.skip("Chromium is not installed")
        yield browser.new_page()
        browser.close()


class _Canvas:
    """Clicks the mock Spin button; stands in for GameCanvas."""

    def __init__(self, page, tmp_path) -> None:
        self.page, self.tmp_path = page, tmp_path

    def click_spin(self, coords) -> None:
        self.page.click("#spin")

    def take_game_screenshot(self, name: str):
        path = self.tmp_path / f"{name}.png"
        path.write_bytes(self.page.screenshot())
        return path


def _prepare(page, url) -> NetworkMonitor:
    monitor = NetworkMonitor()
    monitor.attach(page)
    page.goto(url)
    page.wait_for_timeout(300)
    monitor.mark()
    return monitor


def _spin(page, monitor, tmp_path):
    return run_spin_with_bonus_retry(
        _Canvas(page, tmp_path), monitor, {"x": 0.5, "y": 0.5}, round_timeout_s=5, post_settle_ms=0
    )


def test_real_browser_captures_init_balance_and_settled_losing_spin(game_server, page, tmp_path):
    MockGame.balance, MockGame.mode = "100.00", "lose"
    monitor = _prepare(page, game_server)
    assert monitor.last_balance == Decimal("100.00")

    run = _spin(page, monitor, tmp_path)

    rnd = run.attempt.round
    assert run.attempt.status is SpinAttemptStatus.SETTLED
    assert (rnd.balance_before, rnd.balance_after, rnd.bet) == (
        Decimal("100.00"), Decimal("99.80"), Decimal("0.20"),
    )
    assert rnd.server_reconciles is True
    assert run.final_screenshot.exists()


def test_real_browser_waits_for_collect_on_winning_spin(game_server, page, tmp_path):
    MockGame.balance, MockGame.mode = "100.00", "win"
    monitor = _prepare(page, game_server)

    rnd = _spin(page, monitor, tmp_path).attempt.round

    assert rnd.total_win == Decimal("1.50")
    assert rnd.balance_after == Decimal("101.30")
    assert rnd.server_reconciles is True


def test_real_browser_reports_server_rejection(game_server, page, tmp_path):
    MockGame.balance, MockGame.mode = "0.05", "reject"
    monitor = _prepare(page, game_server)

    attempt = _spin(page, monitor, tmp_path).attempt

    assert attempt.status is SpinAttemptStatus.REJECTED
    assert "insufficient" in attempt.error.lower()


def test_real_browser_evidence_never_contains_the_session_token(game_server, page, tmp_path):
    MockGame.balance, MockGame.mode = "100.00", "lose"
    monitor = _prepare(page, game_server)
    _spin(page, monitor, tmp_path)

    text = monitor.save_evidence(tmp_path / "net.json").read_text(encoding="utf-8")

    assert "SECRET" not in text
    assert "doSpin" in text
