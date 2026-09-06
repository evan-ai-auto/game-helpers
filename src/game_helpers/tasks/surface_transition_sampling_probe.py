"""Diagnostic-only sampler for hosted WSGAME surface transitions.

Historical entry point (unchanged):

    python -m game_helpers.tasks.surface_transition_sampling_probe

Implementation helpers live in sibling modules; CLI and workflow stay here.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import sys
from pathlib import Path

from ..capture import WindowsGraphicsCapture
from ..core.surface import query_surface_geometry
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .surface_transition_sampling import sample_transition
from .surface_transition_sampling_capture import capture_role


def main() -> int:
    if sys.platform != "win32":
        print("本探针仅支持 Windows。")
        return 2
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
        print(f"parent window not found: {args.parent_title!r}")
        return 2
    manager = GameViewManager(parent.hwnd, timeout=2.0)
    if len(manager.views()) < 2:
        print("至少需要 2 个 WSGAME surface")
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

    pair = None
    for i, a in enumerate(scan.accounts):
        for b in scan.accounts[i + 1 :]:
            if a.expected_resolution and b.expected_resolution and a.expected_resolution != b.expected_resolution:
                pair = (a, b)
                break
        if pair:
            break
    if pair is None:
        print("未找到两个不同 Client 分辨率的 WSGAME 实例，无法进行大小切换诊断。")
        return 1

    first, second = pair
    print(
        f"sampling_pair=view{first.view_index}"
        f"({first.expected_resolution[0]}x{first.expected_resolution[1]}) <-> "
        f"view{second.view_index}"
        f"({second.expected_resolution[0]}x{second.expected_resolution[1]})"
    )
    print("截图策略：始终以较大 Client 分辨率作为统一观察画布；父窗口 capture 尺寸单独记录。")

    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    original_fg = int(ctypes.windll.user32.GetForegroundWindow())
    cap = WindowsGraphicsCapture()
    parent_geometry = query_surface_geometry(parent.hwnd)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []

    try:
        # Calibration is part of the initial role/resolution profile and is not timed as a transition.
        manager.switch_surface_to(first.view_index)
        first_geometry = query_surface_geometry(first.hwnd)
        host, crop, *_ = capture_role(cap, parent.hwnd, parent_geometry, first_geometry, (1024, 768))
        first_baseline = (crop.width, crop.height)
        print(
            f"baseline_A client={first.expected_resolution[0]}x{first.expected_resolution[1]} "
            f"crop={first_baseline[0]}x{first_baseline[1]} parent_capture={host.width}x{host.height}"
        )

        manager.switch_surface_to(second.view_index)
        second_geometry = query_surface_geometry(second.hwnd)
        host, crop, *_ = capture_role(cap, parent.hwnd, parent_geometry, second_geometry, (1024, 768))
        second_baseline = (crop.width, crop.height)
        print(
            f"baseline_B client={second.expected_resolution[0]}x{second.expected_resolution[1]} "
            f"crop={second_baseline[0]}x{second_baseline[1]} parent_capture={host.width}x{host.height}"
        )

        manager.switch_surface_to(first.view_index)
        print("=== 开始双向自动采样 ===")
        for round_no in range(1, args.rounds + 1):
            print(f"\n=== round {round_no}: A -> B ===")
            result = sample_transition(
                cap,
                manager,
                parent.hwnd,
                parent_geometry,
                first_geometry,
                second_geometry,
                first.view_index,
                second.view_index,
                first.expected_resolution,
                second.expected_resolution,
                first_baseline,
                second_baseline,
                interval=args.interval,
                samples=args.samples,
                threshold=args.settle_threshold,
                consecutive=args.settle_consecutive,
                output_dir=out_dir,
                round_no=round_no,
            )
            results.append(result)
            print(result)
            print(f"=== round {round_no}: B -> A ===")
            result = sample_transition(
                cap,
                manager,
                parent.hwnd,
                parent_geometry,
                second_geometry,
                first_geometry,
                second.view_index,
                first.view_index,
                second.expected_resolution,
                first.expected_resolution,
                second_baseline,
                first_baseline,
                interval=args.interval,
                samples=args.samples,
                threshold=args.settle_threshold,
                consecutive=args.settle_consecutive,
                output_dir=out_dir,
                round_no=round_no,
            )
            results.append(result)
            print(result)

        summary = out_dir / "summary.csv"
        with summary.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(results[0]))
            writer.writeheader()
            writer.writerows(results)
        print("\n=== 汇总 ===")
        for item in results:
            print(
                f"{item['direction']}: client {item['source_client_size']} -> {item['target_client_size']}; "
                f"baseline_crop {item['source_baseline_crop']} -> {item['target_baseline_crop']}; "
                f"switch_return={item['switch_return_ms']}ms; "
                f"target_coverage={item['first_target_coverage_ms']}ms; "
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
