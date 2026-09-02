"""High-level background game switching, capture, and input orchestration."""

from __future__ import annotations

import sys

from .models import GameState, WindowInfo
from .view_manager import GameViewManager
from game_helpers.actions import BackgroundInput
from game_helpers.capture.models import Frame
from game_helpers.capture.wgc import WindowsGraphicsCapture


class BackgroundGameSession:
    """Coordinate one hosted game surface without activating the host window."""

    def __init__(self, window: WindowInfo, *, timeout: float = 2.0) -> None:
        if sys.platform != "win32":
            raise RuntimeError("BackgroundGameSession requires Windows")
        self.window = window
        self.views = GameViewManager(window.hwnd, timeout=timeout)
        self.capture_backend = WindowsGraphicsCapture()

    def select(self, index: int):
        """Expose a one-based WSGAME surface without changing the foreground window."""
        return self.views.switch_surface_to(index)

    def capture(self) -> Frame:
        """Capture the currently exposed hosted surface through the parent HWND."""
        return self.capture_backend.capture(self.window)

    def click(self, x: int, y: int, *, index: int | None = None) -> None:
        """Post a background click in WSGAME client coordinates."""
        view = self.select(index) if index is not None else self.views.views()[self._current_zero_based()]
        BackgroundInput(view.hwnd).click(x, y)

    def mouse_move(self, x: int, y: int, *, index: int | None = None) -> None:
        """Post a background mouse move in WSGAME client coordinates."""
        view = self.select(index) if index is not None else self.views.views()[self._current_zero_based()]
        BackgroundInput(view.hwnd).mouse_move(x, y)

    def snapshot(self, *, index: int | None = None) -> tuple[object, Frame]:
        """Select an optional surface and return its view plus a parent capture."""
        view = self.select(index) if index is not None else self.views.views()[self._current_zero_based()]
        return view, self.capture()

    def state(self, frame: Frame) -> GameState:
        """Create the initial structured state consumed by perception layers."""
        return GameState(window=self.window, screenshot_available=True, metadata={"capture_backend": frame.backend})

    def _current_zero_based(self) -> int:
        return self.views.current_surface_index() - 1
