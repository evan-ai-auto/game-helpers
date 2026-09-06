"""Win32 child-window discovery implementation."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from ...core.models import Rect, WindowInfo


def list_child_windows(parent_hwnd: int, *, visible_only: bool = False) -> list[WindowInfo]:
    """Return direct child windows of ``parent_hwnd`` in screen coordinates."""
    user32 = ctypes.windll.user32
    result: list[WindowInfo] = []
    enum_child_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        visible = bool(user32.IsWindowVisible(hwnd))
        if visible_only and not visible:
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buffer, 256)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        result.append(
            WindowInfo(
                hwnd=int(hwnd),
                title=title_buffer.value,
                class_name=class_buffer.value,
                bounds=Rect(rect.left, rect.top, rect.right, rect.bottom),
                visible=visible,
            )
        )
        return True

    user32.EnumChildWindows(wintypes.HWND(parent_hwnd), enum_child_proc(callback), 0)
    return result
