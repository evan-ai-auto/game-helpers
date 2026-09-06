"""Win32 top-level window discovery implementation."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Iterable

from ...core.models import Rect, WindowInfo


def _window_info_from_hwnd(hwnd: int) -> WindowInfo:
    user32 = ctypes.windll.user32
    hwnd_value = wintypes.HWND(hwnd)
    if not user32.IsWindow(hwnd_value):
        raise ValueError(f"invalid window hwnd={hwnd}")
    length = user32.GetWindowTextLengthW(hwnd_value)
    title_buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd_value, title_buffer, length + 1)
    class_buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd_value, class_buffer, 256)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd_value, ctypes.byref(rect))
    return WindowInfo(
        hwnd=int(hwnd), title=title_buffer.value, class_name=class_buffer.value,
        bounds=Rect(rect.left, rect.top, rect.right, rect.bottom),
        visible=bool(user32.IsWindowVisible(hwnd_value)),
    )


def get_window_info(hwnd: int) -> WindowInfo:
    return _window_info_from_hwnd(int(hwnd))


def list_windows(*, visible_only: bool = True) -> list[WindowInfo]:
    user32 = ctypes.windll.user32
    result: list[WindowInfo] = []
    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True
        result.append(_window_info_from_hwnd(hwnd))
        return True

    user32.EnumWindows(enum_windows_proc(callback), 0)
    return result


def find_window(title: str, *, exact: bool = False) -> WindowInfo | None:
    candidates: Iterable[WindowInfo] = list_windows()
    for window in candidates:
        if (window.title == title) if exact else (title.lower() in window.title.lower()):
            return window
    return None
