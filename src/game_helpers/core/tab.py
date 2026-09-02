"""Win32 tab-control helpers for hosted game views.

The game application uses a standard ``SysTabControl32`` and keeps only the
selected ``WSGAME`` child visible. A hidden WSGAME child may not have an
independent rendered surface, so capturing it directly can return the
currently displayed game's pixels. The safe first implementation therefore
selects the requested tab through the normal tab control, waits for the
corresponding child to become visible, and can restore the original tab.
"""

from __future__ import annotations

import sys
import time

from .children import list_child_windows


def find_tab_control(parent_hwnd: int) -> int | None:
    """Return the first standard SysTabControl32 child of ``parent_hwnd``."""
    for child in list_child_windows(parent_hwnd, visible_only=False):
        if child.class_name.lower() == "systabcontrol32":
            return child.hwnd
    return None


def current_tab_index(tab_hwnd: int) -> int:
    """Return the zero-based selected tab index."""
    if sys.platform != "win32":
        raise RuntimeError("tab control operations are only available on Windows")

    import ctypes

    TCM_GETCURSEL = 0x130B
    return int(ctypes.windll.user32.SendMessageW(tab_hwnd, TCM_GETCURSEL, 0, 0))


def _tab_center(tab_hwnd: int, index: int) -> tuple[int, int]:
    import ctypes
    from ctypes import wintypes

    TCM_GETITEMRECT = 0x130A
    rect = wintypes.RECT()
    result = ctypes.windll.user32.SendMessageW(
        tab_hwnd,
        TCM_GETITEMRECT,
        index,
        ctypes.byref(rect),
    )
    if not result:
        raise RuntimeError(f"could not get rectangle for tab {index}")
    return ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)


def select_tab(tab_hwnd: int, index: int) -> None:
    """Select a tab using normal mouse messages so the parent gets notifications."""
    if sys.platform != "win32":
        raise RuntimeError("tab control operations are only available on Windows")
    if index < 0:
        raise ValueError("tab index must be non-negative")

    import ctypes

    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    MK_LBUTTON = 0x0001
    x, y = _tab_center(tab_hwnd, index)
    lparam = (y << 16) | (x & 0xFFFF)
    user32 = ctypes.windll.user32
    user32.SendMessageW(tab_hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    user32.SendMessageW(tab_hwnd, WM_LBUTTONUP, 0, lparam)


def wait_for_game_view(parent_hwnd: int, game_hwnd: int, *, timeout: float = 2.0) -> bool:
    """Wait until the requested WSGAME child becomes visible."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for child in list_child_windows(parent_hwnd, visible_only=False):
            if child.hwnd == game_hwnd:
                return child.visible
        time.sleep(0.02)
    return False


class GameViewTabSession:
    """Temporarily activate a game tab and restore the original tab on exit."""

    def __init__(self, parent_hwnd: int, target_game_hwnd: int, *, timeout: float = 2.0):
        self.parent_hwnd = parent_hwnd
        self.target_game_hwnd = target_game_hwnd
        self.timeout = timeout
        self.tab_hwnd: int | None = None
        self.original_index: int | None = None

    def __enter__(self) -> "GameViewTabSession":
        self.tab_hwnd = find_tab_control(self.parent_hwnd)
        if self.tab_hwnd is None:
            raise RuntimeError("SysTabControl32 was not found")

        from .game_view import discover_game_views

        views = discover_game_views(self.parent_hwnd)
        target_index = next((i for i, view in enumerate(views) if view.hwnd == self.target_game_hwnd), None)
        if target_index is None:
            raise RuntimeError(f"game window {self.target_game_hwnd} is not a discovered WSGAME child")

        self.original_index = current_tab_index(self.tab_hwnd)
        if self.original_index != target_index:
            select_tab(self.tab_hwnd, target_index)
            if not wait_for_game_view(self.parent_hwnd, self.target_game_hwnd, timeout=self.timeout):
                raise RuntimeError(f"game view {target_index + 1} did not become visible")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.tab_hwnd is None or self.original_index is None:
            return
        if current_tab_index(self.tab_hwnd) != self.original_index:
            select_tab(self.tab_hwnd, self.original_index)
            time.sleep(0.05)
