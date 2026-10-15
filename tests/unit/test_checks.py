"""Unit tests for src/core/checks.py.

Tests cover:
    - CheckRunner lifecycle, soft-check execution, and exception capture
    - run_check direct recording and status determination
    - info and skip methods
    - passed property semantics (only FAIL and ERROR make it False)
    - summary formatting
    - reconcile_ingame_balance (S1.09) with exact and tolerance bounds
    - reconcile_betsson_balance (S1.10)
    - check_balance_unchanged (S2.06, S2.07) for Scenario 2
    - check_language_keywords (S2.04) case-insensitivity and market keywords
    - String vs Decimal handling and error resilience
"""

from decimal import Decimal
import pytest

from src.core.checks import (
    CheckRunner,
    check_balance_unchanged,
    check_language_keywords,
    reconcile_betsson_balance,
    reconcile_ingame_balance,
)

try:
    from src.models.schemas import CheckStatus
except ImportError:
    from src.core.checks import CheckStatus


class TestCheckRunner:
    """Tests for the core CheckRunner class."""

    def test_init_state(self) -> None:
        runner = CheckRunner()
        assert len(runner.results) == 0
        assert len(runner) == 0
        assert runner.passed is True
        assert runner.failed is False
        assert runner.failures == []

    def test_run_success_pass(self) -> None:
        runner = CheckRunner()
        res = runner.run("S1.01", "Saldo visible", lambda: ("10.00", "10.00", "DOM found"))
        assert res.id == "S1.01"
        assert res.name == "Saldo visible"
        assert res.expected == "10.00"
        assert res.observed == "10.00"
        assert res.status == CheckStatus.PASS
        assert res.detail == "DOM found"
        assert runner.passed is True
        assert len(runner) == 1

    def test_run_mismatch_fail(self) -> None:
        runner = CheckRunner()
        res = runner.run("S1.03", "Moneda", lambda: ("EUR", "USD", "Wrong currency"))
        assert res.id == "S1.03"
        assert res.status == CheckStatus.FAIL
        assert res.expected == "EUR"
        assert res.observed == "USD"
        assert runner.passed is False
        assert runner.failed is True
        assert len(runner.failures) == 1

    def test_run_info_when_expected_is_none(self) -> None:
        runner = CheckRunner()
        res = runner.run("info", "In-game vs Betsson", lambda: (None, "diff: 0.05", "Informative only"))
        assert res.status == CheckStatus.PASS
        assert res.expected is None
        assert res.observed == "diff: 0.05"
        assert runner.passed is True

    def test_run_captures_exception_as_error(self) -> None:
        runner = CheckRunner()

        def faulty_check():
            raise TimeoutError("Element selector timed out after 5s")

        res = runner.run("S1.02", "Canvas visible", faulty_check)
        assert res.id == "S1.02"
        assert res.status == CheckStatus.ERROR
        assert res.expected is None
        assert res.observed is None
        assert "TimeoutError: Element selector timed out after 5s" in (res.detail or "")
        assert runner.passed is False
        assert len(runner.failures) == 1

    def test_run_check_direct(self) -> None:
        runner = CheckRunner()
        r1 = runner.run_check("S1.01", "Check 1", expected="A", observed="A")
        assert r1.status == CheckStatus.PASS

        r2 = runner.run_check("S1.02", "Check 2", expected="A", observed="B")
        assert r2.status == CheckStatus.FAIL

        r3 = runner.run_check("S1.03", "Check 3", expected=None, observed="C")
        assert r3.status == CheckStatus.PASS

        # Explicit status override
        r4 = runner.run_check("S1.04", "Check 4", expected="A", observed="B", status=CheckStatus.PASS)
        assert r4.status == CheckStatus.PASS

    def test_info_method(self) -> None:
        runner = CheckRunner()
        res = runner.info("info_01", "Observación", "Lectura HUD exitosa")
        assert res.id == "info_01"
        assert res.status == CheckStatus.INFO
        assert res.detail == "Lectura HUD exitosa"
        # INFO does not mark runner as failed
        assert runner.passed is True

    def test_skip_method(self) -> None:
        runner = CheckRunner()
        res = runner.skip("S1.07", "Bonus round", "No bonus triggered, step skipped")
        assert res.id == "S1.07"
        assert res.status == CheckStatus.SKIP
        assert res.detail == "No bonus triggered, step skipped"
        # SKIP does not mark runner as failed
        assert runner.passed is True

    def test_passed_semantics_with_mixed_statuses(self) -> None:
        runner = CheckRunner()
        runner.run_check("c1", "p1", expected="1", observed="1")
        runner.info("c2", "i1", "info")
        runner.skip("c3", "s1", "skip")
        assert runner.passed is True

        runner.run_check("c4", "f1", expected="1", observed="2")
        assert runner.passed is False

    def test_get_check_and_iteration(self) -> None:
        runner = CheckRunner()
        runner.run_check("A1", "First", expected="x", observed="x")
        runner.run_check("A2", "Second", expected="y", observed="y")

        assert runner.get_check("A1") is not None
        assert runner.get_check("A1").name == "First"  # type: ignore[union-attr]
        assert runner.get_check("A3") is None

        ids = [c.id for c in runner]
        assert ids == ["A1", "A2"]

    def test_summary_formatting(self) -> None:
        runner = CheckRunner()
        runner.run_check("S1.01", "Saldo Betsson", expected="100.00", observed="100.00")
        runner.run_check("S1.02", "Juego abierto", expected="open", observed="closed")
        runner.info("info", "Nota", "Solo informativo")

        summary_text = runner.summary()
        assert "=== CheckRunner Summary [FAILED] ===" in summary_text
        assert "Total: 3" in summary_text
        assert "PASS: 1" in summary_text
        assert "FAIL: 1" in summary_text
        assert "INFO: 1" in summary_text
        assert "S1.01: Saldo Betsson" in summary_text
        assert "S1.02: Juego abierto" in summary_text


