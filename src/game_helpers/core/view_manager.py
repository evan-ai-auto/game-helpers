"""High-level switching between hosted game views.

The game hosts multiple ``WSGAME`` views inside one top-level frame. Direct
Windows Graphics Capture of those child HWNDs is not supported by the current
capture backend, while the application exposes ``Ctrl+Tab`` as its native view
switcher. This manager uses that native shortcut and leaves capture to the
parent window.

The key shortcut uses ordinary desktop keyboard input. It therefore requires
the hosted application to be the foreground input target; this module does not
attempt background input injection or process-level input manipulation.
"""

from __future__ import annotations

import sys
import time

from .game_view import GameView, discover_game_views
from .tab import current_tab_index, find_tab_control


class GameViewManager:
    """Switch and inspect game views hosted by one top-level window."""

    def __init__(
        self,
        parent_hwnd: int,
        *,
        switch_delay: float = 0.15,
        timeout: float = 2.0,
    ) -> None:
        self.parent_hwnd = parent_hwnd
        self.switch_delay = switch_delay
        self.timeout = timeout

    def views(self) -> list[GameView]:
        """Return the currently discovered WSGAME views."""
        return discover_game_views(self.parent_hwnd)

    def current_index(self) -> int:
        """Return the current one-based game-view index."""
        tab_hwnd = self._tab_hwnd()
        return current_tab_index(tab_hwnd) + 1

    def switch_to(self, index: int) -> GameView:
        """Switch to a one-based view index using the application's Ctrl+Tab."""
        views = self.views()
        if not 1 <= index <= len(views):
            raise ValueError(f"game view index must be between 1 and {len(views)}")

        current = self.current_index()
        if current == index:
            return views[index - 1]

        # Ctrl+Tab advances one view. Repeating it handles more than two views
        # without assuming a particular number of hosted accounts.
        steps = (index - current) % len(views)
        for _ in range(steps):
            self._send_ctrl_tab()
            time.sleep(self.switch_delay)

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

    def _tab_hwnd(self) -> int:
        tab_hwnd = find_tab_control(self.parent_hwnd)
        if tab_hwnd is None:
            raise RuntimeError("SysTabControl32 was not found")
        return tab_hwnd

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
