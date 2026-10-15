"""MasterOrchestrator: Coordinates parallel execution of the four SubAgentWorkers.

Handles:
- Parallel worker execution via ThreadPoolExecutor / asyncio.
- Account-level FileLock fallback to prevent concurrent logins on shared credentials (R2/R12).
- Gemini API shared rate-limiting semaphore.
- MasterReport aggregation and output of report.html, report.md, and master_report.json.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Iterator

from filelock import FileLock

from config.settings import get_settings
from src.agents.sub_agent import SubAgentWorker
from src.models.schemas import AgentId, MasterReport, SubAgentReport
from src.report.aggregator import (
    build_master_report,
    find_subagent_reports,
    generate_markdown_summary,
)
from src.report.html_report import generate_html_report

logger = logging.getLogger(__name__)


class AccountLockManager:
    """Manages file-based mutual exclusion locks per username.

    Used as fallback when two or more scenarios must share the same Betsson account,
    preventing concurrent logins and wallet balance race conditions (R2/R12).
    """

    def __init__(self, lock_dir: Path | str | None = None) -> None:
        """Initialize lock manager with a target lock directory."""
        self.lock_dir = Path(lock_dir) if lock_dir else Path("artifacts") / "locks"
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, FileLock] = {}
        self._mutex = threading.Lock()

    def _get_lock(self, username: str) -> FileLock:
        """Retrieve or create a FileLock for the given username."""
        safe_name = re.sub(r"[^\w\-_.]", "_", username.strip().lower())
        lock_file = self.lock_dir / f"{safe_name}.lock"
        with self._mutex:
            if safe_name not in self._locks:
                self._locks[safe_name] = FileLock(str(lock_file), timeout=60.0)
            return self._locks[safe_name]

    @contextmanager
    def acquire(self, username: str) -> Iterator[None]:
        """Context manager acquiring the account lock if a username is specified."""
        if not username or not username.strip():
            yield
            return

        lock = self._get_lock(username)
        logger.debug("Acquiring account lock for user: %s", username)
        with lock:
            logger.debug("Account lock acquired for user: %s", username)
            try:
                yield
            finally:
                logger.debug("Released account lock for user: %s", username)


class GeminiRateLimiter:
    """Shared concurrency limiter and delay throttler for Gemini API requests."""

    def __init__(self, max_concurrent: int = 3, min_interval_sec: float = 0.25) -> None:
        """Initialize rate limiter with concurrency capacity and pacing interval."""
        self.semaphore = threading.BoundedSemaphore(value=max_concurrent)
        self.min_interval_sec = min_interval_sec
        self._last_call_time = 0.0
        self._mutex = threading.Lock()

    @contextmanager
    def acquire(self) -> Iterator[None]:
        """Context manager enforcing concurrent slot capacity and request pacing."""
        with self.semaphore:
            with self._mutex:
                now = time.time()
                elapsed = now - self._last_call_time
                if elapsed < self.min_interval_sec:
                    time.sleep(self.min_interval_sec - elapsed)
                self._last_call_time = time.time()
            yield


class MasterOrchestrator:
    """Orchestrates parallel execution of all validation workers and consolidates outputs."""

    DEFAULT_AGENTS: list[AgentId] = [
        AgentId.agent_com_s1,
        AgentId.agent_com_s2,
        AgentId.agent_pe_s1,
        AgentId.agent_pe_s2,
    ]

    def __init__(
        self,
        artifacts_dir: Path | str = "artifacts",
        agents: list[AgentId | str] | None = None,
        max_workers: int = 4,
    ) -> None:
        """Initialize orchestrator with output path and target agent identifiers."""
        self.artifacts_dir = Path(artifacts_dir).resolve()
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers

        raw_agents = agents or self.DEFAULT_AGENTS
        self.agents = [
            a if isinstance(a, AgentId) else AgentId(str(a)) for a in raw_agents
        ]

        self.lock_manager = AccountLockManager(self.artifacts_dir / "locks")
        self.rate_limiter = GeminiRateLimiter()

    def run_worker(self, agent_id: AgentId) -> SubAgentReport:
        """Instantiate and execute a single SubAgentWorker with account locking."""
        settings = get_settings()
        creds = settings.get_credentials(agent_id) if settings.has_credentials(agent_id) else None
        username = creds.username if creds else ""
        password = creds.password if creds else ""

        worker_artifacts_dir = self.artifacts_dir / agent_id.value
        worker = SubAgentWorker(
            agent_id=agent_id,
            artifacts_dir=worker_artifacts_dir,
            username=username,
            password=password,
        )

        # Protect execution with account lock in case multiple workers share username
        with self.lock_manager.acquire(username):
            return worker.execute()

    def run_all(self) -> MasterReport:
        """Run all configured subagents in parallel and compile MasterReport."""
        logger.info(
            "Launching %d subagents in parallel (max_workers=%d)",
            len(self.agents),
            self.max_workers,
        )
        reports: list[SubAgentReport] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_agent = {
                executor.submit(self.run_worker, agent_id): agent_id
                for agent_id in self.agents
            }
            for future in as_completed(future_to_agent):
                agent_id = future_to_agent[future]
                try:
                    report = future.result()
                    reports.append(report)
                    logger.info("Subagent %s completed with status: %s", agent_id.value, report.overall.value)
                except Exception as exc:
                    logger.exception("Subagent %s failed execution: %s", agent_id.value, exc)

        # Sort reports consistently
        reports.sort(key=lambda r: r.agent_id.value)
        master_report = build_master_report(reports)
        self.save_reports(master_report)
        return master_report

    def aggregate_from_artifacts(self, search_dir: Path | None = None) -> MasterReport:
        """Aggregate existing result_*.json files into MasterReport without re-running."""
        target_dir = Path(search_dir) if search_dir else self.artifacts_dir
        reports = find_subagent_reports(target_dir)
        master_report = build_master_report(reports)
        self.save_reports(master_report)
        return master_report

    def save_reports(self, master_report: MasterReport) -> tuple[Path, Path, Path]:
        """Save master_report.json, report.html, and report.md in the artifacts directory."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        # 1. JSON
        json_path = self.artifacts_dir / "master_report.json"
        json_path.write_text(master_report.model_dump_json(indent=2), encoding="utf-8")

        # 2. HTML
        html_path = self.artifacts_dir / "report.html"
        html_content = generate_html_report(master_report)
        html_path.write_text(html_content, encoding="utf-8")

        # 3. Markdown
        md_path = self.artifacts_dir / "report.md"
        md_content = generate_markdown_summary(master_report)
        md_path.write_text(md_content, encoding="utf-8")

        logger.info("Saved Master Reports:\n - %s\n - %s\n - %s", json_path, html_path, md_path)
        return json_path, html_path, md_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MasterOrchestrator runner")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts directory path")
    parser.add_argument("--aggregate-only", action="store_true", help="Aggregate existing results without executing")
    args = parser.parse_args()

    orchestrator = MasterOrchestrator(artifacts_dir=args.artifacts_dir)
    if args.aggregate_only:
        report = orchestrator.aggregate_from_artifacts()
    else:
        report = orchestrator.run_all()

    print(f"Master Execution Finished: {report.total_pass} passed, {report.total_fail} failed, all_passed={report.all_passed}")

