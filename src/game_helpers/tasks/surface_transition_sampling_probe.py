"""Diagnostic-only sampler for hosted WSGAME surface transitions.

Historical entry point (unchanged):

    python -m game_helpers.tasks.surface_transition_sampling_probe

Runs fully in the background: surface + native tab switch without activating the
game window. Host relayout is expected from the game after select_tab.
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
from .surface_transition_sampling_host import (
    get_client_size,
    switch_view_background,
    wait_parent_client_at_least,
)


def _calibrate_view(cap, manager, parent_hwnd, account, *, host_ready_timeout: float):
    """Background-switch to the view, wait for host fit, capture native baseline."""
    profile = account.expected_resolution
    assert profile is not None
    switch_view_background(manager, account.view_index)
    parent_client = wait_parent_client_at_least(
        parent_hwnd, profile[0], profile[1], timeout=host_ready_timeout
    )
    parent_geometry = query_surface_geometry(parent_hwnd)
    child_geometry = query_surface_geometry(account.hwnd)
    host, crop, _scales, mapped, clipped = capture_role(
        cap, parent_hwnd, parent_geometry, child_geometry
    )
    if clipped != mapped:
        raise RuntimeError(
            f"baseline for view#{account.view_index} is incomplete: "
            f"parent_client={parent_client[0]}x{parent_client[1]}, "
            f"parent_capture={host.width}x{host.height}, "
            f"client={profile[0]}x{profile[1]}, "
            f"crop={crop.width}x{crop.height}, mapped={mapped}, clipped={clipped}"
        )
    baseline = (crop.width, crop.height)
    print(
        f"baseline view#{account.view_index} "
        f"client={profile[0]}x{profile[1]} "
        f"crop={baseline[0]}x{baseline[1]} "
        f"parent_client={parent_client[0]}x{parent_client[1]} "
        f"parent_capture={host.width}x{host.height}"
    )
    return parent_geometry, child_geometry, baseline, host


def _run_directed_sample(
    *,
    cap,
    manager,
    parent_hwnd,
    source_account,
    target_account,
    source_geometry,
    target_geometry,
    source_baseline,
    target_baseline,
    interval: float,
    samples: int,
    threshold: float,
    consecutive: int,
    output_dir: Path,
    round_no: int,
    host_ready_timeout: float,
) -> dict[str, object]:
    target_profile = target_account.expected_resolution
    source_profile = source_account.expected_resolution
    assert target_profile is not None and source_profile is not None

    # Ensure we start on the source view with a host sized for the source.
    switch_view_background(manager, source_account.view_index)
    wait_parent_client_at_least(
        parent_hwnd, source_profile[0], source_profile[1], timeout=host_ready_timeout
    )
    parent_geometry = query_surface_geometry(parent_hwnd)
    source_geometry = query_surface_geometry(source_account.hwnd)
    target_geometry = query_surface_geometry(target_account.hwnd)

    result = sample_transition(
        cap,
        manager,
        parent_hwnd,
        parent_geometry,
        source_geometry,
        target_geometry,
        source_account.view_index,
        target_account.view_index,
        source_profile,
        target_profile,
        source_baseline,
        target_baseline,
        interval=interval,
        samples=samples,
        threshold=threshold,
        consecutive=consecutive,
        output_dir=output_dir,
        round_no=round_no,
        host_ready_timeout=host_ready_timeout,
    )
    if not result.get("complete", False):
        reason = result.get("failure_reason") or "incomplete target coverage"
        print(f"采样失败（{result['direction']}）: {reason}")
        raise RuntimeError(reason)
    return result


def main() -> int:
    if sys.platform != "win32":
        print("本探针仅支持 Windows。")
        return 2
    parser = argparse.ArgumentParser(description="诊断 WSGAME 大/小 Surface 切换渲染稳定时间（仅诊断，纯后台）")
    parser.add_argument("parent_title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--settle-threshold", type=float, default=2.0)
    parser.add_argument("--settle-consecutive", type=int, default=3)
    parser.add_argument("--host-ready-timeout", type=float, default=3.0)
    parser.add_argument("--output", default="diagnostic/surface_transition_sampling")
    args = parser.parse_args()

    parent = find_window(args.parent_title)
    if parent is None:
        print(f"parent window not found: {args.parent_title!r}")
        return 2
    # activate_before_switch stays False: never Ctrl+Tab / never raise game.
    manager = GameViewManager(parent.hwnd, timeout=2.0, activate_before_switch=False)
    if len(manager.views()) < 2:
        print("至少需要 2 个 WSGAME surface")
        return 1

    scan = scan_game_accounts(parent.hwnd)
    print(f"parent hwnd={parent.hwnd}")
    initial_client = get_client_size(parent.hwnd)
    print(f"parent_client_initial={initial_client[0]}x{initial_client[1]}")
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
    print("截图策略：纯后台 surface+select_tab；等宿主重排后按目标原生 client 截取（小按小、大按大）。")

    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    original_fg = int(ctypes.windll.user32.GetForegroundWindow())
    cap = WindowsGraphicsCapture()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []

    try:
        print("=== 标定 baseline（后台 Tab 对齐 + 原生尺寸） ===")
        _, first_geometry, first_baseline, _ = _calibrate_view(
            cap, manager, parent.hwnd, first, host_ready_timeout=args.host_ready_timeout
        )
        _, second_geometry, second_baseline, _ = _calibrate_view(
            cap, manager, parent.hwnd, second, host_ready_timeout=args.host_ready_timeout
        )

        switch_view_background(manager, first.view_index)
        wait_parent_client_at_least(
            parent.hwnd,
            first.expected_resolution[0],
            first.expected_resolution[1],
            timeout=args.host_ready_timeout,
        )
        print("=== 开始双向自动采样 ===")
        for round_no in range(1, args.rounds + 1):
            print(f"\n=== round {round_no}: A -> B ===")
            result = _run_directed_sample(
                cap=cap,
                manager=manager,
                parent_hwnd=parent.hwnd,
                source_account=first,
                target_account=second,
                source_geometry=first_geometry,
                target_geometry=second_geometry,
                source_baseline=first_baseline,
                target_baseline=second_baseline,
                interval=args.interval,
                samples=args.samples,
                threshold=args.settle_threshold,
                consecutive=args.settle_consecutive,
                output_dir=out_dir,
                round_no=round_no,
                host_ready_timeout=args.host_ready_timeout,
            )
            results.append(result)
            print(result)
            print(f"=== round {round_no}: B -> A ===")
            result = _run_directed_sample(
                cap=cap,
                manager=manager,
                parent_hwnd=parent.hwnd,
                source_account=second,
                target_account=first,
                source_geometry=second_geometry,
                target_geometry=first_geometry,
                source_baseline=second_baseline,
                target_baseline=first_baseline,
                interval=args.interval,
                samples=args.samples,
                threshold=args.settle_threshold,
                consecutive=args.settle_consecutive,
                output_dir=out_dir,
                round_no=round_no,
                host_ready_timeout=args.host_ready_timeout,
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
                f"parent_after={item.get('parent_client_after_switch')}; "
                f"switch_return={item['switch_return_ms']}ms; "
                f"target_coverage={item['first_target_coverage_ms']}ms; "
                f"visual_stable={item['first_visual_stable_ms']}ms; "
                f"complete={item['complete']}"
            )
        print(f"summary={summary}")
        return 0
    except RuntimeError as exc:
        print(f"探针中止: {exc}")
        if results:
            summary = out_dir / "summary.csv"
            with summary.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(results[0]))
                writer.writeheader()
                writer.writerows(results)
            print(f"partial_summary={summary}")
        return 1
    finally:
        try:
            manager.switch_surface_to(original_surface)
            manager.switch_to(original_tab)
            if manager.current_surface_index() != original_surface:
                raise RuntimeError("could not restore original surface")
            if manager.current_index() != original_tab:
                raise RuntimeError("could not restore original tab")
        except Exception as restore_exc:
            print(f"restore_warning: {restore_exc}")
        finally:
            final_fg = int(ctypes.windll.user32.GetForegroundWindow())
            print("\n恢复测试上下文：")
            try:
                print(f"restored_surface={manager.current_surface_index() == original_surface}")
                print(f"restored_tab={manager.current_index() == original_tab}")
            except Exception as state_exc:
                print(f"restore_state_warning: {state_exc}")
            print(f"foreground_final={final_fg}")
            print(f"foreground_unchanged={final_fg == original_fg}")


if __name__ == "__main__":
    raise SystemExit(main())