class TestReconciliationChecks:
    """Tests for S1.09 and S1.10 balance reconciliation helpers."""

    def test_reconcile_ingame_balance_exact_match(self) -> None:
        runner = CheckRunner()
        res = reconcile_ingame_balance(
            runner,
            before=Decimal("100.00"),
            bet=Decimal("1.00"),
            prize=Decimal("2.50"),
            after=Decimal("101.50"),
        )
        assert res.id == "S1.09"
        assert res.name == "Saldo in-game reconcilia"
        assert res.status == CheckStatus.PASS
        assert res.expected == "101.50"
        assert res.observed == "101.50"
        assert "PASSED" in (res.detail or "")
        assert runner.passed is True

    def test_reconcile_ingame_balance_with_tolerance(self) -> None:
        runner = CheckRunner()
        # 100 - 1 + 0 = 99.00 expected; observed 99.01 (diff 0.01 <= tolerance 0.01)
        res = reconcile_ingame_balance(
            runner,
            before=Decimal("100.00"),
            bet=Decimal("1.00"),
            prize=Decimal("0.00"),
            after=Decimal("99.01"),
        )
        assert res.id == "S1.09"
        assert res.status == CheckStatus.PASS
        assert runner.passed is True

    def test_reconcile_ingame_balance_fail_beyond_tolerance(self) -> None:
        runner = CheckRunner()
        # 100 - 1 + 0 = 99.00 expected; observed 98.90 (diff 0.10 > tolerance)
        res = reconcile_ingame_balance(
            runner,
            before=Decimal("100.00"),
            bet=Decimal("1.00"),
            prize=Decimal("0.00"),
            after=Decimal("98.90"),
        )
        assert res.id == "S1.09"
        assert res.status == CheckStatus.FAIL
        assert runner.passed is False

    def test_reconcile_ingame_balance_string_inputs(self) -> None:
        runner = CheckRunner()
        # Accepts ES format string inputs with currency
        res = reconcile_ingame_balance(
            runner,
            before="€ 1.000,50",  # type: ignore[arg-type]
            bet="€ 0,50",        # type: ignore[arg-type]
            prize="€ 0,00",       # type: ignore[arg-type]
            after="€ 1.000,00",   # type: ignore[arg-type]
        )
        assert res.status == CheckStatus.PASS
        assert res.expected == "1000.00"
        assert res.observed == "1000.00"

    def test_reconcile_betsson_balance(self) -> None:
        runner = CheckRunner()
        res = reconcile_betsson_balance(
            runner,
            before=Decimal("50.00"),
            bet=Decimal("2.00"),
            prize=Decimal("10.00"),
            after=Decimal("58.00"),
        )
        assert res.id == "S1.10"
        assert res.name == "Saldo Betsson reconcilia"
        assert res.status == CheckStatus.PASS
        assert runner.passed is True

    def test_reconcile_handles_float_as_error(self) -> None:
        runner = CheckRunner()
        # Floating point forbidden by rule 1: captured as ERROR without raising
        res = reconcile_ingame_balance(
            runner,
            before=100.0,  # type: ignore[arg-type]
            bet=Decimal("1.00"),
            prize=Decimal("0.00"),
            after=Decimal("99.00"),
        )
        assert res.status == CheckStatus.ERROR
        assert "forbidden" in (res.detail or "").lower()


