"""Generic action execution boundary.

The executor interprets the action contract; Win32 input mechanics live in the
platform adapter and can be replaced without changing Agent-facing actions.
"""

from __future__ import annotations

import sys
import time

from game_helpers.core.models import Action, ActionType
from game_helpers.platform.windows.desktop_input import DesktopInput


class ActionExecutor:
    """Execute generic actions through the active platform adapter."""

    def __init__(self, *, input_adapter: DesktopInput | None = None) -> None:
        self.input = input_adapter or DesktopInput()

    def execute(self, action: Action) -> None:
        if sys.platform != "win32":
            raise RuntimeError("ActionExecutor requires Windows")
        if action.type is ActionType.WAIT:
            time.sleep(action.duration_ms / 1000)
            return
        if action.type is ActionType.MOVE:
            if action.target is None:
                raise ValueError("MOVE action requires target")
            self.input.move(action.target)
            return
        if action.type in (ActionType.CLICK, ActionType.DOUBLE_CLICK):
            if action.target is None:
                raise ValueError(f"{action.type.value} action requires target")
            self.input.click(action.target, double=action.type is ActionType.DOUBLE_CLICK)
            return
        raise NotImplementedError(f"Unsupported action: {action.type.value}")
