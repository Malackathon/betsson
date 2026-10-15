"""Protocol interfaces for isolated agent execution.

Defines structural subtyping protocols replicating signatures expected from
browser, flow, and vision modules so that e2e orchestration can be developed
and tested independently before full branch integration.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.models.schemas import (
    GeminiBalanceReading,
    GeminiHudReading,
    GeminiMessageReading,
    GeminiSpinLocation,
)


@runtime_checkable
class LobbyPageProtocol(Protocol):
    """Protocol for Betsson lobby navigation, authentication, and balance reading."""

    def login(self, username: str, password: str) -> bool:
        """Authenticate user on Betsson lobby in an unrecorded browser context."""
        ...

    def navigate_to_game(self, game_title: str) -> bool:
        """Search and navigate to the target Pragmatic Play game."""
        ...

    def get_betsson_balance(self) -> Decimal:
        """Poll and return stabilized Betsson balance from the header DOM."""
        ...

    def get_betsson_currency(self) -> str:
        """Read currency symbol or ISO code displayed in the header DOM."""
        ...


@runtime_checkable
class GameCanvasProtocol(Protocol):
    """Protocol for game frame / canvas interactions and screenshot capture."""

    def get_canvas_rect(self) -> dict[str, int]:
        """Return absolute viewport bounding box for the game canvas / iframe."""
        ...

    def click_spin(self, rel_x: float, rel_y: float) -> bool:
        """Click on spin button using relative normalized canvas coordinates."""
        ...

    def close_intro_dialogs(self) -> bool:
        """Dismiss intro splash screens, promotional modals, or wrapper banners."""
        ...

    def capture_screenshot(self, output_path: Path) -> Path:
        """Capture screenshot of the game canvas area and save to output_path."""
        ...


@runtime_checkable
class VisionInspectorProtocol(Protocol):
    """Protocol for AI-powered visual inspection using Gemini."""

    def read_hud(self, image_path: Path) -> GeminiHudReading:
        """Extract CREDIT, BET, WIN amounts and currency from game HUD."""
        ...

    def read_insufficient_funds_message(self, image_path: Path) -> GeminiMessageReading:
        """Detect modal warning dialog, extract message text, and detect language."""
        ...

    def locate_spin_button(self, image_path: Path) -> GeminiSpinLocation:
        """Detect normalized coordinates of the game's spin button."""
        ...

    def is_bonus_or_free_spins_active(self, image_path: Path) -> bool:
        """Detect if a bonus round, feature trigger, or free spin sequence is active."""
        ...


@runtime_checkable
class MotionDetectorProtocol(Protocol):
    """Protocol for computer vision motion detection and reel stability."""

    def measure_baseline(self) -> float:
        """Measure background ambient animation baseline at rest."""
        ...

    def wait_until_spin_started(self, timeout_sec: float = 5.0) -> bool:
        """Detect when reels start spinning following spin button click."""
        ...

    def wait_until_stable(self, timeout_sec: float = 15.0) -> bool:
        """Poll until reels stop and HUD numbers stabilize."""
        ...

    def is_canvas_altered(self, frame_before: Path, frame_after: Path) -> bool:
        """Check whether pixel motion or modal overlay altered the canvas."""
        ...


@runtime_checkable
class GameFlowProtocol(Protocol):
    """Protocol for high-level game flow orchestration within a single worker."""

    def setup_session(self, agent_id: str, username: str, password: str) -> bool:
        """Initialize dual contexts: unrecorded auth session then recorded game session."""
        ...

    def prepare_game(self, game_title: str) -> bool:
        """Open game and dismiss introductory modals."""
        ...

    def execute_spin_cycle(self) -> dict[str, Any]:
        """Perform click, wait for motion, wait for stability, and return outcomes."""
        ...

    def check_insufficient_funds_banner(self) -> tuple[bool, str, str]:
        """Check for insufficient funds alert (location, message_text, raw_evidence)."""
        ...
