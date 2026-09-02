"""Windows window discovery helpers.

The module has a platform-neutral API and a Win32 implementation that is
loaded lazily. This keeps imports and tests usable on non-Windows machines.
"""

from __future__ import annotations

import sys
from typing import Iterable

from .models import Rect, WindowInfo


def list_windows(*, visible_only: bool = True) -> list[WindowInfo]:
    """Return top-level windows visible to the current desktop session."""
    if sys.platform != "win32":
        return []

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    result: list[WindowInfo] = []

    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if visible_only and not user32.IsWindowVisible(hwnd):
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
                hwnd=hwnd,
                title=title_buffer.value,
                class_name=class_buffer.value,
                bounds=Rect(rect.left, rect.top, rect.right, rect.bottom),
                visible=bool(user32.IsWindowVisible(hwnd)),
            )
        )
        return True

    user32.EnumWindows(enum_windows_proc(callback), 0)
    return result


def find_window(title: str, *, exact: bool = False) -> WindowInfo | None:
    """Find the first top-level window whose title matches ``title``."""
    candidates: Iterable[WindowInfo] = list_windows()
    for window in candidates:
        if (window.title == title) if exact else (title.lower() in window.title.lower()):
            return window
    return None
