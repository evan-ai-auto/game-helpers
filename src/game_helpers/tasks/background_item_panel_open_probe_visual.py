"""Visual verification helpers for the background item-panel open probe."""
from __future__ import annotations

import time

from ..core.view_manager import GameViewManager
from .probe_win32 import foreground_hwnd
from .visual_state import detect_visual_state, make_visual_state_verifier


def verify_capture(capture, hwnd: int, profile, *, timeout: float, poll_interval: float):
    """Poll visual state against one known capture target without clicking."""
    verifier = make_visual_state_verifier(lambda: capture.capture(hwnd), profile)
    deadline = time.monotonic() + timeout
    while True:
        value = verifier()
        if value is not None:
            return value
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(poll_interval, remaining))


def refresh_surface_for_capture(
    manager: GameViewManager,
    selected_view_index: int,
    original_foreground: int,
) -> bool:
    """Force a background-safe WSGAME repaint by switching away and back."""
    views = manager.views()
    if len(views) <= 1:
        return False

    refresh_index = next(index for index in range(1, len(views) + 1) if index != selected_view_index)
    manager.switch_surface_to(refresh_index)
    manager.switch_surface_to(selected_view_index)

    foreground = foreground_hwnd()
    if foreground != original_foreground:
        raise RuntimeError(
            "foreground window changed during visual refresh: "
            f"before={original_foreground}, after={foreground}"
        )
    return True


def print_visual_diagnostic(label: str, frame, profile) -> None:
    """Print one-shot detector evidence so false negatives are distinguishable."""
    observation = detect_visual_state(frame, profile)
    print(f"visual_diagnostic_{label}_status={observation.status}")
    print(f"visual_diagnostic_{label}_confidence={observation.confidence:.6f}")
    print(f"visual_diagnostic_{label}_origin={observation.origin}")
    print(f"visual_diagnostic_{label}_anchor_scores={observation.anchor_scores}")
    print(f"visual_diagnostic_{label}_evidence={observation.evidence}")
