"""High-level switching between hosted game views."""

from __future__ import annotations

import sys
import time

from .game_view import GameView, discover_game_views
from .tab import current_tab_index, find_tab_control, select_tab


class GameViewManager:
    """Switch and inspect game views hosted by one top-level window.

    By default, switching uses the Win32 tab-control API and does not activate
    the host window. This keeps the game in the background while another
    application remains foreground. ``activate_before_switch=True`` is kept as
    an explicit fallback for applications that only respond to Ctrl+Tab.
    """

    def __init__(
        self,
        parent_hwnd: int,
        *,
        switch_delay: float = 0.15,
        timeout: float = 2.0,
        activate_before_switch: bool = False,
    ) -> None:
        self.parent_hwnd = parent_hwnd
        self.switch_delay = switch_delay
        self.timeout = timeout
        self.activate_before_switch = activate_before_switch

    def views(self) -> list[GameView]:
        """Return the currently discovered WSGAME views."""
        return discover_game_views(self.parent_hwnd)

    def current_index(self) -> int:
        """Return the current one-based game-view index."""
        return current_tab_index(self._tab_hwnd()) + 1

    def switch_to(self, index: int) -> GameView:
        """Switch to a one-based view index without foreground activation by default."""
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
            # Directly drive the native SysTabControl32. No keyboard input and
            # no foreground-window change are required.
            select_tab(self._tab_hwnd(), index - 1)

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.current_index() == index:
                return self.views()[index - 1]
            time.sleep(0.02)

        raise TimeoutError(
            f"game view did not switch to #{index}; current view is #{self.current_index()}"
        )

    def switch_next(self) -> GameView:
        """Advance to the next hosted game view."""
        views = self.views()
        if not views:
            raise RuntimeError("no WSGAME views were discovered")
        target = (self.current_index() % len(views)) + 1
        return self.switch_to(target)

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
        """Make the hosted application's top-level window the input target."""
        if sys.platform != "win32":
            raise RuntimeError("game-view switching requires Windows")

        import ctypes

        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        user32.ShowWindow(self.parent_hwnd, SW_RESTORE)
        user32.SetForegroundWindow(self.parent_hwnd)
        time.sleep(0.05)

        foreground = int(user32.GetForegroundWindow())
        if foreground != int(self.parent_hwnd):
            raise RuntimeError(
                f"could not activate host window; foreground hwnd={foreground}, "
                f"expected={self.parent_hwnd}"
            )

    @staticmethod
    def _send_ctrl_tab() -> None:
        if sys.platform != "win32":
            raise RuntimeError("game-view switching requires Windows")

        import ctypes

        user32 = ctypes.windll.user32
        VK_CONTROL = 0x11
        VK_TAB = 0x09
        KEYEVENTF_KEYUP = 0x0002

        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_TAB, 0, 0, 0)
        user32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
