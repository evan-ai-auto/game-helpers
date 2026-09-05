"""Diagnostic-only sampler for hosted WSGAME surface transitions."""
from __future__ import annotations

import argparse
import csv
import ctypes
import sys
import time
from pathlib import Path

import numpy as np

from ..capture import WindowsGraphicsCapture, save_png
from ..capture.models import Frame
from ..core.surface import query_surface_geometry
from ..core.view_manager import GameViewManager
from ..core.window import find_window, get_window_info
from .accounts import scan_game_accounts


def _fingerprint(frame: Frame, size: int = 48) -> np.ndarray:
    raw = np.frombuffer(frame.data, dtype=np.uint8)
    expected = frame.width * frame.height * 4
    if raw.size < expected:
        raise ValueError(f"invalid frame buffer: bytes={raw.size}, expected>={expected}")
    bgra = raw[:expected].reshape(frame.height, frame.width, 4)
    gray = (
        0.114 * bgra[:, :, 0]
        + 0.587 * bgra[:, :, 1]
        + 0.299 * bgra[:, :, 2]
    ).astype(np.float32)
    ys = np.linspace(0, frame.height - 1, size).astype(np.int32)
    xs = np.linspace(0, frame.width - 1, size).astype(np.int32)
    return gray[np.ix_(ys, xs)]


def _delta(previous: np.ndarray | None, current: np.ndarray) -> float | None:
    return None if previous is None else float(np.mean(np.abs(previous - current)))


def _crop_child_from_parent(
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
        (max(0, left), max(0, top), min(host_frame.width, right), min(host_frame.height, bottom)),
    )


def _capture_role(cap, parent_hwnd, parent_geometry, child_geometry, max_client_size):
    host = cap.capture(parent_hwnd)
    crop, scales, mapped, clipped = _crop_child_from_parent(
        host, parent_geometry, child_geometry,
        canvas_width=max_client_size[0], canvas_height=max_client_size[1],
    )
    return host, crop, scales, mapped, clipped


def _sample_transition(
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
    *, interval: float,
    samples: int,
    threshold: float,
    consecutive: int,
    output_dir: Path,
    round_no: int,
) -> dict[str, object]:
    source_area = source_profile[0] * source_profile[1]
    target_area = target_profile[0] * target_profile[1]
    direction = "同尺寸切换" if source_area == target_area else ("小切大" if source_area < target_area else "大切小")
    path = output_dir / (
        f"round-{round_no:02d}-view{source_index}-{source_profile[0]}x{source_profile[1]}"
        f"-to-view{target_index}-{target_profile[0]}x{target_profile[1]}"
    )
    path.mkdir(parents=True, exist_ok=True)

    switch_started = time.perf_counter()
    manager.switch_surface_to(target_index)
    switch_return_ms = (time.perf_counter() - switch_started) * 1000.0

    rows: list[dict[str, object]] = []
    previous_fp: np.ndarray | None = None
    stable_run = 0
    coverage_run = 0
    first_target_coverage_ms: float | None = None
    first_visual_stable_ms: float | None = None

    for sample_index in range(samples):
        if sample_index:
            time.sleep(interval)
        capture_started = time.perf_counter()
        host, crop, scales, mapped, clipped = _capture_role(
            cap, parent_hwnd, parent_geometry, target_geometry,
            (max(source_profile[0], target_profile[0]), max(source_profile[1], target_profile[1])),
        )
        captured_at = time.perf_counter()
        elapsed_ms = (captured_at - switch_started) * 1000.0
        crop_size = (crop.width, crop.height)
        expected_crop = target_baseline
        coverage_ok = (
            mapped[0] >= 0 and mapped[1] >= 0
            and mapped[2] <= host.width and mapped[3] <= host.height
            and clipped == mapped
        )
        if coverage_ok:
            coverage_run += 1
            if first_target_coverage_ms is None:
                first_target_coverage_ms = elapsed_ms
        else:
            coverage_run = 0

        fp = _fingerprint(crop)
        d = _delta(previous_fp, fp)
        previous_fp = fp
        if coverage_ok and crop_size == expected_crop and d is not None and d <= threshold:
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
            "source_client_width": source_profile[0],
            "source_client_height": source_profile[1],
            "target_client_width": target_profile[0],
            "target_client_height": target_profile[1],
            "parent_capture_width": host.width,
            "parent_capture_height": host.height,
            "target_expected_crop_width": expected_crop[0],
            "target_expected_crop_height": expected_crop[1],
            "target_crop_width": crop_size[0],
            "target_crop_height": crop_size[1],
            "capture_to_parent_client_scale_x": round(scales[0], 6),
            "capture_to_parent_client_scale_y": round(scales[1], 6),
            "mapped_left": mapped[0], "mapped_top": mapped[1],
            "mapped_right": mapped[2], "mapped_bottom": mapped[3],
            "clipped_left": clipped[0], "clipped_top": clipped[1],
            "clipped_right": clipped[2], "clipped_bottom": clipped[3],
            "target_coverage": coverage_ok,
            "target_coverage_consecutive": coverage_run,
            "adjacent_fingerprint_delta": "" if d is None else round(d, 4),
            "visual_stable_consecutive": stable_run,
        })

    samples_csv = path / "samples.csv"
    with samples_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)

    return {
        "direction": direction,
        "source_view": source_index, "target_view": target_index,
        "source_client_size": f"{source_profile[0]}x{source_profile[1]}",
        "target_client_size": f"{target_profile[0]}x{target_profile[1]}",
        "source_baseline_crop": f"{source_baseline[0]}x{source_baseline[1]}",
        "target_baseline_crop": f"{target_baseline[0]}x{target_baseline[1]}",
        "switch_return_ms": round(switch_return_ms, 3),
        "first_target_coverage_ms": None if first_target_coverage_ms is None else round(first_target_coverage_ms, 3),
        "first_visual_stable_ms": None if first_visual_stable_ms is None else round(first_visual_stable_ms, 3),
        "sample_interval_ms": round(interval * 1000.0, 3),
        "sample_count": samples, "settle_threshold": threshold,
        "settle_consecutive": consecutive,
        "output_dir": str(path), "csv": str(samples_csv),
    }


