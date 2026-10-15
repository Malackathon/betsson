"""Motion detector for slot game spin lifecycle.

Detects spin start/end events by analyzing frame-to-frame pixel differences
in the reels region. Uses dynamic polling instead of fixed sleep timers.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

Frame = NDArray[np.uint8]  # H×W×3
FrameCapture = Callable[[], Frame]

# ---------------------------------------------------------------------------
# Configuration & result data-classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MotionConfig:
    """Configuration for motion detection thresholds and timing."""

    stability_threshold: float = 0.005       # max diff fraction considered "stable"
    stable_count_required: int = 3           # consecutive stable reads needed
    motion_start_threshold: float = 0.02     # min diff to consider "spin started"
    poll_interval: float = 0.15              # seconds between captures
    timeout: float = 30.0                    # max wait for any event
    baseline_duration: float = 2.0           # seconds of baseline sampling
    baseline_samples: int = 8                # number of baseline pairs


@dataclass
class MotionBaseline:
    """Baseline motion statistics captured at rest."""

    mean_level: float
    max_level: float
    std_level: float
    samples: int
    derived_start_threshold: float      # mean + 3σ or configured minimum
    derived_stability_threshold: float  # mean + 2σ or configured minimum


@dataclass
class SpinLifecycle:
    """Result of monitoring a complete spin cycle."""

    spin_started: bool
    spin_ended: bool
    start_time: float | None = None
    end_time: float | None = None
    spin_duration: float | None = None
    peak_motion: float = 0.0
    frames_analyzed: int = 0
    timed_out: bool = False


# ---------------------------------------------------------------------------
# Core motion helpers
# ---------------------------------------------------------------------------


def motion_level(frame_a: Frame, frame_b: Frame) -> float:
    """Normalized pixel difference in [0.0, 1.0].

    Computed as mean(|a − b|) / 255 across all pixels and channels.
    """
    if frame_a.shape != frame_b.shape:
        raise ValueError(f"Shape mismatch: {frame_a.shape} vs {frame_b.shape}")
    diff = np.abs(frame_a.astype(np.float64) - frame_b.astype(np.float64))
    return float(np.mean(diff) / 255.0)


def motion_level_region(
    frame_a: Frame,
    frame_b: Frame,
    *,
    top_pct: float = 0.15,
    bottom_pct: float = 0.85,
    left_pct: float = 0.05,
    right_pct: float = 0.95,
) -> float:
    """Motion level for a region (defaults to typical reels area)."""
    if frame_a.shape != frame_b.shape:
        raise ValueError(f"Shape mismatch: {frame_a.shape} vs {frame_b.shape}")

    h, w = frame_a.shape[:2]
    y1, y2 = int(h * max(0.0, min(top_pct, 1.0))), int(h * max(0.0, min(bottom_pct, 1.0)))
    x1, x2 = int(w * max(0.0, min(left_pct, 1.0))), int(w * max(0.0, min(right_pct, 1.0)))

    if y2 <= y1 or x2 <= x1:
        raise ValueError(
            f"Invalid region: top={top_pct}, bottom={bottom_pct}, "
            f"left={left_pct}, right={right_pct}"
        )
    return motion_level(frame_a[y1:y2, x1:x2], frame_b[y1:y2, x1:x2])


# ---------------------------------------------------------------------------
# Baseline calibration (R7)
# ---------------------------------------------------------------------------


def capture_baseline(
    capture_fn: FrameCapture,
    config: MotionConfig | None = None,
) -> MotionBaseline:
    """Sample motion at rest to establish dynamic thresholds (R7).

    Takes multiple frame pairs while the game is idle, measures inherent
    noise, and derives start/stability thresholds.
    """
    cfg = config or MotionConfig()
    n = max(cfg.baseline_samples, 2)
    interval = cfg.baseline_duration / n

    levels: list[float] = []
    prev: Frame = capture_fn()

    for _ in range(n):
        _poll_wait(interval)
        cur: Frame = capture_fn()
        levels.append(motion_level_region(prev, cur))
        prev = cur

    arr = np.array(levels, dtype=np.float64)
    mean_lvl, max_lvl, std_lvl = float(np.mean(arr)), float(np.max(arr)), float(np.std(arr))

    baseline = MotionBaseline(
        mean_level=mean_lvl,
        max_level=max_lvl,
        std_level=std_lvl,
        samples=len(levels),
        derived_start_threshold=max(cfg.motion_start_threshold, mean_lvl + 3.0 * std_lvl),
        derived_stability_threshold=max(cfg.stability_threshold, mean_lvl + 2.0 * std_lvl),
    )
    logger.info(
        "Baseline: mean=%.5f max=%.5f std=%.5f start_thr=%.5f stable_thr=%.5f (%d samples)",
        *[baseline.mean_level, baseline.max_level, baseline.std_level,
          baseline.derived_start_threshold, baseline.derived_stability_threshold,
          baseline.samples],
    )
    return baseline


# ---------------------------------------------------------------------------
# Polling-based wait helpers
# ---------------------------------------------------------------------------


def wait_until_motion(
    capture_fn: FrameCapture,
    *,
    threshold: float | None = None,
    config: MotionConfig | None = None,
    baseline: MotionBaseline | None = None,
) -> tuple[bool, float]:
    """Wait until motion exceeds threshold (spin-started signal).

    Returns ``(detected, peak_motion)``.
    """
    cfg = config or MotionConfig()
    thr = _resolve_start_threshold(threshold, baseline, cfg)
    logger.debug("wait_until_motion: thr=%.5f timeout=%.1fs", thr, cfg.timeout)

    prev: Frame = capture_fn()
    peak = 0.0
    deadline = time.monotonic() + cfg.timeout

    while time.monotonic() < deadline:
        _poll_wait(cfg.poll_interval)
        cur = capture_fn()
        level = motion_level_region(prev, cur)
        peak = max(peak, level)
        if level >= thr:
            logger.info("Motion detected: level=%.5f (thr=%.5f)", level, thr)
            return True, peak
        prev = cur

    logger.warning("wait_until_motion timed out (peak=%.5f, thr=%.5f)", peak, thr)
    return False, peak


def wait_until_stable(
    capture_fn: FrameCapture,
    *,
    threshold: float | None = None,
    config: MotionConfig | None = None,
    baseline: MotionBaseline | None = None,
) -> tuple[bool, int]:
    """Wait until motion stays below threshold for consecutive readings.

    Returns ``(stabilized, frames_analyzed)``.
    """
    cfg = config or MotionConfig()
    thr = _resolve_stability_threshold(threshold, baseline, cfg)
    logger.debug("wait_until_stable: thr=%.5f req=%d timeout=%.1fs",
                 thr, cfg.stable_count_required, cfg.timeout)

    prev: Frame = capture_fn()
    streak = 0
    frames = 0
    deadline = time.monotonic() + cfg.timeout

    while time.monotonic() < deadline:
        _poll_wait(cfg.poll_interval)
        cur = capture_fn()
        level = motion_level_region(prev, cur)
        frames += 1

        if level < thr:
            streak += 1
            if streak >= cfg.stable_count_required:
                logger.info("Stabilized after %d frames (thr=%.5f)", frames, thr)
                return True, frames
        else:
            streak = 0
        prev = cur

    logger.warning("wait_until_stable timed out (%d frames, streak=%d)", frames, streak)
    return False, frames


# ---------------------------------------------------------------------------
# Full spin lifecycle monitor
# ---------------------------------------------------------------------------


def monitor_spin_lifecycle(
    capture_fn: FrameCapture,
    *,
    config: MotionConfig | None = None,
    baseline: MotionBaseline | None = None,
) -> SpinLifecycle:
    """Monitor a complete spin: detect start → wait for end.

    Phase 1: Wait for motion spike (reels spinning).
    Phase 2: Wait for stabilisation (reels stopped, HUD readable).
    """
    cfg = config or MotionConfig()

    # Phase 1
    logger.info("Phase 1: waiting for spin to start…")
    detected, peak = wait_until_motion(capture_fn, config=cfg, baseline=baseline)
    if not detected:
        return SpinLifecycle(spin_started=False, spin_ended=False,
                             peak_motion=peak, timed_out=True)

    start_ts = time.monotonic()

    # Phase 2
    logger.info("Phase 2: waiting for reels to stabilise…")
    stable, n_frames = wait_until_stable(capture_fn, config=cfg, baseline=baseline)
    end_ts = time.monotonic()
    duration = end_ts - start_ts

    lifecycle = SpinLifecycle(
        spin_started=True,
        spin_ended=stable,
        start_time=start_ts,
        end_time=end_ts if stable else None,
        spin_duration=duration if stable else None,
        peak_motion=peak,
        frames_analyzed=n_frames,
        timed_out=not stable,
    )
    if stable:
        logger.info("Spin complete: %.2fs, peak=%.5f, %d frames", duration, peak, n_frames)
    else:
        logger.warning("Spin started but stabilisation timed out (%.2fs, %d frames)", duration, n_frames)
    return lifecycle


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _poll_wait(seconds: float) -> None:
    """Wait using monotonic clock. Sleeps most of the interval, then spin-waits."""
    target = time.monotonic() + seconds
    if seconds > 0.05:
        time.sleep(max(0.0, seconds - 0.01))
    while time.monotonic() < target:
        pass


def _resolve_start_threshold(
    explicit: float | None, baseline: MotionBaseline | None, config: MotionConfig,
) -> float:
    if explicit is not None:
        return explicit
    if baseline is not None:
        return baseline.derived_start_threshold
    return config.motion_start_threshold


def _resolve_stability_threshold(
    explicit: float | None, baseline: MotionBaseline | None, config: MotionConfig,
) -> float:
    if explicit is not None:
        return explicit
    if baseline is not None:
        return baseline.derived_stability_threshold
    return config.stability_threshold
