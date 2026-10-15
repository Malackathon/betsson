"""Cheap, AI-free proof that the screen changed (the game visibly reacted to the spin)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

REACTION_THRESHOLD = 0.003  # mean per-pixel change (0..1); reels moving/HUD updating is well above it


def screen_change(before: Path, after: Path) -> float | None:
    """Normalised mean absolute pixel difference in [0, 1] between two screenshots.

    ``after`` is resized to ``before`` when sizes differ slightly. None if a file cannot be read.
    """
    try:
        with Image.open(before) as a, Image.open(after) as b:
            first = np.asarray(a.convert("RGB"), dtype=np.float64)
            second_img = b.convert("RGB")
            if second_img.size != a.size:
                second_img = second_img.resize(a.size)
            second = np.asarray(second_img, dtype=np.float64)
    except (OSError, ValueError):
        return None
    return float(np.mean(np.abs(first - second)) / 255.0)
