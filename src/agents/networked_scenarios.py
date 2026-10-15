"""Scenario checks driven by network ground truth plus ONE grounded Gemini read.

Numbers (balance, bet, win) come from the game server via the network monitor, at zero
cost and deterministic. Gemini is called once per scenario, on the screenshot taken the
moment the round settled, only to verify that the PLAYER SEES those same values.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from src.core.checks import (
    CheckRunner,
    check_balance_unchanged,
    check_language_keywords,
    reconcile_betsson_balance,
    reconcile_ingame_balance,
)
from src.flows.game_flow import SpinOutcome
from src.models.schemas import CheckStatus
from src.network.models import SpinAttemptStatus
from src.vision.screen_change import REACTION_THRESHOLD, screen_change
from src.vision.grounding import (
    FieldComparison,
    GroundedScreenReading,
    ScreenReference,
    build_reference_block,
    compare_reading,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
UNREADABLE = "no readable value on screen"


class GroundedVision(Protocol):
    def read_screen_grounded(self, screenshot: Path, reference_block: str) -> GroundedScreenReading: ...


@dataclass(frozen=True)
class ScenarioContext:
    market: str  # "com" | "pe"
    currency_symbol: str
    insufficient_keywords: list[str]
    inspector: GroundedVision
    include_reference_values: bool = True


@dataclass(frozen=True)
class ScreenVerification:
    reading: GroundedScreenReading | None
    by_field: dict[str, FieldComparison]

    def matches(self, field: str) -> bool | None:
        comparison = self.by_field.get(field)
        return comparison.matches if comparison else None

    def detail(self, field: str) -> str:
        comparison = self.by_field.get(field)
        return comparison.detail if comparison else UNREADABLE


def _verify_screen(ctx: ScenarioContext, screenshot: Path | None, reference: ScreenReference) -> ScreenVerification:
    """The single Gemini call of a scenario, grounded with the server numbers."""
    if screenshot is None or not Path(screenshot).exists():
        return ScreenVerification(None, {})
    block = build_reference_block(reference, include_values=ctx.include_reference_values)
    reading = ctx.inspector.read_screen_grounded(Path(screenshot), block)
    comparisons = compare_reading(reading, reference)
    return ScreenVerification(reading, {c.field: c for c in comparisons})


def _status(ok: bool) -> CheckStatus:
    return CheckStatus.PASS if ok else CheckStatus.FAIL


def _tri_status(value: bool | None) -> CheckStatus:
    return CheckStatus.PASS if value is True else CheckStatus.FAIL


# ----------------------------------------------------------------- Scenario 1


def evaluate_scenario_1(runner: CheckRunner, outcome: SpinOutcome, ctx: ScenarioContext) -> None:
    attempt, rnd = outcome.spin_attempt, outcome.network_round
    settled = attempt is not None and attempt.status is SpinAttemptStatus.SETTLED and rnd is not None

    runner.run_check(
        "S1.01", "Saldo Betsson antes legible",
        expected="Decimal > 0", observed=str(outcome.balance_before),
        detail=f"Saldo en cabecera (DOM): {outcome.balance_before}",
        status=_status(outcome.balance_before > ZERO),
    )

    screen = ScreenVerification(None, {})
    if settled:
        reference = ScreenReference(rnd.balance_after, rnd.bet, rnd.total_win, ctx.currency_symbol, ctx.market)
        screen = _verify_screen(ctx, outcome.final_screenshot, reference)
    _screen_checks_s1(runner, screen, settled)
    _spin_lifecycle_checks(runner, attempt, rnd)
    _visual_reaction_check(runner, outcome)

    bonus_left = bool(rnd and rnd.bonus_triggered)
    _bonus_check(runner, rnd, outcome.bonus_retries)
    if not settled:
        _fail_reconciliation(runner, attempt)
    elif bonus_left:
        runner.skip("S1.09", "Saldo in-game reconcilia", "Bonus/free spins activos tras agotar reintentos (R8)")
        runner.skip("S1.10", "Saldo Betsson reconcilia", "Bonus/free spins activos tras agotar reintentos (R8)")
    else:
        _reconciliation_checks(runner, outcome, screen)

    curr_ok = ctx.currency_symbol.lower() in outcome.currency_observed.lower() or (
        bool(outcome.currency_observed) and outcome.currency_observed.lower() in ctx.currency_symbol.lower()
    )
    runner.run_check(
        "S1.11", "Moneda de Betsson = mercado",
        expected=ctx.currency_symbol, observed=outcome.currency_observed,
        detail=f"Moneda en cabecera Betsson (DOM): {outcome.currency_observed!r}",
        status=_status(curr_ok),
    )


def _screen_checks_s1(runner: CheckRunner, screen: ScreenVerification, settled: bool) -> None:
    reading = screen.reading
    hud_ok = bool(reading and reading.legible and reading.credit_raw)
    runner.run_check(
        "S1.02", "Juego Pragmatic abierto en Real Play",
        expected="HUD visible con CREDIT/BET/WIN",
        observed="HUD legible" if hud_ok else "HUD ilegible o sin giro liquidado",
        detail="Lectura visual de la captura tomada al liquidarse la ronda" if settled else "Sin ronda liquidada",
        status=_status(hud_ok),
    )
    runner.run_check(
        "S1.03", "Moneda mostrada = mercado",
        expected="currency", observed=screen.detail("currency"),
        detail=screen.detail("currency"), status=_tri_status(screen.matches("currency")),
    )
    legible = screen.matches("balance") is not None and screen.matches("bet") is not None
    runner.run_check(
        "S1.04", "Apuesta y saldo in-game legibles",
        expected="credit y bet legibles en pantalla",
        observed="legibles" if legible else UNREADABLE,
        detail=f"balance: {screen.detail('balance')} | bet: {screen.detail('bet')}",
        status=_status(legible),
    )
    runner.run_check(
        "S1.08", "Apuesta mostrada = apuesta usada",
        expected="apuesta en pantalla == apuesta cobrada por el servidor",
        observed=screen.detail("bet"), detail=screen.detail("bet"),
        status=_tri_status(screen.matches("bet")),
    )


def _spin_lifecycle_checks(runner: CheckRunner, attempt, rnd) -> None:
    started = attempt is not None and attempt.status is not SpinAttemptStatus.NO_TRAFFIC
    runner.run_check(
        "S1.05", "El giro empezó",
        expected="True", observed=str(started),
        detail="La petición de giro llegó al servidor del juego (red)" if started
        else "Ninguna petición de giro llegó al servidor tras el clic",
        status=_status(started),
    )
    done = attempt is not None and attempt.status is SpinAttemptStatus.SETTLED
    runner.run_check(
        "S1.06", "El giro terminó",
        expected="True", observed=str(done),
        detail="El servidor liquidó la ronda (na=s)" if done else (attempt.detail if attempt else "sin intento de giro"),
        status=_status(done),
    )


def _visual_reaction_check(runner: CheckRunner, outcome: SpinOutcome) -> None:
    """The PDF asks to verify FROM THE SCREEN that the game reacted: compare before/after captures."""
    shots = [p for p in outcome.screenshots if p is not None]
    before, after = (shots[0] if shots else None), outcome.final_screenshot
    change = screen_change(before, after) if before and after and before != after else None
    if change is None:
        runner.skip("S1.05v", "El juego reaccionó en pantalla", "Sin capturas antes/después comparables")
        return
    runner.run_check(
        "S1.05v", "El juego reaccionó en pantalla",
        expected=f"cambio visual >= {REACTION_THRESHOLD}", observed=f"{change:.4f}",
        detail="Diferencia entre la captura previa al giro y la tomada al liquidarse la ronda (sin IA)",
        status=_status(change >= REACTION_THRESHOLD),
    )


def _bonus_check(runner: CheckRunner, rnd, retries: int) -> None:
    if rnd is None:
        runner.skip("S1.07", "No se disparó bonus/free spins", "Sin ronda liquidada que inspeccionar")
    elif rnd.bonus_triggered:
        runner.run_check(
            "S1.07", "No se disparó bonus/free spins",
            expected="False", observed="True",
            detail=f"Bonus activo tras {retries} reintento(s); no es un fallo del producto (R8)",
            status=CheckStatus.INFO,
        )
    else:
        runner.run_check(
            "S1.07", "No se disparó bonus/free spins",
            expected="False", observed="False",
            detail=f"Giro base estándar ({retries} reintento(s) por bonus)", status=CheckStatus.PASS,
        )


def _fail_reconciliation(runner: CheckRunner, attempt) -> None:
    why = attempt.detail if attempt else "sin intento de giro"
    for check_id, name in (("S1.09", "Saldo in-game reconcilia"), ("S1.10", "Saldo Betsson reconcilia")):
        runner.run_check(
            check_id, name, expected="saldo_después = antes − apuesta + premio",
            observed="sin ronda liquidada", detail=f"No se puede reconciliar: {why}", status=CheckStatus.FAIL,
        )


def _reconciliation_checks(runner: CheckRunner, outcome: SpinOutcome, screen: ScreenVerification) -> None:
    rnd = outcome.network_round
    runner.run_check(
        "S1.09n", "Servidor: saldo reconcilia (red)",
        expected="saldo_después = antes − apuesta + premio",
        observed=str(rnd.server_reconciles),
        detail=f"antes={rnd.balance_before}, apuesta={rnd.bet}, premio={rnd.total_win}, después={rnd.balance_after}",
        status=_status(rnd.server_reconciles is True),
    )
    shown = screen.by_field["balance"].observed if "balance" in screen.by_field else None
    if shown is None or not rnd.is_complete:
        runner.run_check(
            "S1.09", "Saldo in-game reconcilia",
            expected="saldo visible == antes − apuesta + premio", observed=UNREADABLE,
            detail=screen.detail("balance"), status=CheckStatus.FAIL,
        )
    else:
        reconcile_ingame_balance(runner, rnd.balance_before, rnd.bet, rnd.total_win, shown)
    reconcile_betsson_balance(
        runner, outcome.balance_before, rnd.bet or ZERO, rnd.total_win or ZERO, outcome.balance_after
    )


# ----------------------------------------------------------------- Scenario 2


def evaluate_scenario_2(runner: CheckRunner, outcome: SpinOutcome, ctx: ScenarioContext) -> None:
    attempt = outcome.spin_attempt
    bet, before, after = outcome.bet_amount, outcome.hud_credit_before, outcome.hud_credit_after

    reference = ScreenReference(after if after > ZERO else None, bet if bet > ZERO else None, None,
                                ctx.currency_symbol, ctx.market)
    screen = _verify_screen(ctx, outcome.final_screenshot, reference)

    precondition = bet > ZERO and before < bet
    runner.run_check(
        "S2.01", "Precondición: saldo < apuesta",
        expected="saldo < apuesta", observed=f"saldo={before}, apuesta={bet}",
        detail="Cuenta preparada (saldo según el servidor)" if precondition
        else "Cuenta no preparada o apuesta desconocida: el saldo cubre la apuesta",
        status=_status(precondition),
    )

    unchanged = before == after
    rejected = (attempt is None or attempt.status in (SpinAttemptStatus.REJECTED, SpinAttemptStatus.NO_TRAFFIC))
    runner.run_check(
        "S2.02", "El giro es rechazado (no hay giro pagado)",
        expected="True", observed=str(rejected and unchanged),
        detail=f"estado del giro={attempt.status.value if attempt else 'sin clic'}; "
        f"saldo servidor antes={before}, después={after}",
        status=_status(rejected and unchanged),
    )

    message = (screen.reading.message_raw if screen.reading else None) or outcome.insufficient_msg or ""
    runner.run_check(
        "S2.03", "Mensaje de saldo insuficiente visible",
        expected="Texto de mensaje no vacío", observed=message or "<vacío>",
        detail=f"Mensaje leído en pantalla: {message!r}", status=_status(bool(message.strip())),
    )
    check_language_keywords(runner, message, ctx.insufficient_keywords)
    runner.run_check(
        "S2.05", "Moneda mostrada = mercado",
        expected=ctx.currency_symbol, observed=screen.detail("currency"),
        detail=screen.detail("currency"), status=_tri_status(screen.matches("currency")),
    )
    check_balance_unchanged(runner, "S2.06", "Saldo in-game sin cambios", before, after)
    _visual_balance_check(runner, screen)
    check_balance_unchanged(runner, "S2.07", "Saldo Betsson sin cambios", outcome.balance_before, outcome.balance_after)


def _visual_balance_check(runner: CheckRunner, screen: ScreenVerification) -> None:
    verdict = screen.matches("balance")
    if verdict is None:
        runner.skip("S2.06v", "Saldo visible == saldo del servidor", screen.detail("balance"))
        return
    runner.run_check(
        "S2.06v", "Saldo visible == saldo del servidor",
        expected="pantalla == servidor", observed=screen.detail("balance"),
        detail=screen.detail("balance"), status=_status(verdict),
    )
