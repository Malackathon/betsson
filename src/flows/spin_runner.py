"""Click Spin, wait for the SERVER to settle the round, then capture the screen.

The arrival of the settling response is the exact trigger for the final screenshot,
so the picture is taken when the game has actually finished (not after a fixed sleep).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.network.models import SpinAttempt, SpinAttemptStatus
from src.network.monitor import DEFAULT_ROUND_TIMEOUT_S, NetworkMonitor

logger = logging.getLogger(__name__)

DEFAULT_POST_SETTLE_MS = 1200  # lets the on-screen WIN/CREDIT counters finish animating
DEFAULT_MAX_BONUS_RETRIES = 3
FINAL_SHOT_NAME = "final_after_round"


class SpinCanvas(Protocol):
    """The slice of GameCanvas the runner needs."""

    def click_spin(self, spin_coords: Any) -> None: ...

    def take_game_screenshot(self, name: str) -> Path: ...


@dataclass(frozen=True)
class SpinRun:
    attempt: SpinAttempt
    final_screenshot: Path | None
    bonus_retries: int


def run_spin_with_bonus_retry(
    canvas: SpinCanvas,
    monitor: NetworkMonitor,
    spin_coords: Any,
    *,
    round_timeout_s: float = DEFAULT_ROUND_TIMEOUT_S,
    post_settle_ms: int = DEFAULT_POST_SETTLE_MS,
    max_bonus_retries: int = DEFAULT_MAX_BONUS_RETRIES,
) -> SpinRun:
    """Spin until a clean (non-bonus) round, a rejection, or the retry budget is spent (R8)."""
    bonus_retries = 0
    attempts_made = 0
    while True:
        attempts_made += 1
        attempt, shot = _single_spin(canvas, monitor, spin_coords, round_timeout_s, post_settle_ms)
        bonus = attempt.status is SpinAttemptStatus.SETTLED and attempt.round and attempt.round.bonus_triggered
        if not bonus or attempts_made >= max_bonus_retries:
            return SpinRun(attempt, shot, bonus_retries)
        bonus_retries += 1
        logger.info("Bonus/free spins triggered (attempt %d); spinning again (R8)", attempts_made)


def _single_spin(
    canvas: SpinCanvas,
    monitor: NetworkMonitor,
    spin_coords: Any,
    round_timeout_s: float,
    post_settle_ms: int,
) -> tuple[SpinAttempt, Path | None]:
    mark = monitor.mark()
    canvas.click_spin(spin_coords)
    attempt = monitor.wait_for_round(mark, timeout_s=round_timeout_s)
    if post_settle_ms > 0:
        time.sleep(post_settle_ms / 1000)
    return attempt, canvas.take_game_screenshot(FINAL_SHOT_NAME)
