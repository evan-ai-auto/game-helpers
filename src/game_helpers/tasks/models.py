"""Data models for human-defined game assets and task recipes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskCategory(str, Enum):
    SOUL_FORGING = "soul_forging"
    GENERAL = "general"


class StepType(str, Enum):
    OPEN_TASK_PANEL = "open_task_panel"
    CLOSE_TASK_PANEL = "close_task_panel"
    FIND_NPC = "find_npc"
    TALK = "talk"
    DIALOG = "dialog"
    GIVE_ITEM = "give_item"
    USE_ITEM = "use_item"
    NAVIGATE = "navigate"
    VERIFY = "verify"


@dataclass(frozen=True)
class ItemAsset:
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    quantity_hint: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NpcAsset:
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    scene_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SceneAsset:
    id: str
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TravelEdge:
    source_scene: str
    target_scene: str
    cost: float
    action: str
    required_item: str | None = None


@dataclass(frozen=True)
class TaskStep:
    type: StepType
    target: str | None = None
    text: str | None = None
    item: str | None = None
    quantity: int = 1
    scene_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskRecipe:
    id: str
    name: str
    category: TaskCategory = TaskCategory.GENERAL
    initial_npc: str | None = None
    required_items: tuple[str, ...] = ()
    steps: tuple[TaskStep, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutePlan:
    source_scene: str
    target_scene: str
    scenes: tuple[str, ...]
    actions: tuple[str, ...]
    cost: float


@dataclass(frozen=True)
class AccountCandidate:
    """Identity and current surface geometry for one 梦幻西游 WSGAME instance."""

    view_index: int
    hwnd: int
    process_id: int | None
    character_name: str | None = None
    account_name: str | None = None
    identity: str | None = None
    logged_in: bool | None = None
    client_width: int | None = None
    client_height: int | None = None
    dpi: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def expected_resolution(self) -> tuple[int, int] | None:
        """Resolution observed during the initial instance scan."""
        if self.client_width and self.client_height:
            return self.client_width, self.client_height
        return None
