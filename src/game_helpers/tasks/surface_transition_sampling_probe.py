"""Diagnostic-only sampler for hosted WSGAME surface transitions.

The probe is intentionally isolated from production switching logic. It scans
characters once, records their current client geometry, automatically resolves
the actual capture size of each surface, then measures both directions between
one small and one large observed surface. No manual child-window switching is
required.
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


def _capture(cap: WindowsGraphicsCapture, parent_hwnd: int):
    started = time.perf_counter()
    frame = cap.capture(parent_hwnd)
    return frame, (time.perf_counter() - started) * 1000.0


def _observe_baseline(
    cap: WindowsGraphicsCapture,
    parent_hwnd: int,
    *,
    interval: float,
    samples: int,
    threshold: float,
    consecutive: int,
) -> tuple[int, int]:
    """Capture an already-selected surface and return its observed stable size."""
    last_size: tuple[int, int] | None = None
    size_run = 0
    previous: np.ndarray | None = None
    stable_run = 0
    stable_size: tuple[int, int] | None = None

    for index in range(samples):
        if index:
            time.sleep(interval)
        frame, _ = _capture(cap, parent_hwnd)
        current_size = _size(frame)
        if current_size == last_size:
            size_run += 1
        else:
            last_size = current_size
            size_run = 1
            stable_run = 0
        current_fp = _fingerprint(frame)
        d = _delta(previous, current_fp)
        previous = current_fp
        if d is not None and d <= threshold:
            stable_run += 1
        else:
            stable_run = 0
        if size_run >= consecutive and stable_run >= consecutive:
            stable_size = current_size
    if stable_size is None:
        if last_size is None:
            raise RuntimeError("no baseline capture")
        stable_size = last_size
    return stable_size


def _sample_transition(
    cap: WindowsGraphicsCapture,
    manager: GameViewManager,
    parent_hwnd: int,
    source_index: int,
    target_index: int,
    source_capture_size: tuple[int, int],
    target_capture_size: tuple[int, int],
    *,
    interval: float,
    samples: int,
    threshold: float,
    consecutive: int,
    output_dir: Path,
    round_no: int,
) -> dict[str, object]:
    source_area = source_capture_size[0] * source_capture_size[1]
    target_area = target_capture_size[0] * target_capture_size[1]
    if source_area == target_area:
        direction = "同尺寸切换"
    elif source_area < target_area:
        direction = "小切大"
    else:
        direction = "大切小"

    transition_dir = (
        f"round-{round_no:02d}-view{source_index}-{source_capture_size[0]}x{source_capture_size[1]}"
        f"-to-view{target_index}-{target_capture_size[0]}x{target_capture_size[1]}"
    )
    path = output_dir / transition_dir
    path.mkdir(parents=True, exist_ok=True)

    # Source is already the selected surface. Reconfirm a stable baseline
    # immediately before starting the timed transition.
    baseline_size = _observe_baseline(
        cap, parent_hwnd, interval=interval, samples=max(consecutive + 1, 4),
        threshold=threshold, consecutive=consecutive,
    )

    switch_started = time.perf_counter()
    manager.switch_surface_to(target_index)
    switch_return_ms = (time.perf_counter() - switch_started) * 1000.0

    rows: list[dict[str, object]] = []
    previous_fp: np.ndarray | None = None
    target_size_run = 0
    visual_stable_run = 0
    first_target_size_ms: float | None = None
    first_visual_stable_ms: float | None = None

    for sample_index in range(samples):
        if sample_index:
            time.sleep(interval)
        capture_started = time.perf_counter()
        frame = cap.capture(parent_hwnd)
        captured_at = time.perf_counter()
        elapsed_ms = (captured_at - switch_started) * 1000.0
        capture_ms = (captured_at - capture_started) * 1000.0
        frame_size = _size(frame)
        is_target_size = frame_size == target_capture_size
        if is_target_size:
            target_size_run += 1
            if first_target_size_ms is None:
                first_target_size_ms = elapsed_ms
        else:
            target_size_run = 0

        current_fp = _fingerprint(frame)
        d = _delta(previous_fp, current_fp)
        previous_fp = current_fp
        if is_target_size and d is not None and d <= threshold:
            visual_stable_run += 1
        else:
            visual_stable_run = 0
        if first_visual_stable_ms is None and visual_stable_run >= consecutive:
            first_visual_stable_ms = elapsed_ms - (consecutive - 1) * interval * 1000.0

        save_png(frame, str(path / f"frame-{sample_index:03d}-{elapsed_ms:08.1f}ms.png"))
        rows.append({
            "sample": sample_index,
            "since_switch_ms": round(elapsed_ms, 3),
            "capture_ms": round(capture_ms, 3),
            "frame_width": frame_size[0],
            "frame_height": frame_size[1],
            "target_geometry": is_target_size,
            "target_size_consecutive": target_size_run,
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
        "source_capture_size": f"{source_capture_size[0]}x{source_capture_size[1]}",
        "target_capture_size": f"{target_capture_size[0]}x{target_capture_size[1]}",
        "baseline_capture_size": f"{baseline_size[0]}x{baseline_size[1]}",
        "switch_return_ms": round(switch_return_ms, 3),
        "first_target_capture_size_ms": None if first_target_size_ms is None else round(first_target_size_ms, 3),
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

    parser = argparse.ArgumentParser(description="自动测量 WSGAME 大/小 Surface 切换耗时（诊断专用）")
    parser.add_argument("parent_title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--interval", type=float, default=0.05, help="截图间隔秒数，默认 0.05s")
    parser.add_argument("--samples", type=int, default=40, help="每次切换后的截图数量，默认 40")
    parser.add_argument("--rounds", type=int, default=3, help="每个方向重复次数，默认 3")
    parser.add_argument("--settle-threshold", type=float, default=2.0, help="48x48 灰度指纹相邻帧平均差阈值")
    parser.add_argument("--settle-consecutive", type=int, default=3, help="连续稳定帧数")
    parser.add_argument("--output", default="diagnostic/surface_transition_sampling", help="输出目录")
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
        resolution_text = f"{resolution[0]}x{resolution[1]}" if resolution else "unknown"
        print(
            f"view=#{account.view_index} character={account.character_name!r} "
            f"logged_in={account.logged_in} hwnd={account.hwnd} client={resolution_text}"
        )

    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    original_fg = int(ctypes.windll.user32.GetForegroundWindow())
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"sample_interval_ms={args.interval * 1000:.1f}")
    print(f"samples_per_transition={args.samples}")
    print(f"rounds_per_direction={args.rounds}")
    print("后续切换、截图、检测、计时全部自动执行，不需要手动切子窗口。")

    cap = WindowsGraphicsCapture()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[dict[str, object]] = []

    # Prefer a pair whose initial client geometries differ. The capture sizes
    # are then measured independently; this avoids assuming client==capture.
    pairs = [
        (i, j)
        for i, a in enumerate(scan.accounts, 1)
        for j, b in enumerate(scan.accounts, 1)
        if i < j and a.expected_resolution != b.expected_resolution
    ]
    first_view, second_view = pairs[0] if pairs else (1, 2)
    print(f"sampling_pair=view{first_view} <-> view{second_view}")

    try:
        # Resolve the actual capture geometry for both roles before timing.
        manager.switch_surface_to(first_view)
        first_capture_size = _observe_baseline(
            cap, parent.hwnd, interval=args.interval, samples=6,
            threshold=args.settle_threshold, consecutive=args.settle_consecutive,
        )
        manager.switch_surface_to(second_view)
        second_capture_size = _observe_baseline(
            cap, parent.hwnd, interval=args.interval, samples=6,
            threshold=args.settle_threshold, consecutive=args.settle_consecutive,
        )
        print(f"view{first_view}_capture_size={first_capture_size[0]}x{first_capture_size[1]}")
        print(f"view{second_view}_capture_size={second_capture_size[0]}x{second_capture_size[1]}")

        # Measure both directions. Each transition starts only after its source
        # surface has been selected and baseline-confirmed.
        for round_no in range(1, args.rounds + 1):
            manager.switch_surface_to(first_view)
            print(f"\n=== round {round_no}: view{first_view} -> view{second_view} ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, first_view, second_view,
                first_capture_size, second_capture_size,
                interval=args.interval, samples=args.samples,
                threshold=args.settle_threshold,
                consecutive=args.settle_consecutive,
                output_dir=output_dir, round_no=round_no,
            )
            all_results.append(result)
            print(result)

            manager.switch_surface_to(second_view)
            print(f"=== round {round_no}: view{second_view} -> view{first_view} ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, second_view, first_view,
                second_capture_size, first_capture_size,
                interval=args.interval, samples=args.samples,
                threshold=args.settle_threshold,
                consecutive=args.settle_consecutive,
                output_dir=output_dir, round_no=round_no,
            )
            all_results.append(result)
            print(result)

        summary = output_dir / "summary.csv"
        with summary.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(all_results[0]))
            writer.writeheader()
            writer.writerows(all_results)

        print("\n=== 汇总 ===")
        for item in all_results:
            print(
                f"{item['direction']}: "
                f"view{item['source_view']} {item['source_capture_size']} -> "
                f"view{item['target_view']} {item['target_capture_size']}; "
                f"switch_return={item['switch_return_ms']}ms; "
                f"target_size={item['first_target_capture_size_ms']}ms; "
                f"visual_stable={item['first_visual_stable_ms']}ms"
            )
        print(f"summary={summary}")
        return 0
    finally:
        try:
            manager.switch_surface_to(original_surface)
            manager.switch_to(original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
        final_fg = int(ctypes.windll.user32.GetForegroundWindow())
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_final={final_fg}")
        print(f"foreground_unchanged={final_fg == original_fg}")


if __name__ == "__main__":
    raise SystemExit(main())
