"""Unit tests for src.vision.motion_detector.

Uses synthetic frame generators without external dependencies or network.
"""

from __future__ import annotations

import time
import numpy as np
import pytest

from src.vision.motion_detector import (
    Frame,
    MotionBaseline,
    MotionConfig,
    SpinLifecycle,
    capture_baseline,
    monitor_spin_lifecycle,
    motion_level,
    motion_level_region,
    wait_until_motion,
    wait_until_stable,
)


def _make_frame(h: int = 100, w: int = 100, val: int = 128) -> Frame:
    """Create a solid uint8 frame."""
    return np.full((h, w, 3), val, dtype=np.uint8)


class TestMotionLevel:
    def test_identical_frames_zero_motion(self) -> None:
        f1 = _make_frame(100, 100, 100)
        f2 = _make_frame(100, 100, 100)
        assert motion_level(f1, f2) == 0.0

    def test_max_diff_frames_one_motion(self) -> None:
        f1 = _make_frame(10, 10, 0)
        f2 = _make_frame(10, 10, 255)
        assert pytest.approx(motion_level(f1, f2), rel=1e-4) == 1.0

    def test_shape_mismatch_raises(self) -> None:
        f1 = _make_frame(10, 10)
        f2 = _make_frame(20, 20)
        with pytest.raises(ValueError, match="mismatch"):
            motion_level(f1, f2)


class TestMotionLevelRegion:
    def test_region_motion_detected(self) -> None:
        f1 = _make_frame(100, 100, 0)
        f2 = _make_frame(100, 100, 0)
        # Modify only the center region (y: 20-80, x: 20-80)
        f2[20:80, 20:80, :] = 255

        lvl_reels = motion_level_region(
            f1, f2, top_pct=0.2, bottom_pct=0.8, left_pct=0.2, right_pct=0.8
        )
        assert pytest.approx(lvl_reels, rel=1e-4) == 1.0

        # Non-modified region
        lvl_top = motion_level_region(
            f1, f2, top_pct=0.0, bottom_pct=0.1, left_pct=0.0, right_pct=1.0
        )
        assert lvl_top == 0.0

    def test_invalid_region_raises(self) -> None:
        f1 = _make_frame(50, 50)
        with pytest.raises(ValueError, match="Invalid region"):
            motion_level_region(f1, f1, top_pct=0.8, bottom_pct=0.2)


class TestCaptureBaseline:
    def test_baseline_calculation(self) -> None:
        # Static stream with small noise
        counter = 0

        def capture_stream() -> Frame:
            nonlocal counter
            counter += 1
            # alternating small delta
            val = 100 + (counter % 2) * 2
            return _make_frame(60, 60, val)

        cfg = MotionConfig(baseline_duration=0.1, baseline_samples=4)
        baseline = capture_baseline(capture_stream, config=cfg)

        assert isinstance(baseline, MotionBaseline)
        assert baseline.samples == 4
        assert baseline.derived_start_threshold >= cfg.motion_start_threshold
        assert baseline.derived_stability_threshold >= cfg.stability_threshold


class TestWaitHelpers:
    def test_wait_until_motion_detected(self) -> None:
        step = 0

        def stream() -> Frame:
            nonlocal step
            step += 1
            val = 255 if step >= 3 else 0
            return _make_frame(40, 40, val)

        cfg = MotionConfig(poll_interval=0.01, timeout=1.0, motion_start_threshold=0.1)
        detected, peak = wait_until_motion(stream, config=cfg)
        assert detected is True
        assert peak > 0.5

    def test_wait_until_motion_timeout(self) -> None:
        f = _make_frame(40, 40, 100)
        cfg = MotionConfig(poll_interval=0.01, timeout=0.05, motion_start_threshold=0.1)
        detected, peak = wait_until_motion(lambda: f, config=cfg)
        assert detected is False
        assert peak == 0.0

    def test_wait_until_stable_success(self) -> None:
        step = 0

        def stream() -> Frame:
            nonlocal step
            step += 1
            # High motion first 2 frames, then constant
            val = (step * 50) % 255 if step <= 2 else 120
            return _make_frame(40, 40, val)

        cfg = MotionConfig(
            poll_interval=0.01,
            timeout=1.0,
            stability_threshold=0.05,
            stable_count_required=2,
        )
        stable, frames = wait_until_stable(stream, config=cfg)
        assert stable is True
        assert frames >= 2


class TestSpinLifecycle:
    def test_lifecycle_success(self) -> None:
        step = 0

        def stream() -> Frame:
            nonlocal step
            step += 1
            # Step 1: initial (rest)
            # Step 2-4: spin (high motion)
            # Step 5+: rest (stable)
            if step == 1:
                return _make_frame(50, 50, 0)
            elif 2 <= step <= 4:
                return _make_frame(50, 50, (step * 60) % 255)
            else:
                return _make_frame(50, 50, 200)

        cfg = MotionConfig(
            poll_interval=0.01,
            timeout=1.0,
            motion_start_threshold=0.05,
            stability_threshold=0.05,
            stable_count_required=2,
        )
        lifecycle = monitor_spin_lifecycle(stream, config=cfg)

        assert isinstance(lifecycle, SpinLifecycle)
        assert lifecycle.spin_started is True
        assert lifecycle.spin_ended is True
        assert lifecycle.spin_duration is not None
        assert lifecycle.spin_duration >= 0.0
        assert lifecycle.peak_motion > 0.0
        assert lifecycle.timed_out is False

