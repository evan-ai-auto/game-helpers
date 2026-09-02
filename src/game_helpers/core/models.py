"""Shared data models used by perception, planning, and execution layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    MOVE = "move"
    KEY = "key"
    WAIT = "wait"


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center(self) -> Point:
        return Point(self.left + self.width // 2, self.top + self.height // 2)


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str = ""
    bounds: Rect | None = None
    visible: bool = True


@dataclass(frozen=True)
class Action:
    type: ActionType
    target: Point | None = None
    key: str | None = None
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameState:
    """Current observable state; intentionally independent of any game process."""

    window: WindowInfo | None = None
    screenshot_available: bool = False
    dialog_visible: bool = False
    inventory_visible: bool = False
    task_completed: bool = False
    detected_text: list[str] = field(default_factory=list)
    targets: dict[str, Rect] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
