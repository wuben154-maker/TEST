"""Minimal tool metadata for common tools.

Used for documentation and future policy hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class ToolRisk(str, Enum):
    """Rough risk class for governance and future truncation policy."""

    READ_ONLY = "read_only"
    NETWORK = "network"
    MUTATING = "mutating"


@dataclass(frozen=True)
class ToolSpec:
    """Static metadata for a registered common tool name."""

    name: str
    category: Literal["security", "research", "history", "sandbox"]
    risk: ToolRisk = ToolRisk.READ_ONLY
