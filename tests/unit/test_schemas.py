"""Unit tests for src.models.schemas.

Tests Pydantic v2 domain models, enum behaviors, computed properties,
and serialization contracts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models import (
    AgentId,
    CheckResult,
    CheckStatus,
    GeminiBalanceReading,
    GeminiHudReading,
    GeminiMessageReading,
    GeminiReading,
    GeminiSpinLocation,
    Market,
    MarketConfig,
    MasterReport,
    SubAgentReport,
)


class TestCheckStatus:
    """Tests for the CheckStatus enum."""

    def test_values_and_types(self) -> None:
        """Verify enum members, string inheritance, and Enum subclassing."""
        assert issubclass(CheckStatus, Enum)
        assert issubclass(CheckStatus, str)

        assert CheckStatus.PASS == "PASS"
        assert CheckStatus.FAIL == "FAIL"
        assert CheckStatus.INFO == "INFO"
        assert CheckStatus.ERROR == "ERROR"
        assert CheckStatus.SKIP == "SKIP"

    def test_case_insensitive_lookup(self) -> None:
        """Verify case-insensitive lookup for CheckStatus."""
        assert CheckStatus("pass") is CheckStatus.PASS
        assert CheckStatus("Pass") is CheckStatus.PASS
        assert CheckStatus("FAIL") is CheckStatus.FAIL
        assert CheckStatus("fail") is CheckStatus.FAIL
        assert CheckStatus("info") is CheckStatus.INFO
        assert CheckStatus("error") is CheckStatus.ERROR
        assert CheckStatus("skip") is CheckStatus.SKIP


class TestAgentId:
    """Tests for the AgentId enum."""

    def test_values(self) -> None:
        """Verify all four agent identifiers."""
        assert AgentId.agent_com_s1 == "agent_com_s1"
        assert AgentId.agent_com_s2 == "agent_com_s2"
        assert AgentId.agent_pe_s1 == "agent_pe_s1"
        assert AgentId.agent_pe_s2 == "agent_pe_s2"

    def test_uppercase_aliases(self) -> None:
        """Verify uppercase aliases map to the same enum instances."""
        assert AgentId.AGENT_COM_S1 is AgentId.agent_com_s1
        assert AgentId.AGENT_COM_S2 is AgentId.agent_com_s2
        assert AgentId.AGENT_PE_S1 is AgentId.agent_pe_s1
        assert AgentId.AGENT_PE_S2 is AgentId.agent_pe_s2

    def test_case_insensitive_lookup(self) -> None:
        """Verify case-insensitive lookup."""
        assert AgentId("AGENT_COM_S1") is AgentId.agent_com_s1
        assert AgentId("agent_pe_s2") is AgentId.agent_pe_s2


class TestMarket:
    """Tests for the Market enum."""

    def test_values(self) -> None:
        """Verify COM and PE markets."""
        assert Market.COM == "COM"
        assert Market.PE == "PE"

    def test_case_insensitive_lookup(self) -> None:
        """Verify case-insensitive lookup."""
        assert Market("com") is Market.COM
        assert Market("pe") is Market.PE
        assert Market("COM") is Market.COM
        assert Market("PE") is Market.PE


class TestCheckResult:
    """Tests for CheckResult schema."""

    def test_check_result_defaults(self) -> None:
        """Verify default values for optional fields."""
        check = CheckResult(id="S1.01", name="Login verification", status=CheckStatus.PASS)
        assert check.id == "S1.01"
        assert check.name == "Login verification"
        assert check.status is CheckStatus.PASS
        assert check.expected is None
        assert check.observed is None
        assert check.detail is None

    def test_check_result_full(self) -> None:
        """Verify CheckResult with all fields populated."""
        check = CheckResult(
            id="S1.09",
            name="Balance reconciliation",
            expected="100.00 EUR",
            observed="99.80 EUR",
            detail="Discrepancy of 0.20 EUR observed",
            status=CheckStatus.FAIL,
        )
        assert check.expected == "100.00 EUR"
        assert check.observed == "99.80 EUR"
        assert check.detail == "Discrepancy of 0.20 EUR observed"
        assert check.status is CheckStatus.FAIL

    def test_check_result_serialization(self) -> None:
        """Verify JSON dump serializes status as string."""
        check = CheckResult(id="S1.01", name="Login", status=CheckStatus.PASS)
        dumped = check.model_dump(mode="json")
        assert dumped["status"] == "PASS"

        raw_json = check.model_dump_json()
        assert '"status":"PASS"' in raw_json


class TestSubAgentReport:
    """Tests for SubAgentReport schema and overall computed property."""

    @pytest.fixture
    def base_kwargs(self) -> dict:
        """Base arguments for building a valid SubAgentReport."""
        now = datetime.now(timezone.utc)
        return {
            "agent_id": AgentId.agent_com_s1,
            "market": Market.COM,
            "scenario": 1,
            "evidence_dir": Path("artifacts/agent_com_s1"),
            "video_path": Path("artifacts/agent_com_s1/run.webm"),
            "started_at": now,
            "finished_at": now,
        }

    def test_overall_pass_when_all_pass_info_skip(self, base_kwargs: dict) -> None:
        """Verify overall is PASS when all checks are PASS, INFO, or SKIP."""
        checks = [
            CheckResult(id="1", name="Step 1", status=CheckStatus.PASS),
            CheckResult(id="2", name="Step 2", status=CheckStatus.INFO),
            CheckResult(id="3", name="Step 3", status=CheckStatus.SKIP),
        ]
        report = SubAgentReport(checks=checks, **base_kwargs)
        assert report.overall is CheckStatus.PASS

    def test_overall_fail_when_any_fail(self, base_kwargs: dict) -> None:
        """Verify overall is FAIL if at least one check is FAIL."""
        checks = [
            CheckResult(id="1", name="Step 1", status=CheckStatus.PASS),
            CheckResult(id="2", name="Step 2", status=CheckStatus.FAIL),
            CheckResult(id="3", name="Step 3", status=CheckStatus.SKIP),
        ]
        report = SubAgentReport(checks=checks, **base_kwargs)
        assert report.overall is CheckStatus.FAIL

    def test_overall_error_precedence_over_fail(self, base_kwargs: dict) -> None:
        """Verify overall returns ERROR even if FAIL is also present."""
        checks = [
            CheckResult(id="1", name="Step 1", status=CheckStatus.PASS),
            CheckResult(id="2", name="Step 2", status=CheckStatus.FAIL),
            CheckResult(id="3", name="Step 3", status=CheckStatus.ERROR),
        ]
        report = SubAgentReport(checks=checks, **base_kwargs)
        assert report.overall is CheckStatus.ERROR

    def test_overall_empty_checks(self, base_kwargs: dict) -> None:
        """Verify overall is PASS for empty checks (vacuously true, no errors/fails)."""
        report = SubAgentReport(checks=[], **base_kwargs)
        assert report.overall is CheckStatus.PASS

    def test_overall_is_property_not_stored_field(self, base_kwargs: dict) -> None:
        """Verify overall is a python property and not included in model_dump."""
        report = SubAgentReport(checks=[], **base_kwargs)
        assert "overall" not in report.model_dump()
        assert report.overall == CheckStatus.PASS

    def test_validation_error_on_missing_required_fields(self) -> None:
        """Verify missing fields raise Pydantic ValidationError."""
        with pytest.raises(ValidationError):
            SubAgentReport.model_validate({"agent_id": "agent_com_s1"})


class TestMasterReport:
    """Tests for MasterReport aggregation and metrics."""

    def _make_report(
        self, agent_id: AgentId, market: Market, statuses: list[CheckStatus]
    ) -> SubAgentReport:
        now = datetime.now(timezone.utc)
        checks = [
            CheckResult(id=f"chk_{idx}", name=f"Check {idx}", status=st)
            for idx, st in enumerate(statuses)
        ]
        return SubAgentReport(
            agent_id=agent_id,
            market=market,
            scenario=1,
            checks=checks,
            evidence_dir=Path(f"artifacts/{agent_id}"),
            started_at=now,
            finished_at=now,
        )

    def test_aggregations_all_passed(self) -> None:
        """Verify metrics when all subagent reports pass."""
        rep1 = self._make_report(
            AgentId.agent_com_s1, Market.COM, [CheckStatus.PASS, CheckStatus.INFO]
        )
        rep2 = self._make_report(
            AgentId.agent_pe_s1, Market.PE, [CheckStatus.PASS, CheckStatus.SKIP]
        )
        master = MasterReport(reports=[rep1, rep2])

        assert master.total_pass == 2
        assert master.total_fail == 0
        assert master.all_passed is True

    def test_aggregations_with_failures(self) -> None:
        """Verify metrics when failures or errors are present."""
        rep1 = self._make_report(
            AgentId.agent_com_s1, Market.COM, [CheckStatus.PASS, CheckStatus.FAIL]
        )
        rep2 = self._make_report(
            AgentId.agent_pe_s1, Market.PE, [CheckStatus.PASS, CheckStatus.ERROR]
        )
        master = MasterReport(reports=[rep1, rep2])

        assert master.total_pass == 2
        assert master.total_fail == 1
        assert master.all_passed is False

    def test_master_report_empty(self) -> None:
        """Verify metrics when reports list is empty."""
        master = MasterReport(reports=[])
        assert master.total_pass == 0
        assert master.total_fail == 0
        assert master.all_passed is False


class TestGeminiContracts:
    """Tests for Gemini vision structured readings."""

    def test_gemini_reading_hierarchy(self) -> None:
        """Verify all readings inherit from GeminiReading and BaseModel."""
        for cls in (
            GeminiBalanceReading,
            GeminiHudReading,
            GeminiMessageReading,
            GeminiSpinLocation,
        ):
            assert issubclass(cls, GeminiReading)

    def test_balance_reading(self) -> None:
        """Verify GeminiBalanceReading fields and defaults."""
        reading = GeminiBalanceReading(
            raw_text="Balance: € 1,234.56",
            amount="1,234.56",
            currency_symbol="€",
            legible=True,
        )
        assert reading.raw_text == "Balance: € 1,234.56"
        assert reading.amount == "1,234.56"
        assert reading.currency_symbol == "€"
        assert reading.legible is True

        default_reading = GeminiBalanceReading(raw_text="unclear")
        assert default_reading.amount is None
        assert default_reading.currency_symbol is None
        assert default_reading.legible is True

    def test_hud_reading(self) -> None:
        """Verify GeminiHudReading fields."""
        hud = GeminiHudReading(
            raw_text="CREDIT: 100.00 BET: 0.20 WIN: 0.00",
            credit="100.00",
            bet="0.20",
            win="0.00",
            currency_symbol="€",
        )
        assert hud.credit == "100.00"
        assert hud.bet == "0.20"
        assert hud.win == "0.00"
        assert hud.currency_symbol == "€"
        assert hud.legible is True

    def test_message_reading(self) -> None:
        """Verify GeminiMessageReading fields."""
        msg = GeminiMessageReading(
            raw_text="Saldo insuficiente para jugar",
            message_text="Saldo insuficiente para jugar",
            detected_language="es",
            legible=True,
        )
        assert msg.message_text == "Saldo insuficiente para jugar"
        assert msg.detected_language == "es"
        assert msg.legible is True

    def test_spin_location(self) -> None:
        """Verify GeminiSpinLocation coordinates."""
        spin = GeminiSpinLocation(
            raw_text="Spin button at bottom right",
            x=0.92,
            y=0.88,
            legible=True,
        )
        assert spin.x == 0.92
        assert spin.y == 0.88
        assert spin.legible is True


class TestMarketConfig:
    """Tests for MarketConfig schema."""

    def test_market_config_defaults(self) -> None:
        """Verify default values for selectors and notes."""
        cfg = MarketConfig(
            url="https://www.betsson.com",
            locale="en",
            currency="EUR",
            currency_symbol="€",
            keywords_insufficient=["insufficient", "funds", "balance"],
            game_candidates=["Gates of Olympus", "Sweet Bonanza"],
        )
        assert cfg.url == "https://www.betsson.com"
        assert cfg.locale == "en"
        assert cfg.currency == "EUR"
        assert cfg.currency_symbol == "€"
        assert cfg.keywords_insufficient == ["insufficient", "funds", "balance"]
        assert cfg.game_candidates == ["Gates of Olympus", "Sweet Bonanza"]
        assert cfg.selectors == {}
        assert cfg.notes == ""

    def test_market_config_with_custom_selectors_and_notes(self) -> None:
        """Verify MarketConfig with custom selectors and notes."""
        cfg = MarketConfig(
            url="https://www.betsson.pe",
            locale="es",
            currency="PEN",
            currency_symbol="S/",
            keywords_insufficient=["saldo", "insuficiente"],
            game_candidates=["Gates of Olympus"],
            selectors={"login_button": "#login", "balance": ".user-balance"},
            notes="Requires geo-unblock check",
        )
        assert cfg.selectors["login_button"] == "#login"
        assert cfg.notes == "Requires geo-unblock check"
