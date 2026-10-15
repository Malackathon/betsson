"""Pytest fixtures and hooks for Betsson Game Validation E2E test suite.

Provides:
- Worker-isolated artifact directories.
- Credentials loading with conditional skipping when secrets are missing or geoblocking occurs.
- Session finish hook compiling MasterReport, HTML report, and Markdown summary.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Generator

import pytest

from config.settings import Credentials, get_settings
from src.agents.sub_agent import SubAgentWorker
from src.models.schemas import AgentId, CheckStatus
from src.report.aggregator import (
    build_master_report,
    find_subagent_reports,
    generate_markdown_summary,
)
from src.report.html_report import generate_html_report

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def session_artifacts_dir() -> Path:
    """Return root artifacts directory and ensure it exists."""
    artifacts = Path("artifacts").resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    return artifacts


@pytest.fixture
def agent_artifacts_dir(request: pytest.FixtureRequest, session_artifacts_dir: Path) -> Path:
    """Return dedicated artifacts directory for the active agent."""
    agent_id_val = getattr(request, "param", None)
    if not agent_id_val and hasattr(request, "node"):
        # Extract from parametrized call if present
        for argname, argvalue in request.node.callspec.params.items():
            if "agent_id" in argname:
                agent_id_val = argvalue.value if hasattr(argvalue, "value") else str(argvalue)
                break

    agent_str = agent_id_val or "default_agent"
    agent_dir = session_artifacts_dir / agent_str
    agent_dir.mkdir(parents=True, exist_ok=True)
    return agent_dir


@pytest.fixture
def agent_credentials(request: pytest.FixtureRequest) -> Credentials:
    """Retrieve credentials for the agent and enforce conditional skip if unconfigured or geoblocked."""
    agent_id_val = None
    if hasattr(request, "node") and hasattr(request.node, "callspec"):
        for argname, argvalue in request.node.callspec.params.items():
            if "agent_id" in argname:
                agent_id_val = argvalue.value if hasattr(argvalue, "value") else str(argvalue)
                break

    if not agent_id_val:
        pytest.skip("No agent_id provided for credential check")

    # Conditional Skip: Geoblocking signal (R3)
    if os.getenv("BETSSON_GEOBLOCK_SKIP") == "1":
        pytest.skip(
            f"Skipping {agent_id_val}: BETSSON_GEOBLOCK_SKIP is enabled (Geoblock/antibot mitigation)"
        )

    settings = get_settings()
    # Conditional Skip: Missing or placeholder credentials
    if not settings.has_credentials(agent_id_val):
        pytest.skip(
            f"Skipping {agent_id_val}: Missing credentials in environment or .env for {agent_id_val}. "
            "Please configure BETSSON_*_USER/PASS secrets."
        )

    return settings.get_credentials(agent_id_val)


@pytest.fixture
def sub_agent_worker(
    request: pytest.FixtureRequest,
    agent_credentials: Credentials,
    agent_artifacts_dir: Path,
) -> SubAgentWorker:
    """Instantiate an isolated SubAgentWorker ready for execution."""
    agent_id_val = None
    if hasattr(request, "node") and hasattr(request.node, "callspec"):
        for argname, argvalue in request.node.callspec.params.items():
            if "agent_id" in argname:
                agent_id_val = argvalue
                break

    worker = SubAgentWorker(
        agent_id=agent_id_val,
        artifacts_dir=agent_artifacts_dir,
        username=agent_credentials.username,
        password=agent_credentials.password,
    )
    return worker


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Session finish hook: aggregate all sub-agent reports into MasterReport."""
    artifacts_dir = Path("artifacts").resolve()
    if not artifacts_dir.exists():
        return

    reports = find_subagent_reports(artifacts_dir)
    if not reports:
        logger.info("pytest_sessionfinish: No subagent reports found in %s", artifacts_dir)
        return

    master_report = build_master_report(reports)

    # 1. Save master_report.json
    json_path = artifacts_dir / "master_report.json"
    json_path.write_text(master_report.model_dump_json(indent=2), encoding="utf-8")

    # 2. Save report.html
    html_path = artifacts_dir / "report.html"
    html_path.write_text(generate_html_report(master_report), encoding="utf-8")

    # 3. Save report.md
    md_path = artifacts_dir / "report.md"
    md_path.write_text(generate_markdown_summary(master_report), encoding="utf-8")

    logger.info(
        "pytest_sessionfinish: Consolidated %d reports into %s and %s",
        len(reports),
        json_path,
        html_path,
    )

