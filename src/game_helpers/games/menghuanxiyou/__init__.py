"""梦幻西游 first-game adapter."""

from .agent import DreamAgent
from .perception import DreamObservationBuilder
from .soul_task import (
    MILESTONES,
    MilestoneState,
    SoulRoundStatus,
    SoulTaskLoop,
    SoulTaskRound,
    TaskExecutionResult,
    TaskExecutionStatus,
    TaskVerification,
)
from .state import DreamGameAdapter, DreamGameState

__all__ = [
    "DreamAgent",
    "DreamGameAdapter",
    "DreamGameState",
    "DreamObservationBuilder",
    "MILESTONES",
    "MilestoneState",
    "SoulRoundStatus",
    "SoulTaskLoop",
    "SoulTaskRound",
    "TaskExecutionResult",
    "TaskExecutionStatus",
    "TaskVerification",
]
