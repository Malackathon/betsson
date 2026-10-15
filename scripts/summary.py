#!/usr/bin/env python3
"""Summary script for GitHub Actions Step Summary.

Consolidates sub-agent JSON reports (result_{agent_id}.json) from the artifacts directory,
generates a comprehensive Markdown summary, and writes it to $GITHUB_STEP_SUMMARY
and/or an output file.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.models.schemas import MasterReport
from src.report.aggregator import (
    build_master_report,
    find_subagent_reports,
    generate_markdown_summary,
)


def main() -> int:
    """CLI entrypoint to consolidate reports and write to $GITHUB_STEP_SUMMARY."""
    parser = argparse.ArgumentParser(
        description="Consolidate sub-agent reports into GitHub Step Summary Markdown"
    )
    parser.add_argument(
        "--artifacts-dir",
        default="artifacts",
        help="Path to the directory containing execution artifacts (default: artifacts)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional file path to write Markdown summary output to",
    )
    args = parser.parse_args()

    artifacts_path = Path(args.artifacts_dir).resolve()
    reports = find_subagent_reports(artifacts_path)

    master_report = build_master_report(reports)
    markdown_content = generate_markdown_summary(master_report)

    # 1. Output to stdout
    try:
        print(markdown_content)
    except UnicodeEncodeError:
        print(markdown_content.encode("ascii", errors="replace").decode("ascii"))

    # 2. Write to custom output file if requested
    if args.output:
        out_file = Path(args.output).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(markdown_content, encoding="utf-8")
        print(f"\n[summary] Written to: {out_file}", file=sys.stderr)

    # 3. Write to $GITHUB_STEP_SUMMARY if available in CI environment
    step_summary_env = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary_env:
        step_summary_path = Path(step_summary_env)
        with step_summary_path.open("a", encoding="utf-8") as f:
            f.write("\n" + markdown_content + "\n")
        print(f"[summary] Appended to GITHUB_STEP_SUMMARY: {step_summary_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
