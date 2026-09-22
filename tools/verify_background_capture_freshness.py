"""Run the layered background WGC freshness probe for a selected game view."""
from __future__ import annotations

import argparse
from pathlib import Path

from game_helpers.core.view_manager import GameViewManager
from game_helpers.tasks.background_capture_freshness import run_background_capture_freshness
from game_helpers.tasks.background_context import BackgroundRunGuard
from game_helpers.tasks.character_selection import scan_and_select
from game_helpers.tasks.soul_task import SOUL_TASK_BASELINE_SIZE
from game_helpers.tasks.verification_session import VerificationSession
from game_helpers.capture import WindowsGraphicsCapture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-hwnd", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--view-index", required=True, type=int)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="apply the current Surface-switch/RedrawWindow refresh once before sampling",
    )
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("diagnostic/workflow_runs/soul_shortcut_diagnostic/background_capture_freshness"),
    )
    args = parser.parse_args()

    if args.seconds <= 0 or args.interval <= 0:
        parser.error("--seconds and --interval must be positive")

    selection = scan_and_select(args.parent_hwnd, args.view_index)
    manager = GameViewManager(args.parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    session = VerificationSession(
        parent_hwnd=args.parent_hwnd,
        selected=selection,
        manager=manager,
        capture=WindowsGraphicsCapture(),
    )

    try:
        session.sync_character()
        geometry = session.geometry()
        if (geometry.client_width, geometry.client_height) != SOUL_TASK_BASELINE_SIZE:
            raise RuntimeError(
                "当前客户区不是 800x600，诊断任务停止："
                f"{geometry.client_width}x{geometry.client_height}"
            )

        report = run_background_capture_freshness(
            session,
            args.output_dir / ("refresh" if args.refresh else "covered"),
            wait_seconds=args.seconds,
            sample_interval=args.interval,
            refresh_before_sampling=args.refresh,
        )
        print(f"[命魂诊断] 角色：{selection.character_name}")
        print(f"[命魂诊断] 模式：{'covered+refresh' if args.refresh else 'covered'}")
        print(f"[命魂诊断] Host 最大变化：{report['host']['max_diff_ratio']:.6f}")
        print(f"[命魂诊断] WSGAME 最大变化：{report['wsgame_crop']['max_diff_ratio']:.6f}")
        print(f"[命魂诊断] Playfield 最大变化：{report['playfield']['max_diff_ratio']:.6f}")
        print(f"[命魂诊断] RightEdge 最大变化：{report['right_edge']['max_diff_ratio']:.6f}")
        print(f"[命魂诊断] 报告：{args.output_dir / ('refresh' if args.refresh else 'covered') / 'validation-report.json'}")
        return 0
    finally:
        restore = guard.finish()
        print(
            "[命魂诊断] 恢复："
            f"Surface={'成功' if restore['restored_surface'] else '失败'}；"
            f"标签={'成功' if restore['restored_tab'] else '失败'}；"
            f"前台={'未变化' if restore['foreground_unchanged'] else '已变化'}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
