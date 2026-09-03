"""High-level switching between hosted game views."""

from __future__ import annotations

import sys
import time

from .game_view import GameView, discover_game_views
from .tab import current_tab_index, find_tab_control, select_tab


class GameViewManager:
    """Switch and inspect game views hosted by one top-level window.

    Tab selection and displayed-surface selection are kept synchronized. The
    background-safe path updates the native tab selection without activating
    the host window, then explicitly binds WSGAME child visibility so capture
    and the UI's selected-tab title describe the same game instance.
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
        """Return the current one-based native tab index."""
        return current_tab_index(self._tab_hwnd()) + 1

    def current_surface_index(self) -> int:
        """Return the one-based WSGAME child that is currently visible."""
        views = self.views()
        for index, view in enumerate(views, start=1):
            if view.window.visible:
                return index
        raise RuntimeError("no visible WSGAME surface was found")

    def switch_to(self, index: int) -> GameView:
        """Switch the native tab to a one-based view index."""
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

        raise TimeoutError(
            f"game view did not switch to #{index}; current view is #{self.current_index()}"
        )

    def switch_surface_to(self, index: int) -> GameView:
        """Display one WSGAME child and synchronize its native tab selection.

        This is the background-safe route validated by the surface probe. It
        selects the corresponding native tab with ``SendMessage`` (no mouse or
        foreground activation), then explicitly shows the target WSGAME child
        and hides siblings. Keeping both states synchronized prevents the host
        UI from showing one character's tab title while rendering another
        character's game surface.
        """
        if sys.platform != "win32":
            raise RuntimeError("background surface switching requires Windows")

        views = self.views()
        if not 1 <= index <= len(views):
            raise ValueError(f"game view index must be between 1 and {len(views)}")

        import ctypes

        user32 = ctypes.windll.user32
        foreground_before = int(user32.GetForegroundWindow())
        SW_HIDE = 0
        SW_SHOWNOACTIVATE = 4
        target = views[index - 1]

        # Keep the host's visible tab/title synchronized with the surface.
        select_tab(self._tab_hwnd(), index - 1)

        for view in views:
            user32.ShowWindow(
                view.hwnd,
                SW_SHOWNOACTIVATE if view.hwnd == target.hwnd else SW_HIDE,
            )

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            current_tab = self.current_index()
            current_surface = self.current_surface_index()
            if current_tab == index and current_surface == index:
                foreground_after = int(user32.GetForegroundWindow())
                if foreground_after != foreground_before:
                    raise RuntimeError(
                        "foreground window changed during background surface switch: "
                        f"before={foreground_before}, after={foreground_after}"
                    )
                return self.views()[index - 1]
            time.sleep(0.02)

        raise TimeoutError(
            f"WSGAME selection did not synchronize for #{index}; "
            f"tab=#{self.current_index()}, surface=#{self.current_surface_index()}"
        )

    def switch_next(self) -> GameView:
        """Advance to the next hosted game view using native tab selection."""
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
