"""Generate a SIMULATED results report to demonstrate how the system reports PASS and FAIL.

All data here is fictitious. What is real: the checks are the project's own S1.xx / S2.xx logic
(src/agents/networked_scenarios.py), so the failure shown in the report is detected by the
actual code, not typed in by hand. Default output: artifacts/SIMULADO_demo_report/ (gitignored); pass a folder to keep it in git.

Usage:  python scripts/simulate_report.py [output_dir]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from src.agents.networked_scenarios import ScenarioContext, evaluate_scenario_1, evaluate_scenario_2  # noqa: E402
from src.core.checks import CheckRunner  # noqa: E402
from src.flows.game_flow import SpinOutcome, SpinStatus  # noqa: E402
from src.models.schemas import AgentId, Market, SubAgentReport  # noqa: E402
from src.network.models import RoundResult, SpinAttempt, SpinAttemptStatus  # noqa: E402
from src.report.aggregator import build_master_report, generate_markdown_summary  # noqa: E402
from src.report.html_report import generate_html_report  # noqa: E402
from src.vision.grounding import GroundedScreenReading  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts") / "SIMULADO_demo_report"
BANNER = "SIMULACIÓN — DATOS FICTICIOS (no son resultados reales de Betsson)"
D = Decimal


class ScriptedVision:
    """Stands in for Gemini: returns what the (fictitious) screen 'shows'."""

    def __init__(self, reading: GroundedScreenReading) -> None:
        self.reading = reading

    def read_screen_grounded(self, screenshot: Path, reference_block: str) -> GroundedScreenReading:
        return self.reading


def _screenshot(path: Path, credit: str, bet: str, win: str, moving: bool, note: str = "") -> Path:
    """A fake slot screen so the evidence folder has real image files (clearly watermarked)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (960, 540), (24, 28, 52))
    d = ImageDraw.Draw(im)
    for col in range(5):
        for row in range(3):
            shade = (200 - 30 * ((col + row + moving) % 5), 90 + 20 * ((col * row + moving) % 6), 80)
            d.ellipse((140 + col * 130, 70 + row * 110, 220 + col * 130, 150 + row * 110), fill=shade)
    d.rectangle((0, 450, 960, 540), fill=(10, 10, 20))
    d.text((60, 470), f"CREDIT {credit}", fill=(255, 255, 255))
    d.text((400, 470), f"BET {bet}", fill=(255, 255, 255))
    d.text((700, 470), f"WIN {win}", fill=(255, 255, 255))
    if note:
        d.rectangle((250, 200, 710, 300), fill=(0, 0, 0), outline=(255, 80, 80))
        d.text((270, 240), note, fill=(255, 255, 255))
    d.text((20, 10), "SIMULADO - NO ES UNA CAPTURA REAL", fill=(255, 210, 0))
    im.save(path)
    return path


def _spin_round(before: str, after: str, bet: str = "0.20", win: str = "0.00") -> SpinAttempt:
    rnd = RoundResult(D(before), D(after), D(bet), D(win), False, True)
    return SpinAttempt(SpinAttemptStatus.SETTLED, round=rnd)


def _scenario_1(agent: str, market: str, symbol: str, evidence: Path, *, betsson_after: str,
                screen_credit: str, server_before="100.00", server_after="99.80") -> tuple[CheckRunner, ...]:
    pre = _screenshot(evidence / "1_antes_del_giro.png", f"{symbol}{server_before}", f"{symbol}0.20", "", False)
    post = _screenshot(evidence / "2_tras_liquidar_la_ronda.png", screen_credit, f"{symbol}0.20", "", True)
    attempt = _spin_round(server_before, server_after)
    outcome = SpinOutcome(
        status=SpinStatus.COMPLETED,
        balance_before=D(server_before), balance_after=D(betsson_after), bet_amount=D("0.20"),
        win_amount=D("0.00"), hud_credit_before=D(server_before), hud_credit_after=D(server_after),
        currency_observed=symbol, spin_attempt=attempt, network_round=attempt.round,
        screenshots=[pre, post], final_screenshot=post, server_balance_known=True,
    )
    reading = GroundedScreenReading(
        credit_raw=screen_credit, bet_raw=f"{symbol}0.20", win_raw=None, currency_raw=symbol, legible=True
    )
    runner = CheckRunner()
    keywords = ["insufficient", "funds"] if market == "com" else ["insuficiente", "fondos", "saldo"]
    evaluate_scenario_1(runner, outcome, ScenarioContext(market, symbol, keywords, ScriptedVision(reading)))
    return (runner,)


