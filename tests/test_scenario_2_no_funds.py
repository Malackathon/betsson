"""End-to-End Test for Scenario 2: Insufficient Funds Rejection and Language Validation.

Validates that attempting a spin without adequate funds properly triggers
the insufficient balance warning modal and does not deduct balance across
both target markets:
- agent_com_s2 (betsson.com, EUR, English warning)
- agent_pe_s2 (betsson.pe, PEN, Spanish warning)

Checks verified: S2.01–S2.07.
"""

from __future__ import annotations

import pytest

from src.agents.sub_agent import SubAgentWorker
from src.models.schemas import AgentId, CheckStatus


@pytest.mark.e2e
@pytest.mark.parametrize(
    "agent_id",
    [AgentId.agent_com_s2, AgentId.agent_pe_s2],
    ids=["com_s2", "pe_s2"],
)
def test_scenario_2_no_funds(
    agent_id: AgentId,
    sub_agent_worker: SubAgentWorker,
) -> None:
    """Execute Scenario 2 insufficient funds spin attempt and verify rejection."""
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

