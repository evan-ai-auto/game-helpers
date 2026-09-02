"""Win32 diagnostics for understanding hosted game-window rendering."""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowDiagnostics:
    """Useful Win32 metadata for deciding which HWND owns rendered pixels."""

    hwnd: int
    parent_hwnd: int
    owner_hwnd: int
    root_hwnd: int
    thread_id: int
    process_id: int
    visible: bool
    cloaked: bool | None
    style: int
    exstyle: int
    class_name: str
    title: str


def diagnose_window(hwnd: int) -> WindowDiagnostics:
    """Read non-invasive Win32 metadata for ``hwnd``.

    This deliberately does not capture pixels or activate/focus the window.
    """
    if sys.platform != "win32":
        raise RuntimeError("window diagnostics are only available on Windows")

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd_value = wintypes.HWND(hwnd)

    title_length = user32.GetWindowTextLengthW(hwnd_value)
    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
    user32.GetWindowTextW(hwnd_value, title_buffer, title_length + 1)

    class_buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd_value, class_buffer, 256)

    process_id = wintypes.DWORD()
    thread_id = int(user32.GetWindowThreadProcessId(hwnd_value, ctypes.byref(process_id)))

    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        GetWindowLongPtrW = user32.GetWindowLongPtrW
        GetWindowLongPtrW.restype = ctypes.c_ssize_t
        style = int(GetWindowLongPtrW(hwnd_value, GWL_STYLE))
        exstyle = int(GetWindowLongPtrW(hwnd_value, GWL_EXSTYLE))
    else:
        GetWindowLongW = user32.GetWindowLongW
        GetWindowLongW.restype = ctypes.c_long
        style = int(GetWindowLongW(hwnd_value, GWL_STYLE))
        exstyle = int(GetWindowLongW(hwnd_value, GWL_EXSTYLE))

    GA_ROOT = 2
    root_hwnd = int(user32.GetAncestor(hwnd_value, GA_ROOT))
    parent_hwnd = int(user32.GetParent(hwnd_value))
    GW_OWNER = 4
    owner_hwnd = int(user32.GetWindow(hwnd_value, GW_OWNER))

    cloaked: bool | None = None
    try:
        dwmapi = ctypes.windll.dwmapi
        DWMWA_CLOAKED = 14
        cloaked_value = wintypes.DWORD()
        hr = int(
            dwmapi.DwmGetWindowAttribute(
                hwnd_value,
                DWMWA_CLOAKED,
                ctypes.byref(cloaked_value),
                ctypes.sizeof(cloaked_value),
            )
        )
        if hr >= 0:
            cloaked = bool(cloaked_value.value)
    except (AttributeError, OSError):
        cloaked = None

    return WindowDiagnostics(
        hwnd=hwnd,
        parent_hwnd=parent_hwnd,
        owner_hwnd=owner_hwnd,
        root_hwnd=root_hwnd,
        thread_id=thread_id,
        process_id=int(process_id.value),
        visible=bool(user32.IsWindowVisible(hwnd_value)),
        cloaked=cloaked,
        style=style,
        exstyle=exstyle,
        class_name=class_buffer.value,
        title=title_buffer.value,
    )
