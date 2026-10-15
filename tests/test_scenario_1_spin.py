"""End-to-End Test for Scenario 1: Real Play Spin and Mathematical Reconciliation.

Validates the full cycle of real-money gameplay on Pragmatic Play slots across
both target markets:
- agent_com_s1 (betsson.com, EUR, English)
- agent_pe_s1 (betsson.pe, PEN, Spanish)

Checks verified: S1.01–S1.11 plus informative balance comparison.
"""

from __future__ import annotations

import pytest

from src.agents.sub_agent import SubAgentWorker
from src.models.schemas import AgentId, CheckStatus


@pytest.mark.e2e
@pytest.mark.parametrize(
    "agent_id",
    [AgentId.agent_com_s1, AgentId.agent_pe_s1],
    ids=["com_s1", "pe_s1"],
)
def test_scenario_1_spin(
    agent_id: AgentId,
    sub_agent_worker: SubAgentWorker,
) -> None:
    """Execute Scenario 1 Real Play spin and verify mathematical reconciliation."""
    report = sub_agent_worker.execute()

    # Ensure individual JSON report was written to disk
    expected_json = sub_agent_worker.artifacts_dir / f"result_{agent_id.value}.json"
    assert expected_json.exists(), f"Subagent report JSON was not created at {expected_json}"

    # Verify no unhandled execution error crashed the worker
    assert (
        report.overall != CheckStatus.ERROR
    ), f"Worker {agent_id.value} failed with an unhandled runtime error: {report.checks}"

    # Verify all soft checks passed
    failures = [c for c in report.checks if c.status == CheckStatus.FAIL]
    failure_details = "; ".join(f"{c.id} ({c.name}): {c.detail}" for c in failures)
    assert report.overall == CheckStatus.PASS, f"Checks failed for {agent_id.value}: {failure_details}"

