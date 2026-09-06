"""Reusable planning, memory, and recovery primitives for Game Agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Iterable

from .agent_protocol import ActionResult, AgentDecision, VerificationResult
from .models import GameState


@dataclass(frozen=True)
class PlanStep:
    """One semantic step in a long-running game goal."""

    name: str
    objective: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMemory:
    """Small bounded episodic memory used for recovery and progress tracking."""

    max_events: int = 64
    events: list[str] = field(default_factory=list)
    failures: int = 0
    last_state_key: str | None = None
    last_progress_at: float = field(default_factory=monotonic)

    def remember(self, event: str) -> None:
        self.events.append(event)
        if len(self.events) > self.max_events:
            del self.events[:-self.max_events]

    def observe_state(self, state_key: str) -> None:
        if state_key != self.last_state_key:
            self.last_state_key = state_key
            self.last_progress_at = monotonic()

    def record_results(self, results: Iterable[ActionResult], verification: VerificationResult) -> None:
        failed = any(not result.succeeded for result in results)
        if failed or not verification.verified:
            self.failures += 1
            self.remember(verification.reason or "step failed")
        else:
            self.failures = 0
            self.remember(verification.reason or "step verified")


@dataclass(frozen=True)
class RecoveryDecision:
    """Recovery intent; the game policy turns it into concrete Actions."""

    mode: str
    reason: str


class RecoveryPolicy:
    """Escalating recovery policy that prevents blind repeated clicking."""

    def __init__(self, *, max_retries: int = 3, stall_seconds: float = 8.0) -> None:
        self.max_retries = max_retries
        self.stall_seconds = stall_seconds

    def decide(self, memory: AgentMemory) -> RecoveryDecision | None:
        if memory.failures >= self.max_retries:
            return RecoveryDecision("abort", "连续动作/验证失败，停止自动化以避免失控")
        if monotonic() - memory.last_progress_at >= self.stall_seconds:
            return RecoveryDecision("reacquire", "状态长时间无进展，重新获取视觉锚点")
        if memory.failures:
            return RecoveryDecision("retry", f"第 {memory.failures} 次恢复")
        return None


class GoalPlanner:
    """Ordered long-task planner with explicit semantic milestones."""

    def __init__(self, steps: Iterable[PlanStep]) -> None:
        self.steps = tuple(steps)
        self.index = 0

    @property
    def current(self) -> PlanStep | None:
        if self.index >= len(self.steps):
            return None
        return self.steps[self.index]

    def advance_if(self, completed: bool) -> None:
        if completed and self.current is not None:
            self.index += 1

    @property
    def completed(self) -> bool:
        return self.index >= len(self.steps)

    def snapshot(self) -> dict[str, Any]:
        return {"step_index": self.index, "step": self.current.name if self.current else None}


def state_key(state: GameState) -> str:
    """Stable coarse state key for progress detection."""

    return repr((
        getattr(state, "scene_id", None),
        getattr(state, "scene_name", None),
        getattr(state, "dialog_visible", False),
        getattr(state, "item_panel_open", False),
        getattr(state, "soul_task_claimed", False),
    ))
