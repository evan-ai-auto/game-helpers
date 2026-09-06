"""Background host helpers for surface-transition sampling.

Primary path: switch surface + native tab without activating the game, then wait
until the host client grows to the target resolution via the game's own layout.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ParentWindowRestore:
    hwnd: int
    left: int
    top: int
    width: int
    height: int
    changed: bool


def _foreground_hwnd() -> int:
    if sys.platform != "win32":
        raise RuntimeError("foreground query requires Windows")
    import ctypes

    return int(ctypes.windll.user32.GetForegroundWindow())


def get_client_size(hwnd: int) -> tuple[int, int]:
    if sys.platform != "win32":
        raise RuntimeError("client size requires Windows")
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        raise ctypes.WinError()
    return int(rect.right - rect.left), int(rect.bottom - rect.top)


def switch_view_background(manager, index: int) -> None:
    """Show one hosted view without bringing the game to the foreground.

    Matches the MVP-2 character-selection sequence: ``switch_surface_to`` then
    background ``switch_to`` (native ``select_tab``). Ctrl+Tab / SetForeground
    are intentionally not used.
    """
    if getattr(manager, "activate_before_switch", False):
        raise RuntimeError(
            "switch_view_background requires activate_before_switch=False "
            "(foreground Ctrl+Tab is not allowed for this probe)"
        )
    foreground_before = _foreground_hwnd()
    manager.switch_surface_to(index)
    manager.switch_to(index)
    if manager.current_surface_index() != index:
        raise RuntimeError(f"surface did not become #{index}")
    if manager.current_index() != index:
        raise RuntimeError(f"native tab did not become #{index}")
    foreground_after = _foreground_hwnd()
    if foreground_after != foreground_before:
        raise RuntimeError(
            "foreground window changed during background view switch: "
            f"before={foreground_before}, after={foreground_after}"
        )


def wait_parent_client_at_least(
    parent_hwnd: int,
    min_width: int,
    min_height: int,
    *,
    timeout: float = 3.0,
    poll: float = 0.02,
) -> tuple[int, int]:
    """Poll until the host client is large enough for the target surface."""
    deadline = time.monotonic() + timeout
    last = get_client_size(parent_hwnd)
    while time.monotonic() < deadline:
        last = get_client_size(parent_hwnd)
        if last[0] >= min_width and last[1] >= min_height:
            return last
        time.sleep(poll)
    raise RuntimeError(
        "后台 Tab 切换未触发宿主重排到目标分辨率: "
        f"have={last[0]}x{last[1]}, need>={min_width}x{min_height}. "
        "不会回退到前台 Ctrl+Tab；请确认该账号在后台 select_tab 后宿主是否会放大。"
    )


def ensure_parent_client_size(
    hwnd: int,
    min_width: int,
    min_height: int,
    *,
    padding: int = 8,
) -> ParentWindowRestore:
    """Legacy SetWindowPos helper retained for experiments; not used by the probe."""
    if sys.platform != "win32":
        raise RuntimeError("parent resize requires Windows")
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd_w = wintypes.HWND(hwnd)
    outer = wintypes.RECT()
    if not user32.GetWindowRect(hwnd_w, ctypes.byref(outer)):
        raise ctypes.WinError()
    left, top = int(outer.left), int(outer.top)
    outer_w = int(outer.right - outer.left)
    outer_h = int(outer.bottom - outer.top)
    client_w, client_h = get_client_size(hwnd)
    token = ParentWindowRestore(
        hwnd=int(hwnd),
        left=left,
        top=top,
        width=outer_w,
        height=outer_h,
        changed=False,
    )
    need_w = int(min_width) + int(padding)
    need_h = int(min_height) + int(padding)
    if client_w >= need_w and client_h >= need_h:
        return token

    frame_w = max(0, outer_w - client_w)
    frame_h = max(0, outer_h - client_h)
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    if not user32.SetWindowPos(
        hwnd_w,
        None,
        left,
        top,
        need_w + frame_w,
        need_h + frame_h,
        SWP_NOZORDER | SWP_NOACTIVATE,
    ):
        raise ctypes.WinError()
    new_client_w, new_client_h = get_client_size(hwnd)
    if new_client_w < need_w or new_client_h < need_h:
        restore_parent_window(
            ParentWindowRestore(
                hwnd=int(hwnd),
                left=token.left,
                top=token.top,
                width=token.width,
                height=token.height,
                changed=True,
            )
        )
        raise RuntimeError(
            "parent client still too small after resize: "
            f"have={new_client_w}x{new_client_h}, need>={need_w}x{need_h}"
        )
    return ParentWindowRestore(
        hwnd=int(hwnd),
        left=token.left,
        top=token.top,
        width=token.width,
        height=token.height,
        changed=True,
    )


def restore_parent_window(token: ParentWindowRestore) -> None:
    if not token.changed:
        return
    if sys.platform != "win32":
        raise RuntimeError("parent restore requires Windows")
    import ctypes
    from ctypes import wintypes

    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    if not ctypes.windll.user32.SetWindowPos(
        wintypes.HWND(token.hwnd),
        None,
        token.left,
        token.top,
        token.width,
        token.height,
        SWP_NOZORDER | SWP_NOACTIVATE,
    ):
        raise ctypes.WinError()
