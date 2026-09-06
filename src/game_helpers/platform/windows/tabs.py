"""Win32 tab-control and hosted-view switching implementation."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from .children import list_child_windows


def find_tab_control(parent_hwnd: int) -> int | None:
    for child in list_child_windows(parent_hwnd, visible_only=False):
        if child.class_name.lower() == "systabcontrol32":
            return child.hwnd
    return None


def current_tab_index(tab_hwnd: int) -> int:
    if sys.platform != "win32":
        raise RuntimeError("tab control operations are only available on Windows")
    return int(ctypes.windll.user32.SendMessageW(tab_hwnd, 0x130B, 0, 0))


def _notify_tab_parent(tab_hwnd: int, code: int) -> int:
    class NMHDR(ctypes.Structure):
        _fields_ = [("hwndFrom", wintypes.HWND), ("idFrom", ctypes.c_size_t), ("code", wintypes.UINT)]

    parent = ctypes.windll.user32.GetParent(tab_hwnd)
    if not parent:
        raise RuntimeError(f"could not find parent for tab control {tab_hwnd}")
    hdr = NMHDR(
        hwndFrom=tab_hwnd,
        idFrom=ctypes.windll.user32.GetDlgCtrlID(tab_hwnd),
        code=code,
    )
    send_message = ctypes.windll.user32.SendMessageW
    send_message.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    send_message.restype = ctypes.c_ssize_t
    return int(send_message(parent, 0x004E, hdr.idFrom, ctypes.addressof(hdr)))


def select_tab(tab_hwnd: int, index: int) -> None:
    if sys.platform != "win32":
        raise RuntimeError("tab control operations are only available on Windows")
    if index < 0:
        raise ValueError("tab index must be non-negative")
    if _notify_tab_parent(tab_hwnd, -551):
        raise RuntimeError(f"tab {index} change was vetoed by the parent")
    result = ctypes.windll.user32.SendMessageW(tab_hwnd, 0x130C, index, 0)
    if result == -1:
        raise RuntimeError(f"could not select tab {index}")
    _notify_tab_parent(tab_hwnd, -552)


def wait_for_game_view(parent_hwnd: int, game_hwnd: int, *, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for child in list_child_windows(parent_hwnd, visible_only=False):
            if child.hwnd == game_hwnd:
                return child.visible
        time.sleep(0.02)
    return False


class GameViewTabSession:
    """Temporarily select a hosted game tab and restore the original tab."""

    def __init__(self, parent_hwnd: int, target_game_hwnd: int, *, timeout: float = 2.0):
        self.parent_hwnd = parent_hwnd
        self.target_game_hwnd = target_game_hwnd
        self.timeout = timeout
        self.tab_hwnd: int | None = None
        self.original_index: int | None = None
        self.target_index: int | None = None

    def __enter__(self) -> "GameViewTabSession":
        self.tab_hwnd = find_tab_control(self.parent_hwnd)
        if self.tab_hwnd is None:
            raise RuntimeError("SysTabControl32 was not found")
        from ...core.game_view import discover_game_views
        views = discover_game_views(self.parent_hwnd)
        self.target_index = next((i for i, view in enumerate(views) if view.hwnd == self.target_game_hwnd), None)
        if self.target_index is None:
            raise RuntimeError(f"game window {self.target_game_hwnd} is not a discovered WSGAME child")
        self.original_index = current_tab_index(self.tab_hwnd)
        if self.original_index != self.target_index:
            try:
                select_tab(self.tab_hwnd, self.target_index)
            except Exception:
                self._restore_original()
                raise
            if current_tab_index(self.tab_hwnd) != self.target_index:
                self._restore_original()
                raise RuntimeError(f"tab selection did not reach index {self.target_index}")
            time.sleep(0.10)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._restore_original()

    def _restore_original(self) -> None:
        if self.tab_hwnd is None or self.original_index is None:
            return
        try:
            if current_tab_index(self.tab_hwnd) != self.original_index:
                select_tab(self.tab_hwnd, self.original_index)
                time.sleep(0.10)
        except Exception:
            pass
