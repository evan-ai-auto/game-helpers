"""Capture, crop and transition sampling helpers.

Migrated from surface_transition_sampling_probe while keeping the probe entry
compatible.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..capture import save_png
from ..capture.models import Frame
from .surface_transition_sampling_utils import fingerprint, delta


def crop_child_from_parent(host_frame, parent_geometry, child_geometry):
    sx = host_frame.width / parent_geometry.client_width
    sy = host_frame.height / parent_geometry.client_height
    left = round((child_geometry.screen_left - parent_geometry.screen_left) * sx)
    top = round((child_geometry.screen_top - parent_geometry.screen_top) * sy)
    right = round((left + child_geometry.client_width) * 1)
    bottom = round((top + child_geometry.client_height) * 1)
    return left, top, right, bottom


def capture_role(cap, parent_hwnd, parent_geometry, child_geometry):
    host = cap.capture(parent_hwnd)
    left, top, right, bottom = crop_child_from_parent(host, parent_geometry, child_geometry)
    import numpy as np
    source = np.frombuffer(host.data, dtype=np.uint8).reshape(host.height, host.width, 4)
    cropped = np.ascontiguousarray(source[top:bottom, left:right, :])
    crop = Frame(host.window, cropped.shape[1], cropped.shape[0], cropped.tobytes(), host.captured_at, host.backend)
    return host, crop


def sample_transition(cap, manager, parent_hwnd, target_index, output_dir: Path, samples=40, interval=0.05):
    manager.switch_surface_to(target_index)
    rows = []
    previous = None
    for index in range(samples):
        if index:
            time.sleep(interval)
        frame = cap.capture(parent_hwnd)
        current = fingerprint(frame)
        rows.append({"sample": index, "delta": delta(previous, current)})
        previous = current
        save_png(frame, str(output_dir / f"frame-{index:03d}.png"))
    return rows
