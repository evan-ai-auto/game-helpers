"""Background-safe switching and capture of hosted game child windows."""

from __future__ import annotations

import sys
import time

from game_helpers.core import discover_game_views

from .models import Frame
from .wgc import WindowsGraphicsCapture


class BackgroundViewCapture:
    """Temporarily expose one WSGAME child without activating the host window."""

    def __init__(self, parent_hwnd: int, *, settle_delay: float = 0.25) -> None:
        self.parent_hwnd = int(parent_hwnd)
        self.settle_delay = settle_delay
        self.capture_backend = WindowsGraphicsCapture()

    def capture(self, index: int) -> Frame:
        """Show one hosted view without activation, capture the parent, then restore."""
        if sys.platform != "win32":
            raise RuntimeError("background hosted-view capture requires Windows")

        import ctypes

        views = discover_game_views(self.parent_hwnd)
        if not 1 <= index <= len(views):
            raise ValueError(f"game view index must be between 1 and {len(views)}")

        user32 = ctypes.windll.user32
        SW_HIDE = 0
        SW_SHOWNOACTIVATE = 4
        target = views[index - 1]
        original = {view.hwnd: bool(user32.IsWindowVisible(view.hwnd)) for view in views}
        foreground_before = int(user32.GetForegroundWindow())

        try:
            # SW_SHOWNOACTIVATE is the important distinction from SW_SHOW:
            # the hosted child becomes the displayed surface without asking
            # Windows to activate the game window.
            for view in views:
                user32.ShowWindow(
                    view.hwnd,
                    SW_SHOWNOACTIVATE if view.hwnd == target.hwnd else SW_HIDE,
                )
            time.sleep(self.settle_delay)

            frame = self.capture_backend.capture(
                type(
                    "CaptureWindow",
                    (),
                    {
                        "hwnd": self.parent_hwnd,
                        "bounds": target.window.bounds,
                        "title": target.window.title,
                    },
                )()
            )

            foreground_after = int(user32.GetForegroundWindow())
            if foreground_after != foreground_before:
                raise RuntimeError(
                    "foreground window changed during background capture: "
                    f"before={foreground_before}, after={foreground_after}"
                )
            return frame
        finally:
            for hwnd, visible in original.items():
                user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE if visible else SW_HIDE)
