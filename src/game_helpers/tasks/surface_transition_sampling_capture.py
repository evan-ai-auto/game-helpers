"""Capture and child-surface crop helpers for transition sampling."""
from __future__ import annotations

import numpy as np

from ..capture.models import Frame
from ..core.window import get_window_info


def crop_child_from_parent(
    host_frame: Frame,
    parent_geometry,
    child_geometry,
    *,
    canvas_width: int,
    canvas_height: int,
) -> tuple[Frame, tuple[float, float], tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Map the complete child client rectangle into parent-capture pixels.

    The returned crop is clipped only for measurement; the mapped rectangle
    and coverage are recorded so a transition that has not fully rendered the
    target can be distinguished from a stable state.
    """
    _ = (canvas_width, canvas_height)  # retained for call-site compatibility
    sx = host_frame.width / parent_geometry.client_width
    sy = host_frame.height / parent_geometry.client_height
    left_c = child_geometry.screen_left - parent_geometry.screen_left
    top_c = child_geometry.screen_top - parent_geometry.screen_top
    right_c = left_c + child_geometry.client_width
    bottom_c = top_c + child_geometry.client_height
    left = round(left_c * sx)
    top = round(top_c * sy)
    right = round(right_c * sx)
    bottom = round(bottom_c * sy)

    source = np.frombuffer(host_frame.data, dtype=np.uint8).reshape(
        host_frame.height, host_frame.width, 4
    )
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(host_frame.width, right), min(host_frame.height, bottom)
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError("child target rectangle is outside parent capture")
    cropped = np.ascontiguousarray(source[y0:y1, x0:x1, :])
    return (
        Frame(
            get_window_info(child_geometry.hwnd),
            cropped.shape[1],
            cropped.shape[0],
            cropped.tobytes(),
            host_frame.captured_at,
            host_frame.backend,
        ),
        (sx, sy),
        (left, top, right, bottom),
        (max(0, left), max(0, top), min(host_frame.width, right), min(host_frame.height, bottom)),
    )


def capture_role(cap, parent_hwnd, parent_geometry, child_geometry, max_client_size):
    host = cap.capture(parent_hwnd)
    crop, scales, mapped, clipped = crop_child_from_parent(
        host,
        parent_geometry,
        child_geometry,
        canvas_width=max_client_size[0],
        canvas_height=max_client_size[1],
    )
    return host, crop, scales, mapped, clipped
