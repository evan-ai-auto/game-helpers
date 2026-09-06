"""Reusable manual coordinate collection (F8 hover assist).

This is an **asset-calibration** capability, not part of normal background
automation. It may temporarily bring the game to the foreground so the operator
can hover a UI control until a tooltip is visible, then press F8 to capture the
exact screen → client mapping.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Literal

from .background_context import foreground_hwnd

VK_F8 = 0x77
VK_ESCAPE = 0x1B

CoordSource = Literal["auto", "manual", "auto_then_manual"]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


@dataclass(frozen=True)
class ManualCoordinateSample:
    """One operator-confirmed hover point mapped into a target window's client space."""

    screen: tuple[int, int]
    client: tuple[int, int]
    target_hwnd: int
    foreground_hwnd_at_capture: int


def wait_for_f8(*, cancel_on_escape: bool = True) -> bool:
    """Block until F8 (True) or ESC (False)."""
    if sys.platform != "win32":
        raise RuntimeError("manual coordinate capture requires Windows")
    user32 = ctypes.windll.user32
    while True:
        if cancel_on_escape and (user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001):
            return False
        if user32.GetAsyncKeyState(VK_F8) & 0x0001:
            while user32.GetAsyncKeyState(VK_F8) & 0x8000:
                time.sleep(0.02)
            return True
        time.sleep(0.03)


def cursor_screen_pos() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def screen_to_client(hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
    point = POINT(int(screen_x), int(screen_y))
    if not ctypes.windll.user32.ScreenToClient(int(hwnd), ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def set_foreground(hwnd: int, *, timeout: float = 2.0) -> None:
    """Best-effort foreground handoff used only by manual-assist calibration."""
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    current = foreground_hwnd()
    if current == int(hwnd):
        return
    current_thread = int(user32.GetWindowThreadProcessId(current, None)) if current else 0
    target_thread = int(user32.GetWindowThreadProcessId(int(hwnd), None))
    attached = False
    try:
        if current_thread and target_thread and current_thread != target_thread:
            if not user32.AttachThreadInput(current_thread, target_thread, True):
                raise ctypes.WinError()
            attached = True
        user32.BringWindowToTop(int(hwnd))
        user32.SetForegroundWindow(int(hwnd))
        deadline = time.monotonic() + timeout
        while foreground_hwnd() != int(hwnd) and time.monotonic() < deadline:
            time.sleep(0.02)
        if foreground_hwnd() != int(hwnd):
            raise RuntimeError(
                f"无法将窗口提到前台 hwnd={hwnd}，当前前台={foreground_hwnd()}"
            )
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def collect_client_coordinate(
    target_hwnd: int,
    *,
    prompt: str,
    foreground_hwnd_for_hover: int | None = None,
    restore_foreground: int | None = None,
) -> ManualCoordinateSample:
    """Prompt the operator to hover a control, press F8, return client coords.

    ``foreground_hwnd_for_hover`` (usually the game parent) is raised only for
    this assist step. ``restore_foreground`` defaults to the pre-assist FG window.
    """
    if sys.platform != "win32":
        raise RuntimeError("manual coordinate capture requires Windows")

    previous_fg = foreground_hwnd()
    restore_to = previous_fg if restore_foreground is None else int(restore_foreground)
    hover_fg = int(foreground_hwnd_for_hover) if foreground_hwnd_for_hover else None

    print(prompt)
    print("操作：悬停到目标上（建议看到 tooltip）→ 保持鼠标不动 → 按 F8；取消按 ESC。")
    if hover_fg:
        print(f"[采坐标] 临时前台 hwnd={hover_fg} …")
        set_foreground(hover_fg)

    try:
        if not wait_for_f8():
            raise RuntimeError("已取消人工采坐标（ESC）。")
        screen = cursor_screen_pos()
        client = screen_to_client(target_hwnd, screen[0], screen[1])
        sample = ManualCoordinateSample(
            screen=screen,
            client=client,
            target_hwnd=int(target_hwnd),
            foreground_hwnd_at_capture=foreground_hwnd(),
        )
        print(f"coord_source=manual")
        print(f"cursor_screen={sample.screen}")
        print(f"click_client={sample.client}")
        return sample
    finally:
        if restore_to and foreground_hwnd() != restore_to:
            try:
                set_foreground(restore_to)
                print(f"[采坐标] 已恢复前台 hwnd={restore_to}")
            except Exception as exc:
                print(f"[采坐标] 恢复前台失败：{exc}")


def parse_coord_source(value: str) -> CoordSource:
    normalized = str(value).strip().lower().replace("-", "_")
    aliases = {
        "auto": "auto",
        "manual": "manual",
        "assist": "manual",
        "auto_then_manual": "auto_then_manual",
        "auto_or_manual": "auto_then_manual",
        "fallback": "auto_then_manual",
    }
    if normalized not in aliases:
        raise ValueError(
            "coord_source 仅支持 auto | manual | auto_then_manual "
            f"（收到 {value!r}）"
        )
    return aliases[normalized]  # type: ignore[return-value]
