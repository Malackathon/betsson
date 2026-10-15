"""Reporting package for Betsson Game Validation.

Provides autonomous HTML reporting, Markdown summary generation, evidence collection,
and sub-agent report aggregation.
"""

from src.report.aggregator import (
    build_master_report,
    find_subagent_reports,
    generate_markdown_summary,
    load_subagent_report,
)
from src.report.evidence import record_evidence_screenshot, sanitize_filename
from src.report.html_report import generate_html_report

__all__ = [
    "build_master_report",
    "find_subagent_reports",
    "generate_html_report",
    "generate_markdown_summary",
    "load_subagent_report",
    "record_evidence_screenshot",
    "sanitize_filename",
]
