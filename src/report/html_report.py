"""Autonomous HTML report generator for Betsson Intelligent Game Validation.

Generates self-contained, standalone report.html files without external CDN dependencies
or third-party network assets, ensuring strict offline functionality and fast rendering.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from src.models.schemas import CheckResult, CheckStatus, MasterReport, SubAgentReport


def _badge_html(status: CheckStatus | str) -> str:
    """Return an inline styled HTML badge for a check status."""
    raw_status = status.value if hasattr(status, "value") else str(status)
    color_map = {
        "PASS": ("#10b981", "#ecfdf5", "PASS"),
        "FAIL": ("#ef4444", "#fef2f2", "FAIL"),
        "ERROR": ("#f59e0b", "#fffbeb", "ERROR"),
        "INFO": ("#3b82f6", "#eff6ff", "INFO"),
        "SKIP": ("#6b7280", "#f3f4f6", "SKIP"),
    }
    border_color, bg_color, label = color_map.get(raw_status.upper(), ("#6b7280", "#f3f4f6", raw_status))
    return (
        f'<span style="display:inline-block; padding: 2px 8px; font-size: 11px; font-weight: 700; '
        f'border-radius: 9999px; color: {border_color}; background-color: {bg_color}; '
        f'border: 1px solid {border_color};">{html.escape(label)}</span>'
    )


def generate_html_report(
    master_report: MasterReport,
    title: str = "Betsson Intelligent Game Validation — E2E Master Report",
) -> str:
    """Generate self-contained HTML report string from a MasterReport."""
    total_agents = len(master_report.reports)
    total_pass = master_report.total_pass
    total_fail = master_report.total_fail
    all_passed = master_report.all_passed

    overall_label = "ALL CHECKS PASSED" if all_passed else ("FAILED CHECKS DETECTED" if total_agents > 0 else "NO DATA")
    overall_color = "#10b981" if all_passed else ("#ef4444" if total_agents > 0 else "#f59e0b")
    overall_bg = "#ecfdf5" if all_passed else ("#fef2f2" if total_agents > 0 else "#fffbeb")

    # Build Agent Cards and Tables HTML
    agent_cards_html: list[str] = []
    agent_tables_html: list[str] = []

    for report in master_report.reports:
        agent_id_str = report.agent_id.value
        market_str = report.market.value
        scenario_num = report.scenario
        scenario_title = "Scenario 1: Spin Real + Reconciliación" if scenario_num == 1 else "Scenario 2: Saldo Insuficiente"
        duration_sec = (report.finished_at - report.started_at).total_seconds()

        c_pass = sum(1 for c in report.checks if c.status == CheckStatus.PASS)
        c_fail = sum(1 for c in report.checks if c.status == CheckStatus.FAIL)
        c_err = sum(1 for c in report.checks if c.status == CheckStatus.ERROR)
        c_skip = sum(1 for c in report.checks if c.status == CheckStatus.SKIP)
        c_info = sum(1 for c in report.checks if c.status == CheckStatus.INFO)

        card_status_badge = _badge_html(report.overall)

        # Overview card for this agent
        agent_cards_html.append(f"""
        <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-weight: 700; font-size: 14px; color: #111827;">{html.escape(agent_id_str)}</span>
                {card_status_badge}
            </div>
            <div style="font-size: 12px; color: #4b5563; margin-bottom: 12px;">
                <strong>Market:</strong> {html.escape(market_str)} | <strong>Scenario:</strong> {scenario_num}
            </div>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; text-align: center; background: #f9fafb; padding: 8px; border-radius: 6px; font-size: 12px;">
                <div><div style="color: #10b981; font-weight: 700;">{c_pass}</div><div style="color: #6b7280; font-size: 10px;">PASS</div></div>
                <div><div style="color: #ef4444; font-weight: 700;">{c_fail}</div><div style="color: #6b7280; font-size: 10px;">FAIL</div></div>
                <div><div style="color: #4b5563; font-weight: 700;">{duration_sec:.1f}s</div><div style="color: #6b7280; font-size: 10px;">TIME</div></div>
            </div>
        </div>
        """)

        # Detailed Check Rows for this agent
        check_rows: list[str] = []
        for c in report.checks:
            badge = _badge_html(c.status)
            exp = html.escape(c.expected or "-")
            obs = html.escape(c.observed or "-")
            det = html.escape(c.detail or "-")

            check_rows.append(f"""
            <tr style="border-bottom: 1px solid #f3f4f6; font-size: 12px;">
                <td style="padding: 10px; font-weight: 600; color: #111827;">{html.escape(c.id)}</td>
                <td style="padding: 10px; color: #374151;">{html.escape(c.name)}</td>
                <td style="padding: 10px; text-align: center;">{badge}</td>
                <td style="padding: 10px; font-family: monospace; color: #4b5563;">{exp}</td>
                <td style="padding: 10px; font-family: monospace; color: #4b5563;">{obs}</td>
                <td style="padding: 10px; color: #6b7280;">{det}</td>
            </tr>
            """)

        video_markup = (
            f'<div style="font-size: 12px; margin-top: 8px; color: #2563eb;">🎥 Video: <code>{html.escape(report.video_path.name)}</code></div>'
            if report.video_path
            else '<div style="font-size: 12px; margin-top: 8px; color: #9ca3af;">🎥 Video: <em>None captured</em></div>'
        )

        agent_tables_html.append(f"""
        <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 24px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <div style="background: #f9fafb; padding: 12px 16px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h3 style="margin: 0; font-size: 15px; color: #111827;">
                        🤖 <code>{html.escape(agent_id_str)}</code> &mdash; {html.escape(market_str)} ({html.escape(scenario_title)})
                    </h3>
                    {video_markup}
                </div>
                <div>{card_status_badge}</div>
            </div>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; text-align: left;">
                    <thead>
                        <tr style="background: #fdfdfd; border-bottom: 2px solid #e5e7eb; font-size: 11px; text-transform: uppercase; color: #6b7280; letter-spacing: 0.05em;">
                            <th style="padding: 8px 10px; width: 80px;">ID</th>
                            <th style="padding: 8px 10px;">Check Name</th>
                            <th style="padding: 8px 10px; text-align: center; width: 70px;">Status</th>
                            <th style="padding: 8px 10px;">Expected</th>
                            <th style="padding: 8px 10px;">Observed</th>
                            <th style="padding: 8px 10px;">Detail</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(check_rows)}
                    </tbody>
                </table>
            </div>
        </div>
        """)

    cards_joined = "".join(agent_cards_html)
    tables_joined = "".join(agent_tables_html)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f3f4f6;
            margin: 0;
            padding: 24px;
            color: #111827;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header Banner -->
        <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px; margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.05);">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px;">
                <div>
                    <h1 style="margin: 0 0 6px 0; font-size: 22px; color: #111827;">{html.escape(title)}</h1>
                    <p style="margin: 0; color: #6b7280; font-size: 13px;">
                        Automated Multimodal Playwright & Gemini Vision Test Execution
                    </p>
                </div>
                <div style="padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 13px; color: {overall_color}; background-color: {overall_bg}; border: 1px solid {overall_color};">
                    {overall_label}
                </div>
            </div>

            <!-- Metric Cards -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-top: 20px;">
                <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; text-align: center;">
                    <div style="font-size: 24px; font-weight: 700; color: #111827;">{total_agents}</div>
                    <div style="font-size: 11px; text-transform: uppercase; color: #6b7280;">Sub-Agents</div>
                </div>
                <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; text-align: center;">
                    <div style="font-size: 24px; font-weight: 700; color: #10b981;">{total_pass}</div>
                    <div style="font-size: 11px; text-transform: uppercase; color: #6b7280;">Checks Passed</div>
                </div>
                <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; text-align: center;">
                    <div style="font-size: 24px; font-weight: 700; color: #ef4444;">{total_fail}</div>
                    <div style="font-size: 11px; text-transform: uppercase; color: #6b7280;">Checks Failed</div>
                </div>
            </div>
        </div>

        <!-- Sub-Agent Overview Cards -->
        <h2 style="font-size: 16px; font-weight: 700; color: #374151; margin-bottom: 12px;">Sub-Agents Matrix</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 24px;">
            {cards_joined}
        </div>

        <!-- Detailed Tables Breakdown -->
        <h2 style="font-size: 16px; font-weight: 700; color: #374151; margin-bottom: 12px;">Detailed Soft Checks Results</h2>
        {tables_joined}

        <footer style="text-align: center; margin-top: 32px; font-size: 12px; color: #9ca3af;">
            Generated by Antigravity Betsson Challenge Orchestrator &mdash; Strictly Zero External CDNs
        </footer>
    </div>
</body>
</html>
"""
    return html_content

