"""Aggregator for sub-agent execution reports and Markdown summary generator.

Discovers result_{agent_id}.json reports across artifacts/ directories, parses them
into SubAgentReport instances, builds a consolidated MasterReport, and outputs
both JSON and GitHub-flavored Markdown summaries.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.models.schemas import CheckResult, CheckStatus, MasterReport, SubAgentReport

logger = logging.getLogger(__name__)


def load_subagent_report(report_path: Path) -> SubAgentReport:
    """Load and validate a SubAgentReport from a JSON file."""
    content = report_path.read_text(encoding="utf-8")
    return SubAgentReport.model_validate_json(content)


def find_subagent_reports(artifacts_dir: Path) -> list[SubAgentReport]:
    """Scan directory recursively for result_*.json files and load SubAgentReports."""
    reports: list[SubAgentReport] = []
    if not artifacts_dir.exists():
        return reports

    # Search for result_*.json files in both direct root and nested subdirectories
    json_paths = sorted(list(artifacts_dir.glob("**/result_*.json")))
    seen_agents: set[str] = set()

    for path in json_paths:
        try:
            report = load_subagent_report(path)
            # Avoid duplicate reports if found in multiple locations
            if report.agent_id.value not in seen_agents:
                seen_agents.add(report.agent_id.value)
                reports.append(report)
        except Exception as exc:
            logger.warning("Failed to parse report file %s: %s", path, exc)

    # Sort stably by agent_id
    reports.sort(key=lambda r: r.agent_id.value)
    return reports


def build_master_report(reports: list[SubAgentReport]) -> MasterReport:
    """Construct a MasterReport consolidating all provided SubAgentReports."""
    return MasterReport(reports=reports)


def generate_markdown_summary(master_report: MasterReport) -> str:
    """Format MasterReport into a rich GitHub-Flavored Markdown summary for CI and logs."""
    total_agents = len(master_report.reports)
    total_pass = master_report.total_pass
    total_fail = master_report.total_fail
    all_passed = master_report.all_passed

    overall_badge = "✅ **PASSED**" if all_passed else "❌ **FAILED**"
    if total_agents == 0:
        overall_badge = "⚠️ **NO REPORTS COLLECTED**"

    lines: list[str] = [
        "# 🎰 Betsson Intelligent Game Validation — E2E Master Report",
        "",
        f"**Overall Status:** {overall_badge}  ",
        f"**Sub-Agents Executed:** `{total_agents}` | "
        f"**Total Passed Checks:** `{total_pass}` | "
        f"**Total Failed Checks:** `{total_fail}`  ",
        "",
        "---",
        "",
        "## 📊 Sub-Agents Execution Summary",
        "",
        "| Sub-Agent | Market | Scenario | Overall | Total Checks | Pass | Fail | Video |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|",
    ]

    for report in master_report.reports:
        agent_id_str = report.agent_id.value
        market_str = report.market.value
        scenario_str = f"S{report.scenario}"
        overall_val = report.overall.value

        status_emoji = {
            CheckStatus.PASS: "🟢 PASS",
            CheckStatus.FAIL: "🔴 FAIL",
            CheckStatus.ERROR: "🟠 ERROR",
            CheckStatus.SKIP: "⚪ SKIP",
            CheckStatus.INFO: "🔵 INFO",
        }.get(report.overall, overall_val)

        c_pass = sum(1 for c in report.checks if c.status == CheckStatus.PASS)
        c_fail = sum(1 for c in report.checks if c.status == CheckStatus.FAIL)
        total_c = len(report.checks)
        video_info = f"`{report.video_path.name}`" if report.video_path else "_None_"

        lines.append(
            f"| `{agent_id_str}` | **{market_str}** | **{scenario_str}** | {status_emoji} | {total_c} | {c_pass} | {c_fail} | {video_info} |"
        )

    lines.extend(["", "---", "", "## 🔍 Detailed Checks Breakdown", ""])

    for report in master_report.reports:
        agent_id_str = report.agent_id.value
        scenario_desc = (
            "Scenario 1 (Real Play Spin & Math Reconciliation)"
            if report.scenario == 1
            else "Scenario 2 (Insufficient Funds Rejection & Language)"
        )
        lines.append(f"### 🤖 `{agent_id_str}` — {report.market.value} ({scenario_desc})")
        lines.append("")
        lines.append("| Check ID | Name | Status | Expected | Observed | Detail |")
        lines.append("|:---|:---|:---:|:---|:---|:---|")

        for c in report.checks:
            icon = {
                CheckStatus.PASS: "✅ PASS",
                CheckStatus.FAIL: "❌ FAIL",
                CheckStatus.ERROR: "⚠️ ERROR",
                CheckStatus.SKIP: "⏭️ SKIP",
                CheckStatus.INFO: "ℹ️ INFO",
            }.get(c.status, str(c.status))

            exp_val = f"`{c.expected}`" if c.expected is not None else "_None_"
            obs_val = f"`{c.observed}`" if c.observed is not None else "_None_"
            det_val = (c.detail or "").replace("|", "\\|").replace("\n", " ")

            lines.append(f"| **{c.id}** | {c.name} | {icon} | {exp_val} | {obs_val} | {det_val} |")

        lines.append("")

    lines.extend([
        "---",
        "*Report generated automatically by Antigravity Betsson Intelligent Game Validation E2E Orchestrator.*",
    ])

    return "\n".join(lines)

