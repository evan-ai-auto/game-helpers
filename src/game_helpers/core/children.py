"""Win32 child-window discovery helpers.

Some desktop game launchers host multiple logical game instances inside one
 top-level window. Child-window discovery gives the automation layer a way to
 inspect that hierarchy before adding game-specific tab detection.
"""

from __future__ import annotations

import sys

from .models import Rect, WindowInfo


def list_child_windows(parent_hwnd: int, *, visible_only: bool = False) -> list[WindowInfo]:
    """Return direct child windows of ``parent_hwnd``.

    Bounds are converted to screen coordinates so child windows use the same
    coordinate convention as top-level :class:`WindowInfo` objects.
    """
    if sys.platform != "win32":
        return []

    import ctypes
    from ctypes import wintypes

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
                hwnd=hwnd,
                title=title_buffer.value,
                class_name=class_buffer.value,
                bounds=Rect(rect.left, rect.top, rect.right, rect.bottom),
                visible=visible,
            )
        )
        return True

    user32.EnumChildWindows(wintypes.HWND(parent_hwnd), enum_child_proc(callback), 0)
    return result
