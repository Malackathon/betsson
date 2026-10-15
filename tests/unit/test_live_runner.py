"""Wiring tests for the live path (no browser, no network, no Gemini)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents import live_runner
from src.agents.sub_agent import SubAgentWorker
from src.models.schemas import AgentId, CheckStatus
from src.vision.gemini_inspector import SpinButtonLocation


class FakeSpinInspector:
    def __init__(self, location: SpinButtonLocation) -> None:
        self.location = location
        self.calls: list[str] = []

    def locate_spin_button(self, screenshot, *, market: str = "") -> SpinButtonLocation:
        self.calls.append(market)
        return self.location


def test_spin_provider_returns_relative_coordinates_when_confident():
    inspector = FakeSpinInspector(SpinButtonLocation(x_pct=0.9, y_pct=0.8, confidence=0.9, legible=True))
    provider = live_runner.build_spin_provider(inspector, "com")

    assert provider(Path("shot.png")) == {"x": 0.9, "y": 0.8}
    assert inspector.calls == ["com"]


@pytest.mark.parametrize(
    "location",
    [
        SpinButtonLocation(x_pct=0.9, y_pct=0.8, confidence=0.2, legible=True),
        SpinButtonLocation(x_pct=0.9, y_pct=0.8, confidence=0.9, legible=False),
    ],
)
def test_spin_provider_raises_so_gameflow_uses_its_fallback(location):
    provider = live_runner.build_spin_provider(FakeSpinInspector(location), "pe")
    with pytest.raises(ValueError):
        provider(Path("shot.png"))


def test_live_worker_delegates_to_the_live_runner(tmp_path, monkeypatch):
    captured = {}

    def fake_run_live_scenario(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(live_runner, "run_live_scenario", fake_run_live_scenario)
    worker = SubAgentWorker(
        agent_id=AgentId.agent_pe_s2, artifacts_dir=tmp_path, username="u", password="p", live=True
    )

    report = worker.execute()

    assert captured["agent_id"] == "agent_pe_s2"
    assert captured["market"] == "pe"
    assert captured["scenario"] == 2
    assert captured["runner"] is worker.runner
    assert report.agent_id == AgentId.agent_pe_s2


def test_live_worker_reports_an_error_check_instead_of_crashing(tmp_path, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("browser exploded")

    monkeypatch.setattr(live_runner, "run_live_scenario", boom)
    worker = SubAgentWorker(agent_id=AgentId.agent_com_s1, artifacts_dir=tmp_path, live=True)

    report = worker.execute()

    assert report.overall is CheckStatus.ERROR
    assert "browser exploded" in report.checks[-1].observed


def test_non_live_worker_never_touches_the_live_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(live_runner, "run_live_scenario", lambda **kw: pytest.fail("live path used"))
    worker = SubAgentWorker(agent_id=AgentId.agent_com_s1, artifacts_dir=tmp_path)

    worker.execute()  # legacy protocol path with simulated adapters
