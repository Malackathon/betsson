"""Unit tests for MasterOrchestrator, SubAgentWorker logic, AccountLockManager, and reports.

Validates pure logic without network calls, browser launches, or external services.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
import time

import pytest

from src.agents.orchestrator import AccountLockManager, GeminiRateLimiter, MasterOrchestrator
from src.agents.sub_agent import SubAgentWorker, _derive_market_and_scenario
from src.models.schemas import (
    AgentId,
    CheckResult,
    CheckStatus,
    GeminiHudReading,
    GeminiMessageReading,
    GeminiSpinLocation,
    Market,
    MasterReport,
    SubAgentReport,
)
from src.report.aggregator import (
    build_master_report,
    find_subagent_reports,
    generate_markdown_summary,
    load_subagent_report,
)
from src.report.html_report import generate_html_report


# ==============================================================================
# Helper Mock Objects for SubAgentWorker
# ==============================================================================


class MockVisionInspector:
    """Mock vision inspector for testing subagent logic."""

    def __init__(
        self,
        credit: str = "100.00",
        after_credit: str | None = None,
        bet: str = "0.20",
        currency: str = "€",
        bonus_on_first_attempt: bool = False,
    ) -> None:
        self.credit = credit
        self.bet = bet
        self.currency = currency
        self.after_credit = (
            after_credit
            if after_credit is not None
            else str(Decimal(credit) - Decimal(bet))
        )
        self.bonus_on_first_attempt = bonus_on_first_attempt
        self.hud_read_count = 0
        self.bonus_check_count = 0

    def read_hud(self, image_path: Path) -> GeminiHudReading:
        self.hud_read_count += 1
        current_credit = self.credit if self.hud_read_count == 1 else self.after_credit
        return GeminiHudReading(
            raw_text=f"CREDIT: {current_credit} BET: {self.bet} WIN: 0.00",
            credit=current_credit,
            bet=self.bet,
            win="0.00",
            currency_symbol=self.currency,
            legible=True,
        )

    def read_insufficient_funds_message(self, image_path: Path) -> GeminiMessageReading:
        return GeminiMessageReading(
            raw_text="Insufficient balance to spin",
            message_text="Insufficient funds to place bet. Please deposit.",
            detected_language="en",
            legible=True,
        )

    def locate_spin_button(self, image_path: Path) -> GeminiSpinLocation:
        return GeminiSpinLocation(raw_text="center bottom", x=0.5, y=0.85, legible=True)

    def is_bonus_or_free_spins_active(self, image_path: Path) -> bool:
        self.bonus_check_count += 1
        if self.bonus_on_first_attempt and self.bonus_check_count == 1:
            return True
        return False


class MockLobbyPage:
    """Mock lobby page for testing balance and navigation."""

    def __init__(
        self,
        initial_balance: str = "100.00",
        after_balance: str | None = None,
        currency: str = "€",
    ) -> None:
        self.initial_balance = Decimal(initial_balance)
        self.after_balance = (
            Decimal(after_balance)
            if after_balance is not None
            else (Decimal(initial_balance) - Decimal("0.20"))
        )
        self.currency = currency
        self.calls = 0

    def login(self, username: str, password: str) -> bool:
        return True

    def navigate_to_game(self, game_title: str) -> bool:
        return True

    def get_betsson_balance(self) -> Decimal:
        self.calls += 1
        if self.calls == 1:
            return self.initial_balance
        return self.after_balance

    def get_betsson_currency(self) -> str:
        return self.currency


# ==============================================================================
# Unit Tests: AccountLockManager
# ==============================================================================


@pytest.mark.unit
def test_account_lock_manager_empty_user(tmp_path: Path) -> None:
    """Empty or whitespace usernames should bypass locking without blocking."""
    manager = AccountLockManager(lock_dir=tmp_path)
    with manager.acquire(""):
        pass
    with manager.acquire("   "):
        pass
    assert len(list(tmp_path.glob("*.lock"))) == 0


@pytest.mark.unit
def test_account_lock_manager_mutual_exclusion(tmp_path: Path) -> None:
    """Same username should acquire mutual exclusion file lock."""
    manager = AccountLockManager(lock_dir=tmp_path)
    user = "test_user_shared@betsson.com"

    acquired = False

    def worker():
        nonlocal acquired
        with manager.acquire(user):
            acquired = True

    with manager.acquire(user):
        t = threading.Thread(target=worker)
        t.start()
        time.sleep(0.05)
        # Worker thread should be blocked waiting for lock
        assert not acquired

    t.join(timeout=2.0)
    assert acquired


@pytest.mark.unit
def test_account_lock_manager_distinct_users(tmp_path: Path) -> None:
    """Different usernames should not block each other."""
    manager = AccountLockManager(lock_dir=tmp_path)
    user1 = "user1@betsson.com"
    user2 = "user2@betsson.com"

    with manager.acquire(user1):
        # Can concurrently acquire for user2
        with manager.acquire(user2):
            pass


# ==============================================================================
# Unit Tests: GeminiRateLimiter
# ==============================================================================


@pytest.mark.unit
def test_gemini_rate_limiter() -> None:
    """Limiter should allow concurrent slots up to capacity."""
    limiter = GeminiRateLimiter(max_concurrent=2, min_interval_sec=0.01)
    with limiter.acquire():
        with limiter.acquire():
            pass


# ==============================================================================
# Unit Tests: SubAgentWorker Logic
# ==============================================================================


@pytest.mark.unit
def test_derive_market_and_scenario() -> None:
    """Validate parsing of market and scenario from AgentId strings."""
    assert _derive_market_and_scenario("agent_com_s1") == (Market.COM, 1)
    assert _derive_market_and_scenario("agent_com_s2") == (Market.COM, 2)
    assert _derive_market_and_scenario("agent_pe_s1") == (Market.PE, 1)
    assert _derive_market_and_scenario("agent_pe_s2") == (Market.PE, 2)


@pytest.mark.unit
def test_subagent_worker_scenario_1_execution(tmp_path: Path) -> None:
    """Scenario 1 execution should verify checks S1.01-S1.11 and generate result JSON."""
    worker = SubAgentWorker(
        agent_id=AgentId.agent_com_s1,
        artifacts_dir=tmp_path,
        lobby_page=MockLobbyPage(initial_balance="100.00", after_balance="99.80", currency="€"),
        vision_inspector=MockVisionInspector(credit="100.00", after_credit="99.80", bet="0.20", currency="€"),
    )
    report = worker.execute()

    assert report.agent_id == AgentId.agent_com_s1
    assert report.market == Market.COM
    assert report.scenario == 1
    assert report.overall == CheckStatus.PASS

    # Verify key checks are present in result
    check_ids = [c.id for c in report.checks]
    assert "S1.01" in check_ids
    assert "S1.02" in check_ids
    assert "S1.03" in check_ids
    assert "S1.04" in check_ids
    assert "S1.05" in check_ids
    assert "S1.06" in check_ids
    assert "S1.07" in check_ids
    assert "S1.08" in check_ids
    assert "S1.09" in check_ids
    assert "S1.10" in check_ids
    assert "S1.11" in check_ids
    assert "info" in check_ids

    # Result JSON should be written to artifacts
    json_path = tmp_path / "result_agent_com_s1.json"
    assert json_path.exists()
    loaded = SubAgentReport.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert loaded.agent_id == AgentId.agent_com_s1


@pytest.mark.unit
def test_subagent_worker_scenario_1_bonus_retry(tmp_path: Path) -> None:
    """Scenario 1 should retry spin when bonus/free spins are detected (R8)."""
    mock_vision = MockVisionInspector(
        credit="100.00",
        after_credit="99.80",
        bet="0.20",
        currency="€",
        bonus_on_first_attempt=True,
    )
    worker = SubAgentWorker(
        agent_id=AgentId.agent_com_s1,
        artifacts_dir=tmp_path,
        lobby_page=MockLobbyPage(initial_balance="100.00", after_balance="99.80", currency="€"),
        vision_inspector=mock_vision,
    )
    report = worker.execute()

    assert report.overall == CheckStatus.PASS
    # Vision checked bonus twice (1st trigger bonus -> retry -> 2nd normal spin)
    assert mock_vision.bonus_check_count == 2


@pytest.mark.unit
def test_subagent_worker_scenario_2_execution(tmp_path: Path) -> None:
    """Scenario 2 execution should verify checks S2.01-S2.07 and generate result JSON."""
    worker = SubAgentWorker(
        agent_id=AgentId.agent_com_s2,
        artifacts_dir=tmp_path,
        lobby_page=MockLobbyPage(initial_balance="0.05", after_balance="0.05", currency="€"),
        vision_inspector=MockVisionInspector(credit="0.05", after_credit="0.05", bet="0.20", currency="€"),
    )
    report = worker.execute()

    assert report.agent_id == AgentId.agent_com_s2
    assert report.market == Market.COM
    assert report.scenario == 2
    assert report.overall == CheckStatus.PASS

    check_ids = [c.id for c in report.checks]
    assert "S2.01" in check_ids
    assert "S2.02" in check_ids
    assert "S2.03" in check_ids
    assert "S2.04" in check_ids
    assert "S2.05" in check_ids
    assert "S2.06" in check_ids
    assert "S2.07" in check_ids


# ==============================================================================
# Unit Tests: MasterOrchestrator and Aggregator
# ==============================================================================


@pytest.fixture
def sample_subagent_reports(tmp_path: Path) -> list[SubAgentReport]:
    """Create 4 mock SubAgentReport instances and write their result JSONs."""
    reports: list[SubAgentReport] = []
    agents = [
        (AgentId.agent_com_s1, Market.COM, 1),
        (AgentId.agent_com_s2, Market.COM, 2),
        (AgentId.agent_pe_s1, Market.PE, 1),
        (AgentId.agent_pe_s2, Market.PE, 2),
    ]

    for aid, mkt, sc in agents:
        agent_dir = tmp_path / aid.value
        agent_dir.mkdir(parents=True, exist_ok=True)
        checks = [
            CheckResult(id="C.01", name="Check 1", expected="True", observed="True", status=CheckStatus.PASS),
            CheckResult(id="C.02", name="Check 2", expected="€", observed="€", status=CheckStatus.PASS),
        ]
        report = SubAgentReport(
            agent_id=aid,
            market=mkt,
            scenario=sc,  # type: ignore[arg-type]
            checks=checks,
            evidence_dir=agent_dir / "evidence",
            video_path=None,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        report_file = agent_dir / f"result_{aid.value}.json"
        report_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        reports.append(report)

    return reports


@pytest.mark.unit
def test_find_and_build_master_report(tmp_path: Path, sample_subagent_reports: list[SubAgentReport]) -> None:
    """find_subagent_reports should scan artifacts and build a valid MasterReport."""
    found = find_subagent_reports(tmp_path)
    assert len(found) == 4

    master = build_master_report(found)
    assert master.total_pass == 8
    assert master.total_fail == 0
    assert master.all_passed is True


@pytest.mark.unit
def test_master_report_with_failures() -> None:
    """MasterReport should compute total_fail and all_passed=False when checks fail."""
    report = SubAgentReport(
        agent_id=AgentId.agent_com_s1,
        market=Market.COM,
        scenario=1,
        checks=[
            CheckResult(id="S1.01", name="Check 1", status=CheckStatus.PASS),
            CheckResult(id="S1.02", name="Check 2", status=CheckStatus.FAIL),
        ],
        evidence_dir=Path("artifacts"),
        video_path=None,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    master = MasterReport(reports=[report])
    assert master.total_pass == 1
    assert master.total_fail == 1
    assert master.all_passed is False


@pytest.mark.unit
def test_generate_html_report_zero_cdns(sample_subagent_reports: list[SubAgentReport]) -> None:
    """generate_html_report must produce self-contained HTML without external CDNs."""
    master = build_master_report(sample_subagent_reports)
    html_text = generate_html_report(master)

    assert "<!DOCTYPE html>" in html_text
    assert "agent_com_s1" in html_text
    assert "agent_pe_s2" in html_text
    assert "C.01" in html_text
    assert "ALL CHECKS PASSED" in html_text

    # Verify no external CDN dependencies
    assert "fonts.googleapis.com" not in html_text
    assert "cdnjs.cloudflare.com" not in html_text
    assert "cdn.jsdelivr.net" not in html_text


@pytest.mark.unit
def test_generate_markdown_summary(sample_subagent_reports: list[SubAgentReport]) -> None:
    """generate_markdown_summary should format master report into GitHub-flavored Markdown."""
    master = build_master_report(sample_subagent_reports)
    md_text = generate_markdown_summary(master)

    assert "# 🎰 Betsson Intelligent Game Validation — E2E Master Report" in md_text
    assert "`agent_com_s1`" in md_text
    assert "🟢 PASS" in md_text
    assert "| Check ID | Name | Status | Expected | Observed | Detail |" in md_text


@pytest.mark.unit
def test_orchestrator_save_reports(tmp_path: Path, sample_subagent_reports: list[SubAgentReport]) -> None:
    """MasterOrchestrator.save_reports should generate json, html, and md files."""
    orchestrator = MasterOrchestrator(artifacts_dir=tmp_path)
    master = build_master_report(sample_subagent_reports)
    json_p, html_p, md_p = orchestrator.save_reports(master)

    assert json_p.exists()
    assert html_p.exists()
    assert md_p.exists()

    # Re-reading json matches
    reloaded = MasterReport.model_validate_json(json_p.read_text(encoding="utf-8"))
    assert len(reloaded.reports) == 4
