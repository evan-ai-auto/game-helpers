"""Foreground desktop input transport for Win32."""

from __future__ import annotations

import ctypes
import time

from ...core.models import Point


class DesktopInput:
    """Execute basic mouse input against the active Windows desktop."""

    def move(self, target: Point) -> None:
        ctypes.windll.user32.SetCursorPos(target.x, target.y)

    def click(self, target: Point, *, double: bool = False) -> None:
        self.move(target)
        user32 = ctypes.windll.user32
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        if double:
            time.sleep(0.05)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
