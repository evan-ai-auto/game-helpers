"""Compatibility facade for background hosted-view capture.

View switching is runtime orchestration; WGC remains the Capture backend.
"""

from __future__ import annotations

import sys
import time

from game_helpers.core.models import WindowInfo
from game_helpers.runtime.view_manager import GameViewManager

from .models import Frame
from .wgc import WindowsGraphicsCapture


class BackgroundViewCapture:
    """Expose one hosted view through the runtime manager and capture it."""

    def __init__(self, parent_hwnd: int, *, settle_delay: float = 0.25) -> None:
        if sys.platform != "win32":
            raise RuntimeError("background hosted-view capture requires Windows")
        self.parent_hwnd = int(parent_hwnd)
        self.settle_delay = settle_delay
        self.views = GameViewManager(self.parent_hwnd)
        self.capture_backend = WindowsGraphicsCapture()

    def capture(self, index: int) -> Frame:
        view = self.views.switch_surface_to(index)
        time.sleep(self.settle_delay)
        bounds = view.window.bounds
        window = WindowInfo(
            hwnd=self.parent_hwnd,
            title=view.window.title,
            class_name=view.window.class_name,
            bounds=bounds,
            visible=True,
        )
        return self.capture_backend.capture(window)
