"""Verification that a selected character view is bound to the captured surface."""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass

from ..capture import WindowsGraphicsCapture
from ..core.game_view import discover_game_views
from ..core.view_manager import GameViewManager


class BindingStatus(str):
    VERIFIED = "verified"
    STALE = "stale"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class RenderBinding:
    """Evidence linking a selected WSGAME instance to a captured frame."""

    status: str
    view_index: int
    hwnd: int
    process_id: int | None
    identity: str | None
    title: str
    visible_surface_index: int
    frame_sha256: str
    foreground_hwnd_before: int
    foreground_hwnd_after: int
    frame_changed_from_previous: bool


def _pid(hwnd: int) -> int | None:
    import ctypes

    process_id = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value) or None


def verify_render_binding(
    parent_hwnd: int,
    view_index: int,
    *,
    identity: str | None = None,
    previous_frame_sha256: str | None = None,
    settle_delay: float = 0.25,
) -> RenderBinding:
    """Switch a selected view in the background and verify its rendered surface.

    The check deliberately treats HWND/PID/title as window identity and the
    captured frame as rendered-state evidence. A title alone never proves the
    pixels belong to that character.
    """
    if sys.platform != "win32":
        raise RuntimeError("render binding verification requires Windows")

    import ctypes
    import time

    manager = GameViewManager(parent_hwnd, timeout=2.0)
    views = discover_game_views(parent_hwnd)
    if not 1 <= view_index <= len(views):
        raise ValueError(f"game view index must be between 1 and {len(views)}")

    foreground_before = int(ctypes.windll.user32.GetForegroundWindow())
    selected = manager.switch_surface_to(view_index)
    time.sleep(settle_delay)
    visible_index = manager.current_surface_index()
    frame = WindowsGraphicsCapture().capture(parent_hwnd)
    frame_sha = hashlib.sha256(frame.data).hexdigest()
    foreground_after = int(ctypes.windll.user32.GetForegroundWindow())

    same_surface = visible_index == view_index
    foreground_ok = foreground_after == foreground_before
    changed = previous_frame_sha256 is None or frame_sha != previous_frame_sha256
    status = BindingStatus.VERIFIED if same_surface and foreground_ok else BindingStatus.BLOCKED

    return RenderBinding(
        status=status,
        view_index=view_index,
        hwnd=selected.hwnd,
        process_id=_pid(selected.hwnd),
        identity=identity,
        title=selected.window.title,
        visible_surface_index=visible_index,
        frame_sha256=frame_sha,
        foreground_hwnd_before=foreground_before,
        foreground_hwnd_after=foreground_after,
        frame_changed_from_previous=changed,
    )
