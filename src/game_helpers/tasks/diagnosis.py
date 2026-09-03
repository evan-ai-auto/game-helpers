"""Task diagnosis: reconcile a selected character, recipe, and live game state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import AccountCandidate, RoutePlan, TaskRecipe, TaskStep
from .progress import LiveTaskEvidence, TaskProgress, reconcile_progress


class DiagnosisStatus(str, Enum):
    READY = "ready"
    NEED_CLAIM = "need_claim"
    NEED_ROUTE = "need_route"
    NEED_NPC = "need_npc"
    RESUME = "resume"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CharacterSelection:
    character_name: str
    view_index: int
    hwnd: int


@dataclass(frozen=True)
class TaskObservation:
    character_name: str
    task_id: str | None = None
    task_name: str | None = None
    task_claimed: bool | None = None
    task_in_progress: bool | None = None
    current_scene: str | None = None
    target_scene: str | None = None
    target_npc: str | None = None
    target_npc_visible: bool | None = None
    required_items_ready: bool | None = None
    task_panel_visible: bool = False
    completed_step_hints: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskRouteDecision:
    needed: bool
    reason: str
    route: RoutePlan | None = None


@dataclass(frozen=True)
class TaskExecutionPlan:
    recipe_id: str
    character_name: str
    status: DiagnosisStatus
    start_step: TaskStep | None = None
    route: RoutePlan | None = None
    resume_step_index: int | None = None
    confidence: float = 0.0
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskDiagnosis:
    selection: CharacterSelection
    recipe_id: str
    observation: TaskObservation
    plan: TaskExecutionPlan


class TaskDiagnosisEngine:
    """Deterministic first-pass diagnosis; AI can handle only ambiguous cases."""

    def diagnose(
        self,
        selection: CharacterSelection,
        recipe: TaskRecipe,
        observation: TaskObservation,
        checkpoint: TaskProgress | None = None,
        route: RoutePlan | None = None,
    ) -> TaskDiagnosis:
        reasons: list[str] = []
        resume_index: int | None = None
        confidence = 0.0

        if observation.task_claimed is False:
            plan = TaskExecutionPlan(recipe.id, selection.character_name, DiagnosisStatus.NEED_CLAIM,
                                     self._first_step(recipe), reasons=("task is not claimed",))
            return TaskDiagnosis(selection, recipe.id, observation, plan)

        if observation.task_claimed is None:
            plan = TaskExecutionPlan(recipe.id, selection.character_name, DiagnosisStatus.CONFIRM,
                                     reasons=("cannot determine whether task is claimed",))
            return TaskDiagnosis(selection, recipe.id, observation, plan)

        if checkpoint is not None:
            evidence = LiveTaskEvidence(
                task_id=observation.task_id,
                task_name=observation.task_name,
                character_name=observation.character_name,
                scene_id=observation.current_scene,
                target_npc=observation.target_npc,
                completed_step_hints=observation.completed_step_hints,
                task_panel_visible=observation.task_panel_visible,
            )
            decision = reconcile_progress(checkpoint, evidence)
            if decision.can_resume:
                resume_index = decision.step_index
                confidence = decision.confidence
                reasons.append("saved checkpoint reconciles with live state")
            elif decision.confidence > 0:
                reasons.append("checkpoint exists but live state needs confirmation")

        if observation.task_in_progress is False:
            reasons.append("task is not currently in progress")

        if observation.target_scene and observation.current_scene != observation.target_scene:
            if route is not None:
                return self._result(selection, observation, recipe, DiagnosisStatus.NEED_ROUTE,
                                     route=route, resume_index=resume_index, confidence=confidence,
                                     reasons=reasons + ["current scene differs from target scene"])
            return self._result(selection, observation, recipe, DiagnosisStatus.NEED_ROUTE,
                                resume_index=resume_index, confidence=confidence,
                                reasons=reasons + ["no historical route supplied; route planning required"])

        if observation.target_npc and observation.target_npc_visible is False:
            return self._result(selection, observation, recipe, DiagnosisStatus.NEED_NPC,
                                resume_index=resume_index, confidence=confidence,
                                reasons=reasons + ["target NPC is not visible in current scene"])

        if resume_index is not None:
            step = recipe.steps[resume_index] if resume_index < len(recipe.steps) else None
            return self._result(selection, observation, recipe, DiagnosisStatus.RESUME,
                                start_step=step, resume_index=resume_index, confidence=confidence,
                                reasons=reasons)

        return self._result(selection, observation, recipe, DiagnosisStatus.READY,
                            start_step=self._first_step(recipe), reasons=reasons or ["state is ready for execution"])

    @staticmethod
    def _first_step(recipe: TaskRecipe) -> TaskStep | None:
        return recipe.steps[0] if recipe.steps else None

    @staticmethod
    def _result(selection: CharacterSelection, observation: TaskObservation, recipe: TaskRecipe,
                status: DiagnosisStatus, start_step: TaskStep | None = None,
                route: RoutePlan | None = None, resume_index: int | None = None,
                confidence: float = 0.0, reasons: list[str] | None = None) -> TaskDiagnosis:
        plan = TaskExecutionPlan(recipe.id, selection.character_name, status, start_step, route,
                                 resume_index, confidence, tuple(reasons or ()))
        return TaskDiagnosis(selection, recipe.id, observation, plan)
