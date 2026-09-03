"""Persistent task checkpoints and resume decisions."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskProgress:
    """Durable checkpoint for one character's task execution."""

    task_id: str
    task_name: str
    character_name: str
    step_index: int = 0
    status: str = "in_progress"
    scene_id: str | None = None
    target_npc: str | None = None
    completed_steps: tuple[str, ...] = ()
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LiveTaskEvidence:
    """Observations collected after the game is opened again."""

    task_id: str | None = None
    task_name: str | None = None
    character_name: str | None = None
    scene_id: str | None = None
    target_npc: str | None = None
    completed_step_hints: tuple[str, ...] = ()
    task_panel_visible: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResumeDecision:
    can_resume: bool
    reason: str
    step_index: int | None = None
    confidence: float = 0.0


def reconcile_progress(
    checkpoint: TaskProgress | None,
    evidence: LiveTaskEvidence,
) -> ResumeDecision:
    """Reconcile a saved checkpoint with freshly observed game state.

    A checkpoint alone is never treated as proof that a task is still resumable.
    Matching task/character evidence raises confidence; contradictory evidence
    blocks automatic resume and lets the caller ask for human confirmation.
    """
    if checkpoint is None:
        return ResumeDecision(False, "no saved task checkpoint")
    if checkpoint.status in {"completed", "cancelled", "failed"}:
        return ResumeDecision(False, f"checkpoint status is {checkpoint.status}")

    score = 0.0
    reasons: list[str] = []
    contradictions = False

    if evidence.character_name and evidence.character_name == checkpoint.character_name:
        score += 0.35
        reasons.append("character matches checkpoint")
    elif evidence.character_name:
        contradictions = True
        reasons.append("character does not match checkpoint")

    if evidence.task_id and evidence.task_id == checkpoint.task_id:
        score += 0.45
        reasons.append("task id matches checkpoint")
    elif evidence.task_id:
        contradictions = True
        reasons.append("task id does not match checkpoint")
    elif evidence.task_name and evidence.task_name == checkpoint.task_name:
        score += 0.30
        reasons.append("task name matches checkpoint")

    if evidence.scene_id and checkpoint.scene_id and evidence.scene_id == checkpoint.scene_id:
        score += 0.10
        reasons.append("scene matches checkpoint")

    if evidence.target_npc and checkpoint.target_npc and evidence.target_npc == checkpoint.target_npc:
        score += 0.10
        reasons.append("target NPC matches checkpoint")

    if contradictions or score < 0.45:
        return ResumeDecision(False, "; ".join(reasons) or "insufficient live evidence", checkpoint.step_index, score)

    return ResumeDecision(True, "; ".join(reasons), checkpoint.step_index, min(score, 1.0))


class TaskProgressStore:
    """Small JSON-backed store suitable for the MVP and easy to replace later."""

    def __init__(self, path: str | Path = "data/task_progress.json") -> None:
        self.path = Path(path)

    def save(self, progress: TaskProgress) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = self._load_records()
        records[self._key(progress)] = asdict(progress)
        self.path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, character_name: str, task_id: str) -> TaskProgress | None:
        raw = self._load_records().get(f"{character_name}:{task_id}")
        if raw is None:
            return None
        return TaskProgress(
            task_id=raw["task_id"],
            task_name=raw["task_name"],
            character_name=raw["character_name"],
            step_index=int(raw.get("step_index", 0)),
            status=raw.get("status", "in_progress"),
            scene_id=raw.get("scene_id"),
            target_npc=raw.get("target_npc"),
            completed_steps=tuple(raw.get("completed_steps", ())),
            updated_at=float(raw.get("updated_at", 0)),
            metadata=dict(raw.get("metadata", {})),
        )

    def _load_records(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _key(progress: TaskProgress) -> str:
        return f"{progress.character_name}:{progress.task_id}"