def main() -> int:
    if sys.platform != "win32":
        print("本探针仅支持 Windows。"); return 2
    parser = argparse.ArgumentParser(description="诊断 WSGAME 大/小 Surface 切换渲染稳定时间（仅诊断）")
    parser.add_argument("parent_title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--settle-threshold", type=float, default=2.0)
    parser.add_argument("--settle-consecutive", type=int, default=3)
    parser.add_argument("--output", default="diagnostic/surface_transition_sampling")
    args = parser.parse_args()

    parent = find_window(args.parent_title)
    if parent is None:
        print(f"parent window not found: {args.parent_title!r}"); return 2
    manager = GameViewManager(parent.hwnd, timeout=2.0)
    if len(manager.views()) < 2:
        print("至少需要 2 个 WSGAME surface"); return 1

    scan = scan_game_accounts(parent.hwnd)
    print(f"parent hwnd={parent.hwnd}")
    print("=== 第一次角色/分辨率扫描 ===")
    for account in scan.accounts:
        resolution = account.expected_resolution
        text = f"{resolution[0]}x{resolution[1]}" if resolution else "unknown"
        print(f"view=#{account.view_index} character={account.character_name!r} logged_in={account.logged_in} hwnd={account.hwnd} client={text}")

    pair = None
    for i, a in enumerate(scan.accounts):
        for b in scan.accounts[i + 1:]:
            if a.expected_resolution and b.expected_resolution and a.expected_resolution != b.expected_resolution:
                pair = (a, b); break
        if pair: break
    if pair is None:
        print("未找到两个不同 Client 分辨率的 WSGAME 实例，无法进行大小切换诊断。"); return 1

    first, second = pair
    print(f"sampling_pair=view{first.view_index}({first.expected_resolution[0]}x{first.expected_resolution[1]}) <-> view{second.view_index}({second.expected_resolution[0]}x{second.expected_resolution[1]})")
    print("截图策略：始终以较大 Client 分辨率作为统一观察画布；父窗口 capture 尺寸单独记录。")

    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    original_fg = int(ctypes.windll.user32.GetForegroundWindow())
    cap = WindowsGraphicsCapture()
    parent_geometry = query_surface_geometry(parent.hwnd)
    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []

    try:
        # Calibration is part of the initial role/resolution profile and is not timed as a transition.
        manager.switch_surface_to(first.view_index)
        first_geometry = query_surface_geometry(first.hwnd)
        host, crop, *_ = _capture_role(cap, parent.hwnd, parent_geometry, first_geometry, (1024, 768))
        first_baseline = (crop.width, crop.height)
        print(f"baseline_A client={first.expected_resolution[0]}x{first.expected_resolution[1]} crop={first_baseline[0]}x{first_baseline[1]} parent_capture={host.width}x{host.height}")

        manager.switch_surface_to(second.view_index)
        second_geometry = query_surface_geometry(second.hwnd)
        host, crop, *_ = _capture_role(cap, parent.hwnd, parent_geometry, second_geometry, (1024, 768))
        second_baseline = (crop.width, crop.height)
        print(f"baseline_B client={second.expected_resolution[0]}x{second.expected_resolution[1]} crop={second_baseline[0]}x{second_baseline[1]} parent_capture={host.width}x{host.height}")

        manager.switch_surface_to(first.view_index)
        print("=== 开始双向自动采样 ===")
        for round_no in range(1, args.rounds + 1):
            print(f"\n=== round {round_no}: A -> B ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, parent_geometry, first_geometry, second_geometry,
                first.view_index, second.view_index, first.expected_resolution, second.expected_resolution,
                first_baseline, second_baseline, interval=args.interval, samples=args.samples,
                threshold=args.settle_threshold, consecutive=args.settle_consecutive,
                output_dir=out_dir, round_no=round_no,
            )
            results.append(result); print(result)
            print(f"=== round {round_no}: B -> A ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, parent_geometry, second_geometry, first_geometry,
                second.view_index, first.view_index, second.expected_resolution, first.expected_resolution,
                second_baseline, first_baseline, interval=args.interval, samples=args.samples,
                threshold=args.settle_threshold, consecutive=args.settle_consecutive,
                output_dir=out_dir, round_no=round_no,
            )
            results.append(result); print(result)

        summary = out_dir / "summary.csv"
        with summary.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(results[0])); writer.writeheader(); writer.writerows(results)
        print("\n=== 汇总 ===")
        for item in results:
            print(f"{item['direction']}: client {item['source_client_size']} -> {item['target_client_size']}; baseline_crop {item['source_baseline_crop']} -> {item['target_baseline_crop']}; switch_return={item['switch_return_ms']}ms; target_coverage={item['first_target_coverage_ms']}ms; visual_stable={item['first_visual_stable_ms']}ms")
        print(f"summary={summary}")
        return 0
    finally:
        try:
            manager.switch_surface_to(original_surface); manager.switch_to(original_tab)
        finally:
            final_fg = int(ctypes.windll.user32.GetForegroundWindow())
            print("\n恢复测试上下文：")
            print(f"restored_surface={manager.current_surface_index() == original_surface}")
            print(f"restored_tab={manager.current_index() == original_tab}")
            print(f"foreground_final={final_fg}")
            print(f"foreground_unchanged={final_fg == original_fg}")


if __name__ == "__main__":
    raise SystemExit(main())
