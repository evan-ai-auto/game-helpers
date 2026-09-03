"""Human-selectable task workflow definitions for 梦幻西游.

This module intentionally contains only workflow metadata. Selecting a workflow
never performs an action in the game.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import TaskCategory, TaskRecipe


@dataclass(frozen=True)
class TaskWorkflow:
    """A user-facing task workflow entry mapped to a deterministic recipe."""

    id: str
    name: str
    recipe: TaskRecipe
    description: str = ""


class TaskWorkflowRegistry:
    """In-memory registry for the task workflows currently available to the UI."""

    def __init__(self, workflows: tuple[TaskWorkflow, ...] | None = None) -> None:
        self._workflows = workflows or default_workflows()
        self._by_id = {workflow.id: workflow for workflow in self._workflows}
        self._by_name = {workflow.name: workflow for workflow in self._workflows}

    def all(self) -> tuple[TaskWorkflow, ...]:
        return self._workflows

    def get(self, workflow_id: str) -> TaskWorkflow:
        try:
            return self._by_id[workflow_id]
        except KeyError as exc:
            raise ValueError(f"unknown task workflow: {workflow_id}") from exc

    def get_by_name(self, name: str) -> TaskWorkflow:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise ValueError(f"unknown task workflow: {name}") from exc


def default_workflows() -> tuple[TaskWorkflow, ...]:
    """Return the initial safe workflow catalog.

    These recipes are intentionally metadata-only placeholders until the game
    perception layer can diagnose the corresponding task state. They contain
    no executable actions.
    """
    return (
        TaskWorkflow(
            id="shimen",
            name="师门任务",
            description="师门任务诊断流程（当前仅选择流程，不执行任务）。",
            recipe=TaskRecipe(
                id="shimen",
                name="师门任务",
                category=TaskCategory.GENERAL,
                metadata={"game": "梦幻西游", "diagnosis_only": True},
            ),
        ),
        TaskWorkflow(
            id="custom",
            name="自定义任务流程",
            description="用于后续接入用户自定义任务步骤的诊断入口。",
            recipe=TaskRecipe(
                id="custom",
                name="自定义任务流程",
                category=TaskCategory.GENERAL,
                metadata={"game": "梦幻西游", "diagnosis_only": True},
            ),
        ),
    )
