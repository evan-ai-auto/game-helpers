"""High-level GUI Agent session orchestration."""

from __future__ import annotations

import sys

from ..core.models import GameState, WindowInfo
from ..capture.models import Frame
from ..capture.wgc import WindowsGraphicsCapture
from ..platform.windows.input import BackgroundInput
from .view_manager import GameViewManager


class BackgroundGameSession:
    """Coordinate one hosted game surface without activating the host window."""

    def __init__(self, window: WindowInfo, *, timeout: float = 2.0) -> None:
        if sys.platform != "win32":
            raise RuntimeError("BackgroundGameSession requires Windows")
        self.window = window
        self.views = GameViewManager(window.hwnd, timeout=timeout)
        self.capture_backend = WindowsGraphicsCapture()

    def select(self, index: int):
        return self.views.switch_surface_to(index)

    def capture(self) -> Frame:
        return self.capture_backend.capture(self.window)

    def click(self, x: int, y: int, *, index: int | None = None) -> None:
        view = self.select(index) if index is not None else self.views.views()[self._current_zero_based()]
        BackgroundInput(view.hwnd).click(x, y)

    def mouse_move(self, x: int, y: int, *, index: int | None = None) -> None:
        view = self.select(index) if index is not None else self.views.views()[self._current_zero_based()]
        BackgroundInput(view.hwnd).mouse_move(x, y)

    def snapshot(self, *, index: int | None = None) -> tuple[object, Frame]:
        view = self.select(index) if index is not None else self.views.views()[self._current_zero_based()]
        return view, self.capture()

    def state(self, frame: Frame) -> GameState:
        return GameState(window=self.window, screenshot_available=True, metadata={"capture_backend": frame.backend})

    def build_agent_runtime(self, agent, **kwargs):
        from .agent_runtime import AgentRuntime
        return AgentRuntime(self.capture, agent, **kwargs)

    def build_dream_agent_runtime(self, *, asset_root=None, goal: str = "soul_task", **kwargs):
        """Build the Dream Agent Brain with an explicit long-task goal."""
        from ..games.menghuanxiyou import DreamAgent, DreamGameAdapter, DreamObservationBuilder
        from ..games.menghuanxiyou.navigation import DreamNavigationGraph
        from .agent_runtime import AgentRuntime

        adapter = DreamGameAdapter(asset_root)
        navigation = DreamNavigationGraph(adapter.scenes)
        return AgentRuntime(
            self.capture,
            DreamAgent(navigation=navigation, goal=goal),
            observation_builder=DreamObservationBuilder(asset_root),
            game_adapter=adapter,
            **kwargs,
        )

    def _current_zero_based(self) -> int:
        return self.views.current_surface_index() - 1