class TestScenario2Checks:
    """Tests for Scenario 2 (insufficient funds): S2.04, S2.06, S2.07."""

    def test_check_balance_unchanged_pass(self) -> None:
        runner = CheckRunner()
        res = check_balance_unchanged(
            runner,
            check_id="S2.06",
            name="Saldo in-game sin cambios",
            before=Decimal("0.05"),
            after=Decimal("0.05"),
        )
        assert res.id == "S2.06"
        assert res.status == CheckStatus.PASS
        assert res.expected == "0.05"
        assert res.observed == "0.05"
        assert "unchanged" in (res.detail or "").lower()
        assert runner.passed is True

    def test_check_balance_unchanged_fail(self) -> None:
        runner = CheckRunner()
        res = check_balance_unchanged(
            runner,
            check_id="S2.07",
            name="Saldo Betsson sin cambios",
            before=Decimal("10.00"),
            after=Decimal("9.00"),
        )
        assert res.id == "S2.07"
        assert res.status == CheckStatus.FAIL
        assert "changed" in (res.detail or "").lower()
        assert runner.passed is False

    def test_check_balance_unchanged_with_strings(self) -> None:
        runner = CheckRunner()
        res = check_balance_unchanged(
            runner,
            check_id="S2.06",
            name="Saldo in-game",
            before="S/ 12,50",  # type: ignore[arg-type]
            after="S/ 12,50",   # type: ignore[arg-type]
        )
        assert res.status == CheckStatus.PASS
        assert res.expected == "12.50"
        assert res.observed == "12.50"

    def test_check_language_keywords_en(self) -> None:
        runner = CheckRunner()
        keywords = ["insufficient", "funds", "balance"]
        msg = "You have Insufficient Funds to place this bet. Please deposit."

        res = check_language_keywords(runner, msg, keywords)
        assert res.id == "S2.04"
        assert res.status == CheckStatus.PASS
        assert "insufficient" in (res.observed or "").lower()
        assert runner.passed is True

    def test_check_language_keywords_es(self) -> None:
        runner = CheckRunner()
        keywords = ["insuficiente", "fondos", "saldo"]
        msg = "Saldo insuficiente para realizar el giro."

        res = check_language_keywords(runner, msg, keywords)
        assert res.id == "S2.04"
        assert res.status == CheckStatus.PASS
        assert runner.passed is True

    def test_check_language_keywords_fail_when_no_match(self) -> None:
        runner = CheckRunner()
        keywords = ["insufficient", "funds", "balance"]
        msg = "An unexpected network error occurred."

        res = check_language_keywords(runner, msg, keywords)
        assert res.id == "S2.04"
        assert res.status == CheckStatus.FAIL
        assert runner.passed is False

    def test_check_language_keywords_empty_message(self) -> None:
        runner = CheckRunner()
        keywords = ["insufficient", "funds"]

        res = check_language_keywords(runner, "", keywords)
        assert res.id == "S2.04"
        assert res.status == CheckStatus.FAIL
        assert runner.passed is False
