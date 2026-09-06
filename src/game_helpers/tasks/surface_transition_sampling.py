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
from ..core.view_manager import GameViewManager
from .surface_transition_sampling_capture import NORMALIZED_HEIGHT, NORMALIZED_WIDTH, capture_role
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
) -> dict[str, object]:
    source_area = source_profile[0] * source_profile[1]
    target_area = target_profile[0] * target_profile[1]
    direction = "同尺寸切换" if source_area == target_area else ("小切大" if source_area < target_area else "大切小")
    path = output_dir / f"round-{round_no:02d}-view{source_index}-{source_profile[0]}x{source_profile[1]}-to-view{target_index}-{target_profile[0]}x{target_profile[1]}"
    path.mkdir(parents=True, exist_ok=True)

    switch_started = time.perf_counter()
    manager.switch_surface_to(target_index)
    switch_return_ms = (time.perf_counter() - switch_started) * 1000.0

    rows = []
    previous_fp: np.ndarray | None = None
    stable_run = 0
    first_target_coverage_ms = None
    first_visual_stable_ms = None

    for sample_index in range(samples):
        if sample_index:
            time.sleep(interval)
        capture_started = time.perf_counter()
        host, crop, scales, mapped, clipped = capture_role(
            cap,
            parent_hwnd,
            parent_geometry,
            target_geometry,
            (NORMALIZED_WIDTH, NORMALIZED_HEIGHT),
        )
        captured_at = time.perf_counter()
        elapsed_ms = (captured_at - switch_started) * 1000.0
        fp = fingerprint(crop)
        d = delta(previous_fp, fp)
        previous_fp = fp

        coverage_ok = clipped == mapped
        if coverage_ok and first_target_coverage_ms is None:
            first_target_coverage_ms = elapsed_ms

        if d is not None and d <= threshold:
            stable_run += 1
        else:
            stable_run = 0
        if first_visual_stable_ms is None and stable_run >= consecutive:
            first_visual_stable_ms = elapsed_ms - (consecutive - 1) * interval * 1000.0

        save_png(crop, str(path / f"frame-{sample_index:03d}-{elapsed_ms:08.1f}ms.png"))
        rows.append({
            "sample": sample_index,
            "since_switch_ms": round(elapsed_ms, 3),
            "capture_ms": round((captured_at - capture_started) * 1000.0, 3),
            "normalized_width": NORMALIZED_WIDTH,
            "normalized_height": NORMALIZED_HEIGHT,
            "source_client_width": source_profile[0],
            "source_client_height": source_profile[1],
            "target_client_width": target_profile[0],
            "target_client_height": target_profile[1],
            "target_coverage": coverage_ok,
            "adjacent_fingerprint_delta": "" if d is None else round(d, 4),
            "visual_stable_consecutive": stable_run,
        })

    samples_csv = path / "samples.csv"
    with samples_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    return {
        "direction": direction,
        "source_view": source_index,
        "target_view": target_index,
        "source_client_size": f"{source_profile[0]}x{source_profile[1]}",
        "target_client_size": f"{target_profile[0]}x{target_profile[1]}",
        "source_baseline_crop": f"{NORMALIZED_WIDTH}x{NORMALIZED_HEIGHT}",
        "target_baseline_crop": f"{NORMALIZED_WIDTH}x{NORMALIZED_HEIGHT}",
        "switch_return_ms": round(switch_return_ms, 3),
        "first_target_coverage_ms": None if first_target_coverage_ms is None else round(first_target_coverage_ms, 3),
        "first_visual_stable_ms": None if first_visual_stable_ms is None else round(first_visual_stable_ms, 3),
        "normalized_capture": f"{NORMALIZED_WIDTH}x{NORMALIZED_HEIGHT}",
        "sample_interval_ms": round(interval * 1000.0, 3),
        "sample_count": samples,
        "output_dir": str(path),
        "csv": str(samples_csv),
    }


__all__ = ["sample_transition"]
