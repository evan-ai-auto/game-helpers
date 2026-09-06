"""Runtime orchestration for switching hosted game views."""

from __future__ import annotations

import ctypes
import sys
import time

from ..core.game_view import GameView, discover_game_views
from ..platform.windows.tabs import current_tab_index, find_tab_control, select_tab


class GameViewManager:
    """Coordinate hosted views; platform details stay in the Windows adapter."""

    def __init__(self, parent_hwnd: int, *, switch_delay: float = 0.15, timeout: float = 2.0,
                 activate_before_switch: bool = False) -> None:
        self.parent_hwnd = parent_hwnd
        self.switch_delay = switch_delay
        self.timeout = timeout
        self.activate_before_switch = activate_before_switch

    def views(self) -> list[GameView]:
        return discover_game_views(self.parent_hwnd)

    def current_index(self) -> int:
        tab_hwnd = self._tab_hwnd()
        return current_tab_index(tab_hwnd) + 1

    def current_surface_index(self) -> int:
        views = self.views()
        for index, view in enumerate(views, start=1):
            if view.window.visible:
                return index
        raise RuntimeError("no visible WSGAME surface was found")

    def switch_to(self, index: int) -> GameView:
        views = self.views()
        if not 1 <= index <= len(views):
            raise ValueError(f"game view index must be between 1 and {len(views)}")
        current = self.current_index()
        if current == index:
            return views[index - 1]
        if self.activate_before_switch:
            self._activate_parent()
            self._switch_with_ctrl_tab(index, current, len(views))
        else:
            select_tab(self._tab_hwnd(), index - 1)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.current_index() == index:
                return self.views()[index - 1]
            time.sleep(0.02)
        raise TimeoutError(f"game view did not switch to #{index}; current view is #{self.current_index()}")

    def switch_surface_to(self, index: int) -> GameView:
        """Display one hosted surface without changing the foreground window."""
        if sys.platform != "win32":
            raise RuntimeError("background surface switching requires Windows")
        views = self.views()
        if not 1 <= index <= len(views):
            raise ValueError(f"game view index must be between 1 and {len(views)}")
        user32 = ctypes.windll.user32
        foreground_before = int(user32.GetForegroundWindow())
        SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER = 0x0002, 0x0001, 0x0004
        SWP_NOACTIVATE, SWP_SHOWWINDOW, SWP_HIDEWINDOW = 0x0010, 0x0040, 0x0080
        flags_base = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        target = views[index - 1]
        for view in views:
            flags = flags_base | (SWP_SHOWWINDOW if view.hwnd == target.hwnd else SWP_HIDEWINDOW)
            if not user32.SetWindowPos(int(view.hwnd), 0, 0, 0, 0, 0, flags):
                raise ctypes.WinError()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.current_surface_index() == index:
                foreground_after = int(user32.GetForegroundWindow())
                if foreground_after != foreground_before:
                    raise RuntimeError(
                        "foreground window changed during background surface switch: "
                        f"before={foreground_before}, after={foreground_after}"
                    )
                return self.views()[index - 1]
            time.sleep(0.02)
        raise TimeoutError(
            f"WSGAME surface did not switch to #{index}; current surface is #{self.current_surface_index()}"
        )

    def switch_next(self) -> GameView:
        views = self.views()
        if not views:
            raise RuntimeError("no WSGAME views were discovered")
        return self.switch_to((self.current_index() % len(views)) + 1)

    def _switch_with_ctrl_tab(self, index: int, current: int, count: int) -> None:
        steps = (index - current) % count
        for _ in range(steps):
            self._send_ctrl_tab()
            time.sleep(self.switch_delay)

    def _tab_hwnd(self) -> int:
        tab_hwnd = find_tab_control(self.parent_hwnd)
        if tab_hwnd is None:
            raise RuntimeError("SysTabControl32 was not found")
        return tab_hwnd

    def _activate_parent(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("game-view switching requires Windows")
        user32 = ctypes.windll.user32
        user32.ShowWindow(self.parent_hwnd, 9)
        user32.SetForegroundWindow(self.parent_hwnd)
        time.sleep(0.05)
        foreground = int(user32.GetForegroundWindow())
        if foreground != int(self.parent_hwnd):
            raise RuntimeError(f"could not activate host window; foreground hwnd={foreground}, expected={self.parent_hwnd}")

    @staticmethod
    def _send_ctrl_tab() -> None:
        if sys.platform != "win32":
            raise RuntimeError("game-view switching requires Windows")
        user32 = ctypes.windll.user32
        user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(0x09, 0, 0, 0)
        user32.keybd_event(0x09, 0, 0x0002, 0)
        user32.keybd_event(0x11, 0, 0x0002, 0)
