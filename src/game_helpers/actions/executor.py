"""System-level action executor.

This first implementation deliberately uses ordinary user input APIs. It does
not inject into a game process or attempt to bypass anti-cheat protections.
"""

from __future__ import annotations

import time

from game_helpers.core.models import Action, ActionType


class ActionExecutor:
    """Execute basic actions against the current desktop on Windows."""

    def execute(self, action: Action) -> None:
        if __import__("sys").platform != "win32":
            raise RuntimeError("ActionExecutor requires Windows")

        if action.type is ActionType.WAIT:
            time.sleep(action.duration_ms / 1000)
            return

        import ctypes

        user32 = ctypes.windll.user32
        if action.type is ActionType.MOVE:
            if action.target is None:
                raise ValueError("MOVE action requires target")
            user32.SetCursorPos(action.target.x, action.target.y)
            return

        if action.type in (ActionType.CLICK, ActionType.DOUBLE_CLICK):
            if action.target is None:
                raise ValueError(f"{action.type.value} action requires target")
            user32.SetCursorPos(action.target.x, action.target.y)
            user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
            user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
            if action.type is ActionType.DOUBLE_CLICK:
                time.sleep(0.05)
                user32.mouse_event(0x0002, 0, 0, 0, 0)
                user32.mouse_event(0x0004, 0, 0, 0, 0)
            return

        raise NotImplementedError(f"Unsupported action: {action.type.value}")
