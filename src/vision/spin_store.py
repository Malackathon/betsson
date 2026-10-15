"""Persistent, verified Spin-button locations so later runs skip the AI call entirely.

Only locations that have already produced a real spin request are stored (the caller decides),
so a wrong guess (e.g. a "tap to continue" button) is never remembered. Values are relative
(0..1) to the game iframe screenshot. The file lives under ``artifacts/`` (gitignored).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

DEFAULT_PATH = Path("artifacts") / "cache" / "spin_locations.json"
ASPECT_DECIMALS = 1  # 770x433 and 771x434 are the same layout; 4:3 vs 16:9 are not

_lock = threading.Lock()  # one process runs several agents in threads


def spin_key(market: str, game: str, width: float, height: float) -> str:
    ratio = round(width / height, ASPECT_DECIMALS) if height else 0
    return f"{market}|{game}|{ratio}"


def _valid(location: object) -> bool:
    return (
        isinstance(location, dict)
        and all(isinstance(location.get(k), (int, float)) and 0.0 <= location[k] <= 1.0 for k in ("x", "y"))
    )


class SpinLocationStore:
    def __init__(self, path: Path | str = DEFAULT_PATH) -> None:
        self._path = Path(path)

    def get(self, key: str) -> dict[str, float] | None:
        location = self._read().get(key)
        return {"x": float(location["x"]), "y": float(location["y"])} if _valid(location) else None

    def save(self, key: str, location: dict[str, float]) -> None:
        if not _valid(location):
            return
        with _lock:
            data = self._read()
            data[key] = {"x": float(location["x"]), "y": float(location["y"])}
            self._write(data)

    def invalidate(self, key: str) -> None:
        with _lock:
            data = self._read()
            if data.pop(key, None) is not None:
                self._write(data)

    def _read(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)  # atomic: a reader never sees a half-written file
