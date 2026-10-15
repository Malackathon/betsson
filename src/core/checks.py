"""Soft-check engine and domain check helpers for Betsson Game Validation.

Provides CheckRunner for non-blocking validation check recording across
Scenario 1 (Real Play Spin & Reconciliation) and Scenario 2 (Insufficient Funds).
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
import logging
from typing import Any

from src.core.money import parse_money, reconcile

try:
    from src.models.schemas import CheckResult, CheckStatus
except ImportError:  # pragma: no cover
    from enum import Enum
    from pydantic import BaseModel

    class CheckStatus(str, Enum):  # type: ignore[no-redef]
        """Status outcome of a validation check."""

        PASS = "PASS"
        FAIL = "FAIL"
        INFO = "INFO"
        ERROR = "ERROR"
        SKIP = "SKIP"

    class CheckResult(BaseModel):  # type: ignore[no-redef]
        """Result of an individual check."""

        id: str
        name: str
        expected: str | None = None
        observed: str | None = None
        detail: str | None = None
        status: CheckStatus

logger = logging.getLogger(__name__)


def _to_decimal(val: Decimal | str | Any) -> Decimal:
    """Coerce input to Decimal; parses strings via parse_money, forbids floats."""
    if isinstance(val, float):
        raise TypeError(f"Floating-point money values are forbidden: {val!r}")
    if isinstance(val, Decimal):
        return val
    if isinstance(val, str):
        return parse_money(val)
    return Decimal(str(val))


class CheckRunner:
    """Soft-check runner that accumulates check results without raising exceptions."""

    def __init__(self) -> None:
        """Initialize an empty check runner with no results."""
        self.results: list[CheckResult] = []

    def run(
        self,
        check_id: str,
        name: str,
        fn: Callable[[], tuple[str | None, str | None, str | None]],
    ) -> CheckResult:
        """Execute a check callable fn() returning (expected, observed, detail).

        - PASS if expected == observed (or expected is None).
        - ERROR with exception detail if fn() raises.
        - FAIL if expected != observed.
        """
        try:
            expected, observed, detail = fn()
            exp_str = str(expected) if expected is not None else None
            obs_str = str(observed) if observed is not None else None
            det_str = str(detail) if detail is not None else None

            status = CheckStatus.PASS if (exp_str is None or exp_str == obs_str) else CheckStatus.FAIL
            result = CheckResult(
                id=check_id,
                name=name,
                expected=exp_str,
                observed=obs_str,
                detail=det_str,
                status=status,
            )
        except Exception as exc:
            logger.warning("Check %s (%s) raised exception: %s", check_id, name, exc)
            result = CheckResult(
                id=check_id,
                name=name,
                expected=None,
                observed=None,
                detail=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
                status=CheckStatus.ERROR,
            )

        self.results.append(result)
        return result

    def run_check(
        self,
        check_id: str,
        name: str,
        *,
        expected: str | None,
        observed: str | None,
        detail: str | None = None,
        status: CheckStatus | None = None,
    ) -> CheckResult:
        """Directly record a check with expected and observed values."""
        exp_str = str(expected) if expected is not None else None
        obs_str = str(observed) if observed is not None else None
        det_str = str(detail) if detail is not None else None

        if status is None:
            resolved_status = (
                CheckStatus.PASS if (exp_str is None or exp_str == obs_str) else CheckStatus.FAIL
            )
        else:
            resolved_status = status

        result = CheckResult(
            id=check_id,
            name=name,
            expected=exp_str,
            observed=obs_str,
            detail=det_str,
            status=resolved_status,
        )
        self.results.append(result)
        return result

    def info(self, check_id: str, name: str, detail: str) -> CheckResult:
        """Record an informational check (always INFO status)."""
        result = CheckResult(
            id=check_id,
            name=name,
            expected=None,
            observed=None,
            detail=str(detail),
            status=CheckStatus.INFO,
        )
        self.results.append(result)
        return result

    def skip(self, check_id: str, name: str, reason: str) -> CheckResult:
        """Record a skipped check (always SKIP status)."""
        result = CheckResult(
            id=check_id,
            name=name,
            expected=None,
            observed=None,
            detail=str(reason),
            status=CheckStatus.SKIP,
        )
        self.results.append(result)
        return result

    @property
    def passed(self) -> bool:
        """Return True if there are no FAIL or ERROR checks."""
        return not any(r.status in (CheckStatus.FAIL, CheckStatus.ERROR) for r in self.results)

    @property
    def failed(self) -> bool:
        """Return True if any FAIL or ERROR check is present."""
        return not self.passed

    @property
    def failures(self) -> list[CheckResult]:
        """Return all failed or errored CheckResults."""
        return [r for r in self.results if r.status in (CheckStatus.FAIL, CheckStatus.ERROR)]

    def get_check(self, check_id: str) -> CheckResult | None:
        """Retrieve the first recorded CheckResult matching check_id."""
        return next((r for r in self.results if r.id == check_id), None)

    def summary(self) -> str:
        """Generate a human-readable summary of all recorded checks."""
        counts = {s: 0 for s in CheckStatus}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1

        overall = "PASSED" if self.passed else "FAILED"
        lines = [
            f"=== CheckRunner Summary [{overall}] ===",
            (
                f"Total: {len(self.results)} | "
                f"PASS: {counts[CheckStatus.PASS]} | "
                f"FAIL: {counts[CheckStatus.FAIL]} | "
                f"ERROR: {counts[CheckStatus.ERROR]} | "
                f"SKIP: {counts[CheckStatus.SKIP]} | "
                f"INFO: {counts[CheckStatus.INFO]}"
            ),
        ]
        for r in self.results:
            status_val = r.status.value if hasattr(r.status, "value") else str(r.status)
            parts = [f"  [{status_val:5}] {r.id}: {r.name}"]
            if r.expected is not None or r.observed is not None:
                parts.append(f"(expected={r.expected!r}, observed={r.observed!r})")
            if r.detail:
                parts.append(f"- {r.detail}")
            lines.append(" ".join(parts))
        return "\n".join(lines)

    def __len__(self) -> int:
        """Return the count of checks recorded."""
        return len(self.results)

    def __iter__(self):
        """Iterate over recorded CheckResults."""
        return iter(self.results)


def _reconcile_helper(
    runner: CheckRunner,
    check_id: str,
    name: str,
    before: Decimal,
    bet: Decimal,
    prize: Decimal,
    after: Decimal,
) -> CheckResult:
    """Internal helper to reconcile balance and emit CheckResult."""
    try:
        b = _to_decimal(before)
        bt = _to_decimal(bet)
        p = _to_decimal(prize)
        a = _to_decimal(after)

        expected_str = str(b - bt + p)
        observed_str = str(a)
        is_valid, detail = reconcile(b, bt, p, a)
        status = CheckStatus.PASS if is_valid else CheckStatus.FAIL
    except Exception as exc:
        expected_str = None
        observed_str = None
        detail = f"Reconciliation error: {exc}"
        status = CheckStatus.ERROR

    return runner.run_check(
        check_id=check_id,
        name=name,
        expected=expected_str,
        observed=observed_str,
        detail=detail,
        status=status,
    )


def reconcile_ingame_balance(
    runner: CheckRunner,
    before: Decimal,
    bet: Decimal,
    prize: Decimal,
    after: Decimal,
) -> CheckResult:
    """Validate in-game balance reconciliation using spin formula (check S1.09)."""
    return _reconcile_helper(
        runner=runner,
        check_id="S1.09",
        name="Saldo in-game reconcilia",
        before=before,
        bet=bet,
        prize=prize,
        after=after,
    )


def reconcile_betsson_balance(
    runner: CheckRunner,
    before: Decimal,
    bet: Decimal,
    prize: Decimal,
    after: Decimal,
) -> CheckResult:
    """Validate Betsson lobby balance reconciliation using spin formula (check S1.10)."""
    return _reconcile_helper(
        runner=runner,
        check_id="S1.10",
        name="Saldo Betsson reconcilia",
        before=before,
        bet=bet,
        prize=prize,
        after=after,
    )


def check_balance_unchanged(
    runner: CheckRunner,
    check_id: str,
    name: str,
    before: Decimal,
    after: Decimal,
) -> CheckResult:
    """Verify that balance remained unchanged for Scenario 2 checks (S2.06, S2.07)."""
    try:
        b = _to_decimal(before)
        a = _to_decimal(after)
        expected_str = str(b)
        observed_str = str(a)

        if b == a:
            status = CheckStatus.PASS
            detail = f"Balance unchanged: {b}"
        else:
            diff = a - b
            status = CheckStatus.FAIL
            detail = f"Balance changed: before={b}, after={a} (diff={diff})"
    except Exception as exc:
        expected_str = None
        observed_str = None
        detail = f"Balance check error: {exc}"
        status = CheckStatus.ERROR

    return runner.run_check(
        check_id=check_id,
        name=name,
        expected=expected_str,
        observed=observed_str,
        detail=detail,
        status=status,
    )


def check_language_keywords(
    runner: CheckRunner,
    message: str,
    keywords: list[str],
) -> CheckResult:
    """Verify error message contains expected language keywords (check S2.04)."""
    check_id = "S2.04"
    name = "Mensaje en el idioma del mercado"
    expected = f"any of: {keywords}"

    try:
        if not message or not isinstance(message, str) or not message.strip():
            return runner.run_check(
                check_id=check_id,
                name=name,
                expected=expected,
                observed="<empty>",
                detail="Warning message is empty or missing; cannot verify keywords",
                status=CheckStatus.FAIL,
            )

        msg_lower = message.lower()
        matched = [kw for kw in keywords if kw.lower() in msg_lower]

        if matched:
            status = CheckStatus.PASS
            observed = f"matched: {matched}"
            detail = f"Found keyword(s) {matched} in message: {message!r}"
        else:
            status = CheckStatus.FAIL
            observed = f"no match in: {message!r}"
            detail = f"None of keywords {keywords} found in message: {message!r}"
    except Exception as exc:
        observed = "<error>"
        detail = f"Keyword matching error: {exc}"
        status = CheckStatus.ERROR

    return runner.run_check(
        check_id=check_id,
        name=name,
        expected=expected,
        observed=observed,
        detail=detail,
        status=status,
    )


__all__ = [
    "CheckRunner",
    "check_balance_unchanged",
    "check_language_keywords",
    "reconcile_betsson_balance",
    "reconcile_ingame_balance",
]
