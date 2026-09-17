"""Shared Win32 helpers for diagnostic background probes."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from ..core.view_manager import GameViewManager

VK_F8 = 0x77
VK_ESCAPE = 0x1B


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def cursor_pos() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def set_foreground(hwnd: int, timeout: float = 2.0) -> None:
    """Best-effort foreground handoff used only by diagnostic probes."""
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    current = foreground_hwnd()
    if current == hwnd:
        return
    current_thread = int(user32.GetWindowThreadProcessId(current, None)) if current else 0
    target_thread = int(user32.GetWindowThreadProcessId(hwnd, None))
    attached = False
    try:
        if current_thread and target_thread and current_thread != target_thread:
            if not user32.AttachThreadInput(current_thread, target_thread, True):
                raise ctypes.WinError()
            attached = True
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        deadline = time.monotonic() + timeout
        while foreground_hwnd() != hwnd and time.monotonic() < deadline:
            time.sleep(0.02)
        if foreground_hwnd() != hwnd:
            raise RuntimeError(f"failed to make foreground hwnd={hwnd}: current={foreground_hwnd()}")
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def restore_foreground(hwnd: int | None) -> bool:
    if not hwnd:
        return True
    set_foreground(int(hwnd))
    return foreground_hwnd() == int(hwnd)


def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = POINT(int(x), int(y))
    if not ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def client_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    return int(rect.right), int(rect.bottom)


def window_text(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    length = int(user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def parent(hwnd: int) -> int:
    return int(ctypes.windll.user32.GetParent(hwnd))


def root(hwnd: int) -> int:
    return int(ctypes.windll.user32.GetAncestor(hwnd, 2))


def window_from_point(x: int, y: int) -> int:
    return int(ctypes.windll.user32.WindowFromPoint(POINT(int(x), int(y))))


def ancestor_chain(hwnd: int, limit: int = 8) -> list[int]:
    result: list[int] = []
    current = int(hwnd)
    while current and len(result) < limit:
        result.append(current)
        current = parent(current)
    return result


def print_window(label: str, hwnd: int) -> None:
    if not hwnd:
        print(f"{label}=0")
        return
    print(
        f"{label}={hwnd} class='{window_class(hwnd)}' title='{window_text(hwnd)}' "
        f"parent={parent(hwnd)} root={root(hwnd)}"
    )


def wait_for_key_release(vk: int) -> None:
    user32 = ctypes.windll.user32
    while user32.GetAsyncKeyState(vk) & 0x8000:
        time.sleep(0.03)


def wait_for_f8() -> bool:
    user32 = ctypes.windll.user32
    while True:
        if user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001:
            return False
        if user32.GetAsyncKeyState(VK_F8) & 0x0001:
            wait_for_key_release(VK_F8)
            return True
        time.sleep(0.03)


def restore_context(manager: GameViewManager, surface: int | None, tab: int | None) -> None:
    if surface is not None:
        manager.switch_surface_to(surface)
    if tab is not None:
        manager.switch_to(tab)
