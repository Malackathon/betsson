"""Evidence generation and screenshot management for Betsson Game Validation.

Handles saving annotated screenshots in artifacts/{agent_id}/evidence/
without exposing credentials or personal identifiable information (PII).
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize a string for safe use in file system paths."""
    clean = re.sub(r"[^\w\-_.]", "_", name.strip())
    return re.sub(r"_+", "_", clean)


def ensure_evidence_dir(base_dir: Path, agent_id: str) -> Path:
    """Create and return the evidence directory for the specified agent."""
    evidence_dir = base_dir / agent_id / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir


def record_evidence_screenshot(
    image_bytes: bytes,
    output_path: Path,
    description: str = "",
) -> Path:
    """Save raw image bytes to output_path and ensure parent directories exist."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)
    logger.debug("Evidence screenshot saved to %s (%s)", output_path, description)
    return output_path
