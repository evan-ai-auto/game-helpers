"""Diagnostic-only sampler for hosted WSGAME surface transitions.

This probe intentionally does not modify production switching/capture logic.
It scans the WSGAME child windows once, binds their client geometry to the
observed role, then automatically switches between two selected surfaces.
The parent WGC frame is cropped into each selected child's coordinate space;
the parent capture size is never used as the child's resolution.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import sys
import time
from pathlib import Path

import numpy as np

from ..capture import WindowsGraphicsCapture, save_png
from ..core.surface import query_surface_geometry
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts


def _size(frame) -> tuple[int, int]:
    return int(frame.width), int(frame.height)


def _fingerprint(frame, size: int = 48) -> np.ndarray:
    width, height = _size(frame)
    raw = np.frombuffer(frame.data, dtype=np.uint8)
    expected = width * height * 4
    if raw.size < expected:
        raise ValueError(f"invalid frame buffer: bytes={raw.size}, expected>={expected}")
    bgra = raw[:expected].reshape(height, width, 4)
    gray = (
        0.114 * bgra[:, :, 0]
        + 0.587 * bgra[:, :, 1]
        + 0.299 * bgra[:, :, 2]
    ).astype(np.float32)
    ys = np.linspace(0, height - 1, size).astype(np.int32)
    xs = np.linspace(0, width - 1, size).astype(np.int32)
    return gray[np.ix_(ys, xs)]


def _delta(previous: np.ndarray | None, current: np.ndarray) -> float | None:
    if previous is None:
        return None
    return float(np.mean(np.abs(previous - current)))


def _crop_child_from_parent(frame, parent_geometry, child_geometry):
    """Crop a child client rect from a parent WGC frame.

    The parent WGC frame and the parent client area can have different pixel
    sizes. We therefore transform parent-client coordinates into capture-pixel
    coordinates before cropping. This is diagnostic-only and makes the three
    geometries explicit in the output: child client, parent capture, child
    crop.
    """
    parent_client_w = int(parent_geometry.client_width)
    parent_client_h = int(parent_geometry.client_height)
    if parent_client_w <= 0 or parent_client_h <= 0:
        raise RuntimeError("invalid parent client geometry")

    scale_x = frame.width / parent_client_w
    scale_y = frame.height / parent_client_h

    left_client = int(child_geometry.screen_left - parent_geometry.screen_left)
    top_client = int(child_geometry.screen_top - parent_geometry.screen_top)
    right_client = left_client + int(child_geometry.client_width)
    bottom_client = top_client + int(child_geometry.client_height)

    left = round(left_client * scale_x)
    top = round(top_client * scale_y)
    right = round(right_client * scale_x)
    bottom = round(bottom_client * scale_y)

    source = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 4)
    x0 = max(0, left)
    y0 = max(0, top)
    x1 = min(frame.width, right)
    y1 = min(frame.height, bottom)
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError(
            "selected child crop is outside parent capture: "
            f"child_client=({left_client},{top_client},{right_client},{bottom_client}) "
            f"mapped_capture=({left},{top},{right},{bottom}) "
            f"parent_capture={frame.width}x{frame.height}"
        )

    cropped = np.ascontiguousarray(source[y0:y1, x0:x1, :])
    from ..capture.models import Frame
    from ..core.window import get_window_info

    return Frame(
        window=get_window_info(child_geometry.hwnd),
        width=int(cropped.shape[1]),
        height=int(cropped.shape[0]),
        data=cropped.tobytes(),
        captured_at=frame.captured_at,
        backend=frame.backend,
    ), (scale_x, scale_y), (left, top, right, bottom)


def _observe_stable(
    cap: WindowsGraphicsCapture,
    parent_hwnd: int,
    parent_geometry,
    child_geometry,
    *,
    interval: float,
    samples: int,
    threshold: float,
    consecutive: int,
) -> tuple[tuple[int, int], int | None]:
    previous: np.ndarray | None = None
    last_crop_size: tuple[int, int] | None = None
    stable_run = 0
    stable_size: tuple[int, int] | None = None
    stable_at: int | None = None

    for index in range(samples):
        if index:
            time.sleep(interval)
        host = cap.capture(parent_hwnd)
        crop, _, _ = _crop_child_from_parent(host, parent_geometry, child_geometry)
        crop_size = _size(crop)
        if crop_size == last_crop_size:
            stable_run += 1
        else:
            last_crop_size = crop_size
            stable_run = 1
        fp = _fingerprint(crop)
        d = _delta(previous, fp)
        previous = fp
        if d is not None and d <= threshold:
            if stable_run >= consecutive:
                stable_size = crop_size
                stable_at = index
        else:
            stable_run = 0

    if stable_size is None:
        if last_crop_size is None:
            raise RuntimeError("no stable baseline crop captured")
        stable_size = last_crop_size
    return stable_size, stable_at


def _sample_transition(
    cap: WindowsGraphicsCapture,
    manager: GameViewManager,
    parent_hwnd: int,
    parent_geometry,
    source_geometry,
    target_geometry,
    source_index: int,
    target_index: int,
    source_crop_size: tuple[int, int],
    target_crop_size: tuple[int, int],
    *,
    interval: float,
    samples: int,
    threshold: float,
    consecutive: int,
    output_dir: Path,
    round_no: int,
) -> dict[str, object]:
    source_client = (source_geometry.client_width, source_geometry.client_height)
    target_client = (target_geometry.client_width, target_geometry.client_height)
    source_area = source_client[0] * source_client[1]
    target_area = target_client[0] * target_client[1]
    direction = "同尺寸切换" if source_area == target_area else ("小切大" if source_area < target_area else "大切小")

    path = output_dir / (
        f"round-{round_no:02d}-view{source_index}-{source_client[0]}x{source_client[1]}"
        f"-to-view{target_index}-{target_client[0]}x{target_client[1]}"
    )
    path.mkdir(parents=True, exist_ok=True)

    baseline_size, baseline_stable_sample = _observe_stable(
        cap, parent_hwnd, parent_geometry, source_geometry,
        interval=interval, samples=max(consecutive + 1, 4),
        threshold=threshold, consecutive=consecutive,
    )

    switch_started = time.perf_counter()
    manager.switch_surface_to(target_index)
    switch_return_ms = (time.perf_counter() - switch_started) * 1000.0

    rows: list[dict[str, object]] = []
    previous_fp: np.ndarray | None = None
    target_geometry_run = 0
    visual_stable_run = 0
    first_target_crop_ms: float | None = None
    first_visual_stable_ms: float | None = None

    for sample_index in range(samples):
        if sample_index:
            time.sleep(interval)
        capture_started = time.perf_counter()
        host = cap.capture(parent_hwnd)
        captured_at = time.perf_counter()
        elapsed_ms = (captured_at - switch_started) * 1000.0
        capture_ms = (captured_at - capture_started) * 1000.0
        crop, scales, mapped_rect = _crop_child_from_parent(host, parent_geometry, target_geometry)
        crop_size = _size(crop)
        is_target_crop = crop_size == target_crop_size
        if is_target_crop:
            target_geometry_run += 1
            if first_target_crop_ms is None:
                first_target_crop_ms = elapsed_ms
        else:
            target_geometry_run = 0

        fp = _fingerprint(crop)
        d = _delta(previous_fp, fp)
        previous_fp = fp
        if is_target_crop and d is not None and d <= threshold:
            visual_stable_run += 1
        else:
            visual_stable_run = 0
        if first_visual_stable_ms is None and visual_stable_run >= consecutive:
            first_visual_stable_ms = elapsed_ms - (consecutive - 1) * interval * 1000.0

        save_png(crop, str(path / f"frame-{sample_index:03d}-{elapsed_ms:08.1f}ms.png"))
        rows.append({
            "sample": sample_index,
            "since_switch_ms": round(elapsed_ms, 3),
            "capture_ms": round(capture_ms, 3),
            "child_client_width": target_client[0],
            "child_client_height": target_client[1],
            "parent_capture_width": host.width,
            "parent_capture_height": host.height,
            "child_crop_width": crop_size[0],
            "child_crop_height": crop_size[1],
            "crop_scale_x": round(scales[0], 6),
            "crop_scale_y": round(scales[1], 6),
            "mapped_left": mapped_rect[0],
            "mapped_top": mapped_rect[1],
            "mapped_right": mapped_rect[2],
            "mapped_bottom": mapped_rect[3],
            "target_crop_geometry": is_target_crop,
            "target_crop_consecutive": target_geometry_run,
            "adjacent_fingerprint_delta": "" if d is None else round(d, 4),
            "visual_stable_consecutive": visual_stable_run,
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
        "source_client_size": f"{source_client[0]}x{source_client[1]}",
        "target_client_size": f"{target_client[0]}x{target_client[1]}",
        "source_crop_size": f"{source_crop_size[0]}x{source_crop_size[1]}",
        "target_crop_size": f"{target_crop_size[0]}x{target_crop_size[1]}",
        "baseline_crop_size": f"{baseline_size[0]}x{baseline_size[1]}",
        "baseline_stable_sample": baseline_stable_sample,
        "switch_return_ms": round(switch_return_ms, 3),
        "first_target_crop_ms": None if first_target_crop_ms is None else round(first_target_crop_ms, 3),
        "first_visual_stable_ms": None if first_visual_stable_ms is None else round(first_visual_stable_ms, 3),
        "sample_interval_ms": round(interval * 1000.0, 3),
        "sample_count": samples,
        "settle_threshold": threshold,
        "settle_consecutive": consecutive,
        "output_dir": str(path),
        "csv": str(samples_csv),
    }


def main() -> int:
    if sys.platform != "win32":
        print("本探针仅支持 Windows。")
        return 2

    parser = argparse.ArgumentParser(description="诊断 WSGAME 大/小 Surface 切换渲染稳定时间（仅诊断，不改生产逻辑）")
    parser.add_argument("parent_title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--settle-threshold", type=float, default=2.0)
    parser.add_argument("--settle-consecutive", type=int, default=3)
    parser.add_argument("--output", default="diagnostic/surface_transition_sampling")
    args = parser.parse_args()

    if args.interval <= 0 or args.samples < 2 or args.rounds < 1 or args.settle_consecutive < 2:
        print("参数无效")
        return 2

    parent = find_window(args.parent_title)
    if parent is None:
        print(f"parent window not found: {args.parent_title!r}")
        return 2

    manager = GameViewManager(parent.hwnd, timeout=2.0)
    views = manager.views()
    if len(views) < 2:
        print(f"至少需要 2 个 WSGAME surface，当前={len(views)}")
        return 1

    scan = scan_game_accounts(parent.hwnd)
    print(f"parent hwnd={parent.hwnd}")
    print("=== 第一次角色/分辨率扫描 ===")
    for account in scan.accounts:
        resolution = account.expected_resolution
        text = f"{resolution[0]}x{resolution[1]}" if resolution else "unknown"
        print(
            f"view=#{account.view_index} character={account.character_name!r} "
            f"logged_in={account.logged_in} hwnd={account.hwnd} client={text}"
        )

    # Pick two roles with different CLIENT resolutions. Client geometry, not
    # parent capture geometry, defines 大切小/小切大.
    pair = None
    for i, a in enumerate(scan.accounts):
        for j, b in enumerate(scan.accounts):
            if i < j and a.expected_resolution and b.expected_resolution and a.expected_resolution != b.expected_resolution:
                pair = (a, b)
                break
        if pair:
            break
    if pair is None:
        print("未找到两个不同 Client 分辨率的 WSGAME 实例，无法进行大小切换诊断。")
        return 1

    first, second = pair
    print(
        f"sampling_pair=view{first.view_index}({first.expected_resolution[0]}x{first.expected_resolution[1]}) "
        f"<-> view{second.view_index}({second.expected_resolution[0]}x{second.expected_resolution[1]})"
    )
    print("注意：parent_capture_size 与 child_client_size/crop_size 分开记录，不再混用。")

    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    original_fg = int(ctypes.windll.user32.GetForegroundWindow())
    cap = WindowsGraphicsCapture()
    parent_geometry = query_surface_geometry(parent.hwnd)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[dict[str, object]] = []

    try:
        # Establish one clean baseline crop for each selected role. These are
        # calibration captures and are not included in transition timings.
        manager.switch_surface_to(first.view_index)
        first_geom = query_surface_geometry(first.hwnd)
        first_host = cap.capture(parent.hwnd)
        first_crop, _, _ = _crop_child_from_parent(first_host, parent_geometry, first_geom)
        first_crop_size = _size(first_crop)
        print(f"baseline_A client={first.expected_resolution[0]}x{first.expected_resolution[1]} crop={first_crop_size[0]}x{first_crop_size[1]} parent_capture={first_host.width}x{first_host.height}")

        manager.switch_surface_to(second.view_index)
        second_geom = query_surface_geometry(second.hwnd)
        second_host = cap.capture(parent.hwnd)
        second_crop, _, _ = _crop_child_from_parent(second_host, parent_geometry, second_geom)
        second_crop_size = _size(second_crop)
        print(f"baseline_B client={second.expected_resolution[0]}x{second.expected_resolution[1]} crop={second_crop_size[0]}x{second_crop_size[1]} parent_capture={second_host.width}x{second_host.height}")

        manager.switch_surface_to(first.view_index)
        print("=== 开始双向自动采样 ===")
        for round_no in range(1, args.rounds + 1):
            print(f"\n=== round {round_no}: A -> B ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, parent_geometry, first_geom, second_geom,
                first.view_index, second.view_index, first_crop_size, second_crop_size,
                interval=args.interval, samples=args.samples,
                threshold=args.settle_threshold, consecutive=args.settle_consecutive,
                output_dir=out_dir, round_no=round_no,
            )
            all_results.append(result)
            print(result)

            print(f"=== round {round_no}: B -> A ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, parent_geometry, second_geom, first_geom,
                second.view_index, first.view_index, second_crop_size, first_crop_size,
                interval=args.interval, samples=args.samples,
                threshold=args.settle_threshold, consecutive=args.settle_consecutive,
                output_dir=out_dir, round_no=round_no,
            )
            all_results.append(result)
            print(result)

        summary = out_dir / "summary.csv"
        with summary.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(all_results[0]))
            writer.writeheader()
            writer.writerows(all_results)
        print("\n=== 汇总 ===")
        for item in all_results:
            print(
                f"{item['direction']}: "
                f"client {item['source_client_size']} -> {item['target_client_size']}; "
                f"crop {item['source_crop_size']} -> {item['target_crop_size']}; "
                f"switch_return={item['switch_return_ms']}ms; "
                f"target_crop={item['first_target_crop_ms']}ms; "
                f"visual_stable={item['first_visual_stable_ms']}ms"
            )
        print(f"summary={summary}")
        return 0
    finally:
        try:
            manager.switch_surface_to(original_surface)
            manager.switch_to(original_tab)
        finally:
            final_fg = int(ctypes.windll.user32.GetForegroundWindow())
            print("\n恢复测试上下文：")
            print(f"restored_surface={manager.current_surface_index() == original_surface}")
            print(f"restored_tab={manager.current_index() == original_tab}")
            print(f"foreground_final={final_fg}")
            print(f"foreground_unchanged={final_fg == original_fg}")


if __name__ == "__main__":
    raise SystemExit(main())
