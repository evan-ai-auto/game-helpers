"""Diagnostic-only sampler for measuring hosted WSGAME surface transitions.

This probe intentionally does not modify GameViewManager, VerificationSession,
or any production workflow. It discovers the current WSGAME instances first,
records their client geometry, then automatically samples both directions
between two selected instances. The size labels are observations, not
identity: no view number or login state is treated as inherently small/large.
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


def _frame_signature(frame) -> tuple[int, int]:
    return int(frame.width), int(frame.height)


def _fingerprint(frame, size: int = 48) -> np.ndarray:
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
    return frame, (time.perf_counter() - started) * 1000.0


def _measure_stable_baseline(
    cap: WindowsGraphicsCapture,
    parent_hwnd: int,
    *,
    interval: float,
    samples: int,
    settle_threshold: float,
    settle_consecutive: int,
) -> tuple[tuple[int, int], float | None]:
    """Observe one already-selected surface until its capture size is stable."""
    previous: np.ndarray | None = None
    deltas: list[float | None] = []
    last_size: tuple[int, int] | None = None
    size_run = 0
    first_stable_ms: float | None = None
    started = time.perf_counter()
    for _ in range(samples):
        frame, _ = _capture(cap, parent_hwnd)
        size = _frame_signature(frame)
        if size == last_size:
            size_run += 1
        else:
            last_size = size
            size_run = 1
        fp = _fingerprint(frame)
        delta = _fingerprint_delta(previous, fp)
        deltas.append(delta)
        previous = fp
        if first_stable_ms is None and size_run >= settle_consecutive:
            stable_index = _stable_run(deltas, settle_threshold, settle_consecutive)
            if stable_index is not None:
                first_stable_ms = (time.perf_counter() - started) * 1000.0
        time.sleep(interval)
    if last_size is None:
        raise RuntimeError("no baseline frame captured")
    return last_size, first_stable_ms


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
    views = manager.views()
    source = views[source_index - 1]
    target = views[target_index - 1]
    source_client = (source.window.width, source.window.height)
    target_client = (target.window.width, target.window.height)

    source_frame_size, _ = _measure_stable_baseline(
        cap, parent_hwnd, interval=interval, samples=max(4, settle_consecutive + 1),
        settle_threshold=settle_threshold, settle_consecutive=settle_consecutive,
    )

    direction = (
        "小切大" if source_frame_size[0] * source_frame_size[1] < 1 else "未知"
    )
    # Direction is resolved from the actual stable source/target capture sizes
    # after the target has also been observed; no view number is used.
    manager.switch_surface_to(target_index)
    target_frame_size, _ = _measure_stable_baseline(
        cap, parent_hwnd, interval=interval, samples=max(4, settle_consecutive + 1),
        settle_threshold=settle_threshold, settle_consecutive=settle_consecutive,
    )
    manager.switch_surface_to(source_index)
    source_frame_size, _ = _measure_stable_baseline(
        cap, parent_hwnd, interval=interval, samples=max(4, settle_consecutive + 1),
        settle_threshold=settle_threshold, settle_consecutive=settle_consecutive,
    )
    if source_frame_size == target_frame_size:
        direction = "同尺寸切换"
    elif source_frame_size[0] * source_frame_size[1] < target_frame_size[0] * target_frame_size[1]:
        direction = "小切大"
    else:
        direction = "大切小"

    # The actual timed transition begins from a confirmed source baseline.
    transition_dir = f"view{source_index}__{source_frame_size[0]}x{source_frame_size[1]}__to__view{target_index}__{target_frame_size[0]}x{target_frame_size[1]}"
    transition_dir_path = out_dir / f"round-{round_no:02d}-{transition_dir}"
    transition_dir_path.mkdir(parents=True, exist_ok=True)

    switch_started = time.perf_counter()
    manager.switch_surface_to(target_index)
    switch_return_ms = (time.perf_counter() - switch_started) * 1000.0

    rows: list[dict[str, object]] = []
    previous_fp: np.ndarray | None = None
    stable_values: list[float | None] = []
    first_target_size_ms: float | None = None
    stable_index: int | None = None
    stable_size_run = 0

    for sample_index in range(samples):
        if sample_index:
            time.sleep(interval)
        capture_started = time.perf_counter()
        frame = cap.capture(parent_hwnd)
        capture_finished = time.perf_counter()
        since_switch_ms = (capture_finished - switch_started) * 1000.0
        capture_ms = (capture_finished - capture_started) * 1000.0
        geometry = _frame_signature(frame)
        if geometry == target_frame_size and first_target_size_ms is None:
            first_target_size_ms = since_switch_ms

        if geometry == target_frame_size:
            stable_size_run += 1
        else:
            stable_size_run = 0

        fp = _fingerprint(frame)
        delta = _fingerprint_delta(previous_fp, fp)
        previous_fp = fp
        stable_values.append(delta)
        if stable_index is None and stable_size_run >= settle_consecutive:
            candidate = _stable_run(stable_values, settle_threshold, settle_consecutive)
            if candidate is not None:
                stable_index = candidate

        save_png(frame, str(transition_dir_path / f"frame-{sample_index:03d}-{since_switch_ms:08.1f}ms.png"))
        rows.append({
            "sample": sample_index,
            "since_switch_ms": round(since_switch_ms, 3),
            "capture_ms": round(capture_ms, 3),
            "frame_width": geometry[0],
            "frame_height": geometry[1],
            "source_frame_width": source_frame_size[0],
            "source_frame_height": source_frame_size[1],
            "target_frame_width": target_frame_size[0],
            "target_frame_height": target_frame_size[1],
            "target_geometry": geometry == target_frame_size,
            "adjacent_fingerprint_delta": "" if delta is None else round(delta, 4),
        })

    first_visual_stable_ms = None
    if stable_index is not None and stable_index < len(rows):
        first_visual_stable_ms = float(rows[stable_index]["since_switch_ms"])

    csv_path = transition_dir_path / "samples.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    return {
        "direction": direction,
        "source_view": source_index,
        "target_view": target_index,
        "source_client_size": f"{source_client[0]}x{source_client[1]}",
        "target_client_size": f"{target_client[0]}x{target_client[1]}",
        "source_capture_size": f"{source_frame_size[0]}x{source_frame_size[1]}",
        "target_capture_size": f"{target_frame_size[0]}x{target_frame_size[1]}",
        "switch_return_ms": round(switch_return_ms, 3),
        "first_target_capture_size_ms": None if first_target_size_ms is None else round(first_target_size_ms, 3),
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

    parser = argparse.ArgumentParser(description="自动采样 WSGAME 大/小 Surface 切换渲染耗时（诊断专用）")
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

    scan = scan_game_accounts(parent.hwnd)
    print(f"parent hwnd={parent.hwnd}")
    print("=== 初始角色/Surface 扫描 ===")
    for account in scan.accounts:
        resolution = account.expected_resolution
        print(
            f"  view=#{account.view_index} character={account.character_name!r} "
            f"logged_in={account.logged_in} hwnd={account.hwnd} "
            f"client={resolution[0]}x{resolution[1] if resolution else 'unknown'} "
            if resolution else
            f"  view=#{account.view_index} character={account.character_name!r} "
            f"logged_in={account.logged_in} hwnd={account.hwnd} client=unknown"
        )

    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    original_fg = int(ctypes.windll.user32.GetForegroundWindow())
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"sample_interval_ms={args.interval * 1000:.1f}")
    print(f"samples_per_transition={args.samples}")
    print(f"rounds_per_direction={args.rounds}")
    print("本探针全自动切换、截图、检测；不需要手动切子窗口。")
    print("分辨率只作为当前观测状态，不与 view 编号或登录状态绑定。")

    cap = WindowsGraphicsCapture()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[dict[str, object]] = []

    # Pick two views from the first scan, preferring distinct observed client
    # sizes. If client sizes are equal, still measure the pair: capture sizes
    # may differ because the host/capture path can scale them differently.
    distinct = []
    for i, a in enumerate(scan.accounts, 1):
        for j, b in enumerate(scan.accounts, 1):
            if i < j and a.expected_resolution != b.expected_resolution:
                distinct.append((i, j))
    pair = distinct[0] if distinct else (1, 2)
    first_view, second_view = pair
    print(f"sampling_pair=view{first_view} <-> view{second_view}")

    try:
        manager.switch_surface_to(first_view)
        for round_no in range(1, args.rounds + 1):
            print(f"\n=== round {round_no}: 自动测量 view{first_view} -> view{second_view} ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, first_view, second_view,
                interval=args.interval, samples=args.samples,
                settle_threshold=args.settle_threshold,
                settle_consecutive=args.settle_consecutive,
                out_dir=out_dir, round_no=round_no,
            )
            all_results.append(result)
            print(result)

            print(f"=== round {round_no}: 自动测量 view{second_view} -> view{first_view} ===")
            result = _sample_transition(
                cap, manager, parent.hwnd, second_view, first_view,
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
                f"view{item['source_view']} {item['source_capture_size']} -> "
                f"view{item['target_view']} {item['target_capture_size']}, "
                f"switch_return={item['switch_return_ms']}ms, "
                f"target_size={item['first_target_capture_size_ms']}ms, "
                f"visual_stable={item['first_visual_stable_ms']}ms"
            )
        print(f"summary={summary}")
        print(f"foreground_unchanged={int(ctypes.windll.user32.GetForegroundWindow()) == original_fg}")
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
