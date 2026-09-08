"""Shared closed-loop primitives for the 梦幻西游 铸魂/命魂 task round.

Task-specific executors report task completion to this controller. The
controller then performs the common verification/progress/milestone loop.
Milestone 15/30/45 rewards are claimed and the task list is refreshed. The
60 completion icon completes the round; opening the next round is deliberately
left as a future hook.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol


MILESTONES = (15, 30, 45, 60)


class SoulRoundStatus(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    MILESTONE_REWARD = "milestone_reward"
    COMPLETING = "completing"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class TaskExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    PAUSED = "paused"


@dataclass(frozen=True)
class TaskExecutionResult:
    task_id: str
    task_type: str
    status: TaskExecutionStatus
    message: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskVerification:
    task_id: str
    verified: bool
    message: str
    progress: int | None = None


@dataclass(frozen=True)
class MilestoneState:
    threshold: int
    reached: bool = False
    reward_type: str = "reward_chest"
    claimable: bool = False
    claimed: bool = False
    verification: str = "pending"


@dataclass
class SoulTaskRound:
    round_id: str
    progress: int = 0
    status: SoulRoundStatus = SoulRoundStatus.NOT_STARTED
    milestones: dict[int, MilestoneState] = field(
        default_factory=lambda: {
            threshold: MilestoneState(threshold=threshold)
            for threshold in MILESTONES
        }
    )


class TaskExecutor(Protocol):
    def execute(self, task_id: str) -> TaskExecutionResult: ...


class TaskVerifier(Protocol):
    def verify(self, result: TaskExecutionResult) -> TaskVerification: ...


class ProgressDetector(Protocol):
    def detect(self) -> int: ...


class RewardClaimer(Protocol):
    def claim(self, threshold: int) -> bool: ...


class TaskRefresher(Protocol):
    def refresh(self) -> bool: ...


@dataclass
class SoulTaskLoop:
    """Common task-completion pipeline for every soul-task type."""

    round: SoulTaskRound
    verifier: TaskVerifier
    progress_detector: ProgressDetector
    reward_claimer: RewardClaimer
    refresher: TaskRefresher
    events: list[dict[str, object]] = field(default_factory=list)
    stop_after_round: bool = True

    def process_task(self, result: TaskExecutionResult) -> TaskVerification:
        """Verify any task type, then feed the shared progress pipeline."""
        verification = self.verifier.verify(result)
        self.events.append(
            {
                "category": "TASK_VERIFICATION",
                "task_id": result.task_id,
                "task_type": result.task_type,
                "success": verification.verified,
                "message": verification.message,
            }
        )
        if not verification.verified:
            self.round.status = SoulRoundStatus.BLOCKED if result.status == TaskExecutionStatus.BLOCKED else SoulRoundStatus.RUNNING
            return verification

        self.round.status = SoulRoundStatus.RUNNING
        self.detect_progress()
        return verification

    def detect_progress(self) -> int:
        progress = max(0, min(60, int(self.progress_detector.detect())))
        if progress < self.round.progress:
            self.events.append(
                {
                    "category": "PROGRESS_DETECTION",
                    "success": False,
                    "message": "progress moved backwards; retaining previous progress",
                    "progress": self.round.progress,
                    "detected_progress": progress,
                }
            )
            progress = self.round.progress
        self.round.progress = progress
        self.events.append(
            {"category": "PROGRESS_DETECTION", "success": True, "progress": progress}
        )

        for threshold in MILESTONES:
            milestone = self.round.milestones[threshold]
            if progress >= threshold and not milestone.claimed:
                self._handle_milestone(threshold)
                if threshold == 60 and self.round.status == SoulRoundStatus.COMPLETED:
                    break
        return progress

    def _handle_milestone(self, threshold: int) -> None:
        current = self.round.milestones[threshold]
        self.round.milestones[threshold] = MilestoneState(
            threshold=threshold,
            reached=True,
            reward_type="completion_reward" if threshold == 60 else "reward_chest",
            claimable=True,
            claimed=current.claimed,
            verification="detected",
        )
        self.round.status = SoulRoundStatus.MILESTONE_REWARD if threshold < 60 else SoulRoundStatus.COMPLETING
        self.events.append(
            {
                "category": "MILESTONE",
                "threshold": threshold,
                "success": True,
                "reward_type": "completion_reward" if threshold == 60 else "reward_chest",
            }
        )

        if not self.reward_claimer.claim(threshold):
            self.round.status = SoulRoundStatus.BLOCKED
            self.events.append(
                {"category": "REWARD", "threshold": threshold, "success": False, "message": "claim failed"}
            )
            return

        self.round.milestones[threshold] = MilestoneState(
            threshold=threshold,
            reached=True,
            reward_type="completion_reward" if threshold == 60 else "reward_chest",
            claimable=False,
            claimed=True,
            verification="claimed",
        )
        self.events.append({"category": "REWARD", "threshold": threshold, "success": True})

        if threshold < 60:
            if not self.refresher.refresh():
                self.round.status = SoulRoundStatus.BLOCKED
                self.events.append({"category": "TASK_REFRESH", "success": False})
                return
            self.events.append({"category": "TASK_REFRESH", "success": True, "threshold": threshold})
        else:
            self.round.status = SoulRoundStatus.COMPLETED
            self.events.append(
                {
                    "category": "ROUND_COMPLETION",
                    "success": True,
                    "round_id": self.round.round_id,
                    "auto_open_next_round": False,
                }
            )

    def snapshot(self) -> dict[str, object]:
        return {
            "round_id": self.round.round_id,
            "progress": self.round.progress,
            "status": self.round.status.value,
            "milestones": {
                str(k): {
                    "reached": v.reached,
                    "reward_type": v.reward_type,
                    "claimable": v.claimable,
                    "claimed": v.claimed,
                    "verification": v.verification,
                }
                for k, v in self.round.milestones.items()
            },
            "auto_open_next_round": False,
            "events": list(self.events),
        }