def _scenario_2(agent: str, market: str, symbol: str, evidence: Path, *, message: str, language: str) -> tuple[CheckRunner, ...]:
    pre = _screenshot(evidence / "1_antes_del_intento.png", f"{symbol}0.05", f"{symbol}0.20", "", False)
    post = _screenshot(evidence / "2_aviso_saldo_insuficiente.png", f"{symbol}0.05", f"{symbol}0.20", "", False, message[:42])
    outcome = SpinOutcome(
        status=SpinStatus.INSUFFICIENT_FUNDS,
        balance_before=D("0.05"), balance_after=D("0.05"), bet_amount=D("0.20"),
        hud_credit_before=D("0.05"), hud_credit_after=D("0.05"), currency_observed=symbol,
        spin_attempt=SpinAttempt(SpinAttemptStatus.NO_TRAFFIC), screenshots=[pre, post],
        final_screenshot=post, server_balance_known=True,
    )
    reading = GroundedScreenReading(
        credit_raw=f"{symbol}0.05", bet_raw=f"{symbol}0.20", currency_raw=symbol,
        message_raw=message, message_language=language, legible=True,
    )
    runner = CheckRunner()
    keywords = ["insufficient", "funds"] if market == "com" else ["insuficiente", "fondos", "saldo"]
    evaluate_scenario_2(runner, outcome, ScenarioContext(market, symbol, keywords, ScriptedVision(reading)))
    return (runner,)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    start = datetime.now(timezone.utc)
    cases = [
        # (agent id, market, scenario, runner)
        ("agent_com_s1", Market.COM, 1, _scenario_1("agent_com_s1", "com", "€", OUT / "agent_com_s1" / "evidence",
                                                     betsson_after="99.80", screen_credit="€99.80")[0]),
        ("agent_com_s2", Market.COM, 2, _scenario_2("agent_com_s2", "com", "€", OUT / "agent_com_s2" / "evidence",
                                                     message="Insufficient funds. Please deposit.", language="EN")[0]),
        # The failing case: the server debits the bet, but the HUD still shows the old balance
        # and the Betsson wallet was never debited -> the checks must catch it.
        ("agent_pe_s1", Market.PE, 1, _scenario_1("agent_pe_s1", "pe", "S/", OUT / "agent_pe_s1" / "evidence",
                                                   betsson_after="100.00", screen_credit="S/100.00",
                                                   server_before="100.00", server_after="99.80")[0]),
        ("agent_pe_s2", Market.PE, 2, _scenario_2("agent_pe_s2", "pe", "S/", OUT / "agent_pe_s2" / "evidence",
                                                   message="Saldo insuficiente. Por favor, recarga.", language="ES")[0]),
    ]
    reports = []
    for index, (agent, market, scenario, runner) in enumerate(cases):
        report = SubAgentReport(
            agent_id=AgentId(agent), market=market, scenario=scenario, checks=list(runner.results),
            evidence_dir=OUT / agent / "evidence", video_path=None,
            started_at=start + timedelta(seconds=index * 40), finished_at=start + timedelta(seconds=index * 40 + 38),
        )
        (OUT / agent).mkdir(parents=True, exist_ok=True)
        (OUT / agent / f"result_{agent}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        reports.append(report)

    master = build_master_report(reports)
    (OUT / "master_report.json").write_text(master.model_dump_json(indent=2), encoding="utf-8")
    (OUT / "report.html").write_text(
        generate_html_report(master, title=f"🧪 {BANNER} · Betsson Intelligent Game Validation"), encoding="utf-8"
    )
    (OUT / "report.md").write_text(f"> ⚠️ **{BANNER}**\n\n" + generate_markdown_summary(master), encoding="utf-8")
    log = master.write_log(OUT / "test_run.log")
    log.write_text(f"*** {BANNER} ***\n\n" + log.read_text(encoding="utf-8"), encoding="utf-8")

    failed = [(r.agent_id.value, c.id) for r in reports for c in r.checks if c.status.value in ("FAIL", "ERROR")]
    print(f"{BANNER}\nOutput: {OUT.resolve()}")
    print(f"agents={len(reports)} pass={master.total_pass} fail={master.total_fail} all_passed={master.all_passed}")
    print("detected failures:", json.dumps(failed))


if __name__ == "__main__":
    main()
