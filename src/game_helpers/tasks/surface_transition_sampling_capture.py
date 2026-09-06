"""Capture and child-surface crop helpers for transition sampling."""
from __future__ import annotations

import numpy as np

from ..capture.models import Frame
from ..core.window import get_window_info

NORMALIZED_WIDTH = 1024
NORMALIZED_HEIGHT = 768


def normalize_frame(frame: Frame, width: int = NORMALIZED_WIDTH, height: int = NORMALIZED_HEIGHT) -> Frame:
    source = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 4)
    y_index = np.linspace(0, frame.height - 1, height).astype(np.int32)
    x_index = np.linspace(0, frame.width - 1, width).astype(np.int32)
    normalized = np.ascontiguousarray(source[y_index][:, x_index])
    return Frame(frame.window, width, height, normalized.tobytes(), frame.captured_at, frame.backend)


def crop_child_from_parent(host_frame: Frame, parent_geometry, child_geometry, *, canvas_width: int, canvas_height: int):
    sx = host_frame.width / parent_geometry.client_width
    sy = host_frame.height / parent_geometry.client_height

    # Use the child client rectangle as the source of truth. The resulting crop
    # is later normalized, so small/large children share one comparison canvas.
    left = round((child_geometry.screen_left - parent_geometry.screen_left) * sx)
    top = round((child_geometry.screen_top - parent_geometry.screen_top) * sy)
    right = round((child_geometry.screen_left - parent_geometry.screen_left + child_geometry.client_width) * sx)
    bottom = round((child_geometry.screen_top - parent_geometry.screen_top + child_geometry.client_height) * sy)

    source = np.frombuffer(host_frame.data, dtype=np.uint8).reshape(host_frame.height, host_frame.width, 4)
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(host_frame.width, right), min(host_frame.height, bottom)
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError("child target rectangle is outside parent capture")

    cropped = np.ascontiguousarray(source[y0:y1, x0:x1, :])
    return (
        Frame(get_window_info(child_geometry.hwnd), cropped.shape[1], cropped.shape[0], cropped.tobytes(), host_frame.captured_at, host_frame.backend),
        (sx, sy),
        (left, top, right, bottom),
        (x0, y0, x1, y1),
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
    return host, normalize_frame(crop), scales, mapped, clipped
