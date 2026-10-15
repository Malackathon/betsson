"""Checks derived from network ground truth plus ONE grounded Gemini read per scenario."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.agents.networked_scenarios import ScenarioContext, evaluate_scenario_1, evaluate_scenario_2
from src.core.checks import CheckRunner
from src.flows.game_flow import SpinOutcome, SpinStatus
from src.models.schemas import CheckStatus
from src.network.models import RoundResult, SpinAttempt, SpinAttemptStatus
from src.vision.grounding import GroundedScreenReading


class FakeInspector:
    """Records how it was called so tests can assert grounding and call budget."""

    def __init__(self, reading: GroundedScreenReading) -> None:
        self.reading = reading
        self.calls: list[tuple[Path, str]] = []

    def read_screen_grounded(self, screenshot: Path, reference_block: str) -> GroundedScreenReading:
        self.calls.append((screenshot, reference_block))
        return self.reading


def _status(runner: CheckRunner) -> dict[str, CheckStatus]:
    return {c.id: c.status for c in runner.results}


def _ctx(inspector, market="com", symbol="€", keywords=("insufficient", "funds")) -> ScenarioContext:
    return ScenarioContext(
        market=market,
        currency_symbol=symbol,
        insufficient_keywords=list(keywords),
        inspector=inspector,
    )


def _round(**overrides) -> RoundResult:
    base = dict(
        balance_before=Decimal("100.00"),
        balance_after=Decimal("99.80"),
        bet=Decimal("0.20"),
        total_win=Decimal("0.00"),
        bonus_triggered=False,
        server_reconciles=True,
    )
    base.update(overrides)
    return RoundResult(**base)


def _s1_outcome(tmp_path: Path, rnd: RoundResult | None = None, **overrides) -> SpinOutcome:
    rnd = rnd or _round()
    shot = tmp_path / "final.png"
    shot.write_bytes(b"png")
    base = dict(
        status=SpinStatus.COMPLETED,
        balance_before=Decimal("100.00"),
        balance_after=Decimal("99.80"),
        bet_amount=rnd.bet or Decimal("0"),
        win_amount=rnd.total_win or Decimal("0"),
        hud_credit_before=rnd.balance_before or Decimal("0"),
        hud_credit_after=rnd.balance_after or Decimal("0"),
        currency_observed="€",
        spin_attempt=SpinAttempt(SpinAttemptStatus.SETTLED, round=rnd),
        network_round=rnd,
        final_screenshot=shot,
    )
    base.update(overrides)
    return SpinOutcome(**base)


GOOD_S1_READING = GroundedScreenReading(
    credit_raw="€99.80", bet_raw="€0.20", win_raw="0.00", currency_raw="€", legible=True
)


def test_scenario_1_all_green_with_a_single_gemini_call(tmp_path):
    inspector = FakeInspector(GOOD_S1_READING)
    runner = CheckRunner()

    evaluate_scenario_1(runner, _s1_outcome(tmp_path), _ctx(inspector))

    statuses = _status(runner)
    for check_id in ["S1.01", "S1.02", "S1.03", "S1.04", "S1.05", "S1.06", "S1.07",
                     "S1.08", "S1.09", "S1.10", "S1.11"]:
        assert statuses[check_id] is CheckStatus.PASS, check_id
    assert len(inspector.calls) == 1


def test_gemini_is_grounded_with_the_server_numbers(tmp_path):
    inspector = FakeInspector(GOOD_S1_READING)
    evaluate_scenario_1(CheckRunner(), _s1_outcome(tmp_path), _ctx(inspector))

    _, reference_block = inspector.calls[0]
    assert "99.80" in reference_block
    assert "0.20" in reference_block
    assert "€" in reference_block


def test_scenario_1_fails_when_screen_balance_disagrees_with_server(tmp_path):
    wrong = GOOD_S1_READING.model_copy(update={"credit_raw": "€100.00"})
    runner = CheckRunner()

    evaluate_scenario_1(runner, _s1_outcome(tmp_path), _ctx(FakeInspector(wrong)))

    assert _status(runner)["S1.09"] is CheckStatus.FAIL


def test_scenario_1_fails_when_displayed_bet_differs_from_bet_charged(tmp_path):
    wrong = GOOD_S1_READING.model_copy(update={"bet_raw": "€1.00"})
    runner = CheckRunner()

    evaluate_scenario_1(runner, _s1_outcome(tmp_path), _ctx(FakeInspector(wrong)))

    assert _status(runner)["S1.08"] is CheckStatus.FAIL


def test_scenario_1_fails_when_betsson_balance_does_not_reconcile(tmp_path):
    outcome = _s1_outcome(tmp_path, balance_after=Decimal("100.00"))
    runner = CheckRunner()

    evaluate_scenario_1(runner, outcome, _ctx(FakeInspector(GOOD_S1_READING)))

    assert _status(runner)["S1.10"] is CheckStatus.FAIL


def test_scenario_1_winning_spin_reconciles_with_payout(tmp_path):
    rnd = _round(balance_after=Decimal("101.30"), total_win=Decimal("1.50"))
    outcome = _s1_outcome(tmp_path, rnd, balance_after=Decimal("101.30"))
    reading = GOOD_S1_READING.model_copy(update={"credit_raw": "€101.30", "win_raw": "€1.50"})
    runner = CheckRunner()

    evaluate_scenario_1(runner, outcome, _ctx(FakeInspector(reading)))

    assert _status(runner)["S1.09"] is CheckStatus.PASS
    assert _status(runner)["S1.10"] is CheckStatus.PASS


def test_scenario_1_with_no_server_round_fails_without_calling_gemini(tmp_path):
    attempt = SpinAttempt(SpinAttemptStatus.NO_TRAFFIC)
    outcome = _s1_outcome(tmp_path, network_round=None, spin_attempt=attempt, status=SpinStatus.ERROR)
    inspector = FakeInspector(GOOD_S1_READING)
    runner = CheckRunner()

    evaluate_scenario_1(runner, outcome, _ctx(inspector))

    statuses = _status(runner)
    assert statuses["S1.05"] is CheckStatus.FAIL
    assert statuses["S1.09"] is CheckStatus.FAIL
    assert statuses["S1.10"] is CheckStatus.FAIL
    assert inspector.calls == []


def test_scenario_1_bonus_left_over_is_informative_and_skips_reconciliation(tmp_path):
    rnd = _round(bonus_triggered=True)
    outcome = _s1_outcome(tmp_path, rnd, status=SpinStatus.BONUS_TRIGGERED)
    runner = CheckRunner()

    evaluate_scenario_1(runner, outcome, _ctx(FakeInspector(GOOD_S1_READING)))

    statuses = _status(runner)
    assert statuses["S1.07"] is CheckStatus.INFO
    assert statuses["S1.09"] is CheckStatus.SKIP


# ------------------------------------------------------------------ scenario 2

GOOD_S2_READING = GroundedScreenReading(
    credit_raw="€0.05",
    bet_raw="€0.20",
    currency_raw="€",
    message_raw="Insufficient funds. Please deposit.",
    message_language="EN",
    legible=True,
)


def _s2_outcome(tmp_path: Path, attempt: SpinAttempt | None = None, **overrides) -> SpinOutcome:
    shot = tmp_path / "s2.png"
    shot.write_bytes(b"png")
    base = dict(
        status=SpinStatus.INSUFFICIENT_FUNDS,
        balance_before=Decimal("0.05"),
        balance_after=Decimal("0.05"),
        bet_amount=Decimal("0.20"),
        hud_credit_before=Decimal("0.05"),
        hud_credit_after=Decimal("0.05"),
        currency_observed="€",
        spin_attempt=attempt or SpinAttempt(SpinAttemptStatus.NO_TRAFFIC),
        final_screenshot=shot,
        server_balance_known=True,
    )
    base.update(overrides)
    return SpinOutcome(**base)


def test_scenario_2_all_green_with_a_single_gemini_call(tmp_path):
    inspector = FakeInspector(GOOD_S2_READING)
    runner = CheckRunner()

    evaluate_scenario_2(runner, _s2_outcome(tmp_path), _ctx(inspector))

    statuses = _status(runner)
    for check_id in ["S2.01", "S2.02", "S2.03", "S2.04", "S2.05", "S2.06", "S2.07"]:
        assert statuses[check_id] is CheckStatus.PASS, check_id
    assert len(inspector.calls) == 1


def test_scenario_2_fails_when_a_paid_spin_went_through(tmp_path):
    attempt = SpinAttempt(SpinAttemptStatus.SETTLED, round=_round(balance_before=Decimal("5.00")))
    outcome = _s2_outcome(tmp_path, attempt, status=SpinStatus.COMPLETED)
    runner = CheckRunner()

    evaluate_scenario_2(runner, outcome, _ctx(FakeInspector(GOOD_S2_READING)))

    assert _status(runner)["S2.02"] is CheckStatus.FAIL


def test_scenario_2_passes_on_explicit_server_rejection(tmp_path):
    attempt = SpinAttempt(SpinAttemptStatus.REJECTED, error="Insufficient funds")
    runner = CheckRunner()

    evaluate_scenario_2(runner, _s2_outcome(tmp_path, attempt), _ctx(FakeInspector(GOOD_S2_READING)))

    assert _status(runner)["S2.02"] is CheckStatus.PASS


def test_scenario_2_fails_when_server_balance_changed(tmp_path):
    outcome = _s2_outcome(tmp_path, hud_credit_after=Decimal("0.00"))
    runner = CheckRunner()

    evaluate_scenario_2(runner, outcome, _ctx(FakeInspector(GOOD_S2_READING)))

    assert _status(runner)["S2.06"] is CheckStatus.FAIL
    assert _status(runner)["S2.02"] is CheckStatus.FAIL


def test_scenario_2_fails_on_wrong_language(tmp_path):
    spanish = GOOD_S2_READING.model_copy(update={"message_raw": "Saldo insuficiente", "message_language": "ES"})
    runner = CheckRunner()

    evaluate_scenario_2(runner, _s2_outcome(tmp_path), _ctx(FakeInspector(spanish)))

    assert _status(runner)["S2.04"] is CheckStatus.FAIL


def test_scenario_2_fails_when_no_message_is_visible(tmp_path):
    silent = GOOD_S2_READING.model_copy(update={"message_raw": None, "message_language": None})
    runner = CheckRunner()

    evaluate_scenario_2(runner, _s2_outcome(tmp_path), _ctx(FakeInspector(silent)))

    assert _status(runner)["S2.03"] is CheckStatus.FAIL


def test_scenario_2_precondition_fails_when_balance_covers_the_bet(tmp_path):
    outcome = _s2_outcome(tmp_path, hud_credit_before=Decimal("5.00"), hud_credit_after=Decimal("5.00"))
    runner = CheckRunner()

    evaluate_scenario_2(runner, outcome, _ctx(FakeInspector(GOOD_S2_READING)))

    assert _status(runner)["S2.01"] is CheckStatus.FAIL


@pytest.mark.parametrize("missing", ["final_screenshot"])
def test_scenario_2_without_screenshot_fails_visual_checks(tmp_path, missing):
    outcome = _s2_outcome(tmp_path, **{missing: None})
    runner = CheckRunner()

    evaluate_scenario_2(runner, outcome, _ctx(FakeInspector(GOOD_S2_READING)))

    assert _status(runner)["S2.03"] is CheckStatus.FAIL


# ---------------------------------------------- visual reaction (PDF: "verify from the screen")


def _shots(tmp_path, changed: bool):
    from PIL import Image

    pre, post = tmp_path / "pre.png", tmp_path / "post.png"
    Image.new("RGB", (200, 100), (10, 10, 10)).save(pre)
    after = Image.new("RGB", (200, 100), (10, 10, 10))
    if changed:
        after.paste(Image.new("RGB", (80, 50), (240, 200, 30)), (30, 20))
    after.save(post)
    return pre, post


def test_scenario_1_passes_visual_reaction_when_the_screen_changed(tmp_path):
    pre, post = _shots(tmp_path, changed=True)
    outcome = _s1_outcome(tmp_path, final_screenshot=post, screenshots=[pre, post])
    runner = CheckRunner()

    evaluate_scenario_1(runner, outcome, _ctx(FakeInspector(GOOD_S1_READING)))

    assert _status(runner)["S1.05v"] is CheckStatus.PASS


def test_scenario_1_fails_visual_reaction_when_the_screen_did_not_change(tmp_path):
    pre, post = _shots(tmp_path, changed=False)
    outcome = _s1_outcome(tmp_path, final_screenshot=post, screenshots=[pre, post])
    runner = CheckRunner()

    evaluate_scenario_1(runner, outcome, _ctx(FakeInspector(GOOD_S1_READING)))

    assert _status(runner)["S1.05v"] is CheckStatus.FAIL


def test_scenario_1_skips_visual_reaction_without_a_before_screenshot(tmp_path):
    runner = CheckRunner()
    evaluate_scenario_1(runner, _s1_outcome(tmp_path), _ctx(FakeInspector(GOOD_S1_READING)))
    assert _status(runner)["S1.05v"] is CheckStatus.SKIP


def test_scenario_2_does_not_pass_vacuously_when_the_server_balance_was_never_read(tmp_path):
    """0 == 0 because nothing was parsed is NOT a verified 'balance unchanged'."""
    outcome = _s2_outcome(
        tmp_path, hud_credit_before=Decimal("0"), hud_credit_after=Decimal("0"), server_balance_known=False
    )
    runner = CheckRunner()

    evaluate_scenario_2(runner, outcome, _ctx(FakeInspector(GOOD_S2_READING)))

    statuses = _status(runner)
    assert statuses["S2.06"] is CheckStatus.FAIL
    assert statuses["S2.02"] is CheckStatus.FAIL
    assert statuses["S2.01"] is CheckStatus.FAIL
    detail = next(c.detail for c in runner.results if c.id == "S2.06")
    assert "no se pudo leer" in detail.lower()


def test_a_real_zero_balance_account_still_passes_when_the_server_reported_it(tmp_path):
    outcome = _s2_outcome(
        tmp_path, hud_credit_before=Decimal("0"), hud_credit_after=Decimal("0"), server_balance_known=True
    )
    runner = CheckRunner()

    evaluate_scenario_2(runner, outcome, _ctx(FakeInspector(GOOD_S2_READING)))

    assert _status(runner)["S2.06"] is CheckStatus.PASS
    assert _status(runner)["S2.01"] is CheckStatus.PASS
