"""Surface transition sampling orchestration.

Sampling loop and result aggregation live here; the public probe entry remains
``surface_transition_sampling_probe``.
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import numpy as np

from ..capture import WindowsGraphicsCapture, save_png
from ..core.surface import query_surface_geometry
from ..core.view_manager import GameViewManager
from .surface_transition_sampling_capture import capture_role
from .surface_transition_sampling_host import switch_view_background, wait_parent_client_at_least
from .surface_transition_sampling_utils import delta, fingerprint


def sample_transition(
    cap: WindowsGraphicsCapture,
    manager: GameViewManager,
    parent_hwnd: int,
    parent_geometry,
    source_geometry,
    target_geometry,
    source_index: int,
    target_index: int,
    source_profile: tuple[int, int],
    target_profile: tuple[int, int],
    source_baseline: tuple[int, int],
    target_baseline: tuple[int, int],
    *,
    interval: float,
    samples: int,
    threshold: float,
    consecutive: int,
    output_dir: Path,
    round_no: int,
    host_ready_timeout: float = 3.0,
) -> dict[str, object]:
    del source_geometry, parent_geometry  # refreshed after the timed switch
    source_area = source_profile[0] * source_profile[1]
    target_area = target_profile[0] * target_profile[1]
    direction = (
        "同尺寸切换"
        if source_area == target_area
        else ("小切大" if source_area < target_area else "大切小")
    )
    path = output_dir / (
        f"round-{round_no:02d}-view{source_index}-{source_profile[0]}x{source_profile[1]}"
        f"-to-view{target_index}-{target_profile[0]}x{target_profile[1]}"
    )
    path.mkdir(parents=True, exist_ok=True)

    switch_started = time.perf_counter()
    switch_view_background(manager, target_index)
    parent_client = wait_parent_client_at_least(
        parent_hwnd,
        target_profile[0],
        target_profile[1],
        timeout=host_ready_timeout,
    )
    switch_return_ms = (time.perf_counter() - switch_started) * 1000.0

    parent_geometry = query_surface_geometry(parent_hwnd)
    target_geometry = query_surface_geometry(target_geometry.hwnd)

    rows: list[dict[str, object]] = []
    previous_fp: np.ndarray | None = None
    stable_run = 0
    coverage_run = 0
    first_target_coverage_ms: float | None = None
    first_visual_stable_ms: float | None = None

    for sample_index in range(samples):
        if sample_index:
            time.sleep(interval)
        # Geometry can settle for a few frames after host relayout.
        parent_geometry = query_surface_geometry(parent_hwnd)
        target_geometry = query_surface_geometry(target_geometry.hwnd)
        capture_started = time.perf_counter()
        host, crop, scales, mapped, clipped = capture_role(
            cap, parent_hwnd, parent_geometry, target_geometry
        )
        captured_at = time.perf_counter()
        elapsed_ms = (captured_at - switch_started) * 1000.0
        crop_size = (crop.width, crop.height)
        expected_crop = target_baseline
        coverage_ok = clipped == mapped
        if coverage_ok:
            coverage_run += 1
            if first_target_coverage_ms is None:
                first_target_coverage_ms = elapsed_ms
        else:
            coverage_run = 0

        fp = fingerprint(crop)
        d = delta(previous_fp, fp)
        previous_fp = fp
        if coverage_ok and crop_size == expected_crop and d is not None and d <= threshold:
            stable_run += 1
        else:
            stable_run = 0
        if first_visual_stable_ms is None and stable_run >= consecutive:
            first_visual_stable_ms = elapsed_ms - (consecutive - 1) * interval * 1000.0

        save_png(crop, str(path / f"frame-{sample_index:03d}-{elapsed_ms:08.1f}ms.png"))
        rows.append(
            {
                "sample": sample_index,
                "since_switch_ms": round(elapsed_ms, 3),
                "capture_ms": round((captured_at - capture_started) * 1000.0, 3),
                "source_client_width": source_profile[0],
                "source_client_height": source_profile[1],
                "target_client_width": target_profile[0],
                "target_client_height": target_profile[1],
                "parent_client_width": parent_geometry.client_width,
                "parent_client_height": parent_geometry.client_height,
                "parent_capture_width": host.width,
                "parent_capture_height": host.height,
                "target_expected_crop_width": expected_crop[0],
                "target_expected_crop_height": expected_crop[1],
                "target_crop_width": crop_size[0],
                "target_crop_height": crop_size[1],
                "capture_to_parent_client_scale_x": round(scales[0], 6),
                "capture_to_parent_client_scale_y": round(scales[1], 6),
                "mapped_left": mapped[0],
                "mapped_top": mapped[1],
                "mapped_right": mapped[2],
                "mapped_bottom": mapped[3],
                "clipped_left": clipped[0],
                "clipped_top": clipped[1],
                "clipped_right": clipped[2],
                "clipped_bottom": clipped[3],
                "target_coverage": coverage_ok,
                "target_coverage_consecutive": coverage_run,
                "adjacent_fingerprint_delta": "" if d is None else round(d, 4),
                "visual_stable_consecutive": stable_run,
            }
        )

    samples_csv = path / "samples.csv"
    with samples_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    complete = first_target_coverage_ms is not None
    failure_reason = None
    if not complete:
        failure_reason = (
            "target child client was never fully covered by parent capture "
            f"(parent_client={parent_client[0]}x{parent_client[1]}, "
            f"parent_capture last={rows[-1]['parent_capture_width']}x{rows[-1]['parent_capture_height']}, "
            f"target_client={target_profile[0]}x{target_profile[1]}, "
            f"crop={rows[-1]['target_crop_width']}x{rows[-1]['target_crop_height']}). "
            "后台 Tab 对齐切换后宿主仍未完整覆盖目标子窗口。"
        )

    return {
        "direction": direction,
        "source_view": source_index,
        "target_view": target_index,
        "source_client_size": f"{source_profile[0]}x{source_profile[1]}",
        "target_client_size": f"{target_profile[0]}x{target_profile[1]}",
        "source_baseline_crop": f"{source_baseline[0]}x{source_baseline[1]}",
        "target_baseline_crop": f"{target_baseline[0]}x{target_baseline[1]}",
        "parent_client_after_switch": f"{parent_client[0]}x{parent_client[1]}",
        "switch_return_ms": round(switch_return_ms, 3),
        "first_target_coverage_ms": (
            None if first_target_coverage_ms is None else round(first_target_coverage_ms, 3)
        ),
        "first_visual_stable_ms": (
            None if first_visual_stable_ms is None else round(first_visual_stable_ms, 3)
        ),
        "sample_interval_ms": round(interval * 1000.0, 3),
        "sample_count": samples,
        "settle_threshold": threshold,
        "settle_consecutive": consecutive,
        "complete": complete,
        "failure_reason": failure_reason,
        "output_dir": str(path),
        "csv": str(samples_csv),
    }


__all__ = ["sample_transition"]
