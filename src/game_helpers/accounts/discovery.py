"""Discovery and selection models for hosted game accounts."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from game_helpers.core.game_view import GameView, discover_game_views
from game_helpers.tasks.models import AccountCandidate


def process_id(hwnd: int) -> int | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value) or None


def discover_accounts(parent_hwnd: int) -> list[AccountCandidate]:
    """Return all WSGAME views; login/character recognition is pluggable.

    The initial MVP intentionally does not guess an account name from pixels.
    A later perception adapter can fill ``account_name``/``character_name``
    after OCR or template/vision recognition.
    """
    views: list[GameView] = discover_game_views(parent_hwnd)
    return [
        AccountCandidate(
            view_index=view.index,
            hwnd=view.hwnd,
            process_id=process_id(view.hwnd),
            logged_in=None,
            metadata={"visible": view.visible, "class_name": view.window.class_name},
        )
        for view in views
    ]
