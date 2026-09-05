"""Diagnostic-only sampler for measuring hosted WSGAME surface transitions.

This probe intentionally does not modify GameViewManager, VerificationSession,
or any production workflow. It repeatedly captures the host window after a
background surface switch and records timing, geometry, and frame-to-frame
visual convergence so we can estimate 806x606 <-> 1024x768 transition latency.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from ..core.window import find_window


def _frame_signature(frame) -> tuple[int, int]:
    return int(frame.width), int(frame.height)


def _small_gray(frame, size: int = 48) -> np.ndarray:
    """Return a tiny grayscale fingerprint; diagnostic only, not workflow logic."""
    width, height = int(frame.width), int(frame.height)
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

    # Nearest-neighbour downsample keeps this probe dependency-free.
    ys = np.linspace(0, height - 1, size).astype(np.int32)
    xs = np.linspace(0, width - 1, size).astype(np.int32)
    return gray[np.ix_(ys, xs)]


def _fingerprint_delta(a: np.ndarray | None, b: np.ndarray) -> float | None:
    if a is None or a.shape != b.shape:
        return None
    return float(np.mean(np.abs(a - b)))


def _stable_run(values: list[float | None], threshold: float, consecutive: int) -> int | None:
    run = 0
    for index, value in enumerate(values):
        if value is not None and value <= threshold:
            run += 1
            if run >= consecutive:
                return index - consecutive + 1
        else:
            run = 0
    return None


def _capture(cap: WindowsGraphicsCapture, parent_hwnd: int):
    started = time.perf_counter()
    frame = cap.capture(parent_hwnd)
    elapsed = time.perf_counter() - started
    return frame, elapsed


def _sample_transition(
    cap: WindowsGraphicsCapture,
    manager: GameViewManager,
    parent_hwnd: int,
    source_index: int,
    target_index: int,
    *,
    interval: float,
    samples: int,
    settle_threshold: float,
    settle_consecutive: int,
    out_dir: Path,
    round_no: int,
) -> dict[str, object]:
    source = manager.views()[source_index - 1]
    target = manager.views()[target_index - 1]
    source_size = (source.window.width, source.window.height)
    target_size = (target.window.width, target.window.height)

    # Establish the pre-switch state without touching foreground activation.
    pre_frames = []
    for _ in range(3):
        frame, _ = _capture(cap, parent_hwnd)
        pre_frames.append(frame)
        time.sleep(interval)

    transition_dir = f"view{source_index}_{source_size[0]}x{source_size[1]}__to__view{target_index}_{target_size[0]}x{target_size[1]}"
    transition_dir_path = out_dir / f"round-{round_no:02d}-{transition_dir}"
    transition_dir_path.mkdir(parents=True, exist_ok=True)

    switch_started = time.perf_counter()
    manager.switch_surface_to(target_index)
    switch_return_ms = (time.perf_counter() - switch_started) * 1000.0

    rows: list[dict[str, object]] = []
    fingerprints: list[np.ndarray] = []
    previous_fp: np.ndarray | None = None
    first_target_geometry_ms: float | None = None
    stable_values: list[float | None] = []
    first_capture_ms: float | None = None

    for sample_index in range(samples):
        if sample_index:
            time.sleep(interval)
        capture_started = time.perf_counter()
        frame = cap.capture(parent_hwnd)
        capture_finished = time.perf_counter()
        since_switch_ms = (capture_finished - switch_started) * 1000.0
        capture_ms = (capture_finished - capture_started) * 1000.0
        if first_capture_ms is None:
            first_capture_ms = since_switch_ms

        fp = _small_gray(frame)
        delta = _fingerprint_delta(previous_fp, fp)
        previous_fp = fp
        fingerprints.append(fp)
        stable_values.append(delta)

        geometry = _frame_signature(frame)
        is_target_geometry = geometry == _frame_signature(pre_frames[-1]) or geometry == target_size
        # The two common stable states are explicitly recorded; no state is
        # rejected by this diagnostic probe.
        if geometry == target_size and first_target_geometry_ms is None:
            first_target_geometry_ms = since_switch_ms

        save_png(frame, str(transition_dir_path / f"frame-{sample_index:03d}-{since_switch_ms:08.1f}ms.png"))
        rows.append(
            {
                "sample": sample_index,
                "since_switch_ms": round(since_switch_ms, 3),
                "capture_ms": round(capture_ms, 3),
                "frame_width": geometry[0],
                "frame_height": geometry[1],
                "target_client_width": target_size[0],
                "target_client_height": target_size[1],
                "target_geometry": is_target_geometry,
                "adjacent_fingerprint_delta": "" if delta is None else round(delta, 4),
            }
        )

    stable_index = _stable_run(stable_values, settle_threshold, settle_consecutive)
    first_visual_stable_ms = None
    if stable_index is not None and stable_index < len(rows):
        first_visual_stable_ms = float(rows[stable_index]["since_switch_ms"])

    csv_path = transition_dir_path / "samples.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    return {
        "direction": transition_dir,
        "source_view": source_index,
        "target_view": target_index,
        "source_client_size": f"{source_size[0]}x{source_size[1]}",
        "target_client_size": f"{target_size[0]}x{target_size[1]}",
        "switch_return_ms": round(switch_return_ms, 3),
        "first_capture_ms": None if first_capture_ms is None else round(first_capture_ms, 3),
        "first_target_geometry_ms": None if first_target_geometry_ms is None else round(first_target_geometry_ms, 3),
        "first_visual_stable_ms": None if first_visual_stable_ms is None else round(first_visual_stable_ms, 3),
        "settle_threshold": settle_threshold,
        "settle_consecutive": settle_consecutive,
        "sample_interval_ms": round(interval * 1000.0, 3),
        "sample_count": samples,
        "output_dir": str(transition_dir_path),
        "csv": str(csv_path),
    }


def main() -> int:
    if sys.platform != "win32":
        print("本探针仅支持 Windows。")
        return 2

    parser = argparse.ArgumentParser(description="采样 WSGAME 大/小 Surface 切换渲染耗时（诊断专用）")
    parser.add_argument("parent_title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--interval", type=float, default=0.05, help="截图间隔秒数，默认 0.05s")
    parser.add_argument("--samples", type=int, default=40, help="每次切换后的截图数量，默认 40")
    parser.add_argument("--rounds", type=int, default=3, help="每个方向重复次数，默认 3")
    parser.add_argument("--settle-threshold", type=float, default=2.0, help="相邻 48x48 灰度指纹平均差阈值，仅用于诊断")
    parser.add_argument("--settle-consecutive", type=int, default=3, help="连续满足阈值的帧数，默认 3")
    parser.add_argument("--output", default="diagnostic/surface_transition_sampling", help="输出目录")
    args = parser.parse_args()

    if args.interval <= 0 or args.samples < 2 or args.rounds < 1:
        print("参数无效：interval>0, samples>=2, rounds>=1")
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

    print(f"parent hwnd={parent.hwnd}")
    for index, view in enumerate(views, 1):
        print(
            f"  [{index}] hwnd={view.hwnd} "
            f"client={view.window.width}x{view.window.height} "
            f"visible={view.window.visible} title={view.window.title!r}"
        )

    small = [
        i for i, view in enumerate(views, 1)
        if (view.window.width, view.window.height) == (806, 606)
    ]
    large = [
        i for i, view in enumerate(views, 1)
        if (view.window.width, view.window.height) == (1024, 768)
    ]
    if not small or not large:
        print("未同时发现 client=806x606 与 client=1024x768 的两个稳定 surface。")
        print("本探针不会猜测哪个是大/小，请先确认窗口实际 geometry。")
        return 1

    # Use the first matching surface of each size; this is diagnostic only.
    small_index = small[0]
    large_index = large[0]
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()

    print(f"small_surface=view{small_index} (806x606)")
    print(f"large_surface=view{large_index} (1024x768)")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"sample_interval_ms={args.interval * 1000:.1f}")
    print(f"samples_per_transition={args.samples}")
    print(f"rounds_per_direction={args.rounds}")
    print("注意：本探针只读取/截图/切换 Surface，不修改现有生产功能。")

    cap = WindowsGraphicsCapture()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[dict[str, object]] = []
    original_fg = int(__import__("ctypes").windll.user32.GetForegroundWindow())

    try:
        # Start from small for the first direction.
        manager.switch_surface_to(small_index)
        for round_no in range(1, args.rounds + 1):
            print(f"\n=== round {round_no}: 小 -> 大 ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, small_index, large_index,
                interval=args.interval, samples=args.samples,
                settle_threshold=args.settle_threshold,
                settle_consecutive=args.settle_consecutive,
                out_dir=out_dir, round_no=round_no,
            )
            all_results.append(result)
            print(result)

            print(f"=== round {round_no}: 大 -> 小 ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, large_index, small_index,
                interval=args.interval, samples=args.samples,
                settle_threshold=args.settle_threshold,
                settle_consecutive=args.settle_consecutive,
                out_dir=out_dir, round_no=round_no,
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
                f"switch_return={item['switch_return_ms']}ms, "
                f"target_geometry={item['first_target_geometry_ms']}ms, "
                f"visual_stable={item['first_visual_stable_ms']}ms"
            )
        print(f"summary={summary}")
        print(f"foreground_unchanged={int(__import__('ctypes').windll.user32.GetForegroundWindow()) == original_fg}")
        return 0
    finally:
        try:
            manager.switch_surface_to(original_surface)
            manager.switch_to(original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
        final_fg = int(__import__("ctypes").windll.user32.GetForegroundWindow())
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_final={final_fg}")
        print(f"foreground_unchanged={final_fg == original_fg}")
