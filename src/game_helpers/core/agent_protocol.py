"""Platform-independent data contracts for the GUI Agent closed loop.

The runtime pipeline is intentionally explicit:

    Capture -> Observation -> State -> Action -> Result

Planning and verification are represented as data, not coupled to a concrete
capture, vision, input, or game implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any, Mapping, Protocol, Sequence

from .models import Action, GameState, Rect, WindowInfo


class FrameLike(Protocol):
    """Minimum capture contract required by an Observation."""

    window: WindowInfo
    width: int
    height: int
    data: bytes
    captured_at: float
    backend: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class Observation:
    """A normalized perception input produced from one captured frame."""

    frame: FrameLike
    observation_id: str = ""
    timestamp: float = field(default_factory=time)
    objects: Mapping[str, Rect] = field(default_factory=dict)
    text: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ActionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ActionResult:
    """Execution outcome for one requested Action."""

    action: Action
    status: ActionStatus
    started_at: float
    finished_at: float
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status is ActionStatus.SUCCESS


@dataclass(frozen=True)
class VerificationResult:
    """Post-action verification outcome used by recovery/planning."""

    verified: bool
    reason: str = ""
    state: GameState | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentDecision:
    """Planner output: one or more Actions plus an optional rationale."""

    actions: tuple[Action, ...] = ()
    rationale: str = ""
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
