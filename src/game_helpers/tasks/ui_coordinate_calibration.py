"""Manual fixed-coordinate calibration for the two supported 梦幻西游 UI controls.

The experiment deliberately keeps coordinate collection separate from visual
state verification. A coordinate is collected once for the selected target and
resolution, then the existing PostMessageW click + visual verification path is
run. At this stage a PASS/FAIL result is only an auxiliary signal; the operator
should use the saved before/after screenshots and the live game view as the
manual source of truth when the visual assets are incomplete.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..capture import WindowsGraphicsCapture
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .fixed_ui_coordinate import DEFAULT_COORDINATES_PATH
from .manual_coordinate import collect_client_coordinate
from .soul_task import SOUL_TASK_BASELINE_SIZE
from .ui_coordinate_calibration_io import (
    TARGET_ITEM_PANEL,
    TARGET_SHORTCUT_PANEL,
    session_item_profile_path,
    write_sample,
)
from .ui_coordinate_calibration_runners import run_item_panel, run_shortcut_panel
from .verification_session import VerificationSession

__all__ = [
    "TARGET_ITEM_PANEL",
    "TARGET_SHORTCUT_PANEL",
    "main",
    "session_item_profile_path",
]


def main() -> int:
    if sys.platform != "win32":
        print("本实验仅支持 Windows。")
        return 2

    parser = argparse.ArgumentParser(description="梦幻西游固定位置 UI 坐标采集与后台点击实验。")
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output", default=str(DEFAULT_COORDINATES_PATH))
    parser.add_argument("--diagnostic-dir", default="diagnostic/calibration/ui_click")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        print("--timeout 必须大于 0。")
        return 2

    parent = find_window(args.title)
    if parent is None:
        print(f"未找到游戏主窗口: {args.title!r}")
        return 2

    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"parent hwnd={parent.hwnd}")
    print(f"logged_in characters={len(accounts)}")
    if not accounts:
        print("未发现已登录角色，无法采坐标。")
        return 3
    for index, account in enumerate(accounts, 1):
        resolution = account.expected_resolution
        resolution_text = f"{resolution[0]}x{resolution[1]}" if resolution else "unknown"
        print(f"  [{index}] {account.character_name!r} | 实例=#{account.view_index} | client={resolution_text} | identity={account.identity!r}")

    try:
        choice = int(input("请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 4
    if not 1 <= choice <= len(accounts):
        print(f"角色编号必须在 1 到 {len(accounts)} 之间。")
        return 4

    selected = select_character(scan, accounts[choice - 1].view_index)
    sync_selected_character(parent.hwnd, selected)
    resolution = selected.account.expected_resolution
    if resolution != SOUL_TASK_BASELINE_SIZE:
        print(f"当前角色分辨率为 {resolution!r}，本实验只接受 800x600。")
        return 8
    resolution_key = f"{resolution[0]}x{resolution[1]}"
    session = VerificationSession(
        parent_hwnd=parent.hwnd,
        selected=selected,
        manager=GameViewManager(parent.hwnd, timeout=2.0),
        capture=WindowsGraphicsCapture(),
    )
    print(f"selected character={selected.character_name!r} view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"resolution_key={resolution_key}")

    print("\n[800×600 固定位置 UI 坐标采集 + 后台点击实验]")
    print("请选择采集目标：")
    print("1. 道具栏")
    print("2. 任务图标集合开关")
    print("0. 退出")
    try:
        target_choice = input("请选择采集目标：").strip()
    except EOFError:
        print("已取消。")
        return 0
    targets = {"1": TARGET_ITEM_PANEL, "2": TARGET_SHORTCUT_PANEL}
    target = targets.get(target_choice)
    if target is None:
        if target_choice == "0":
            print("已退出。")
            return 0
        print("采集目标无效。")
        return 5

    prompt = (
        "请采集当前 800×600 底部「道具」图标坐标。"
        if target == TARGET_ITEM_PANEL
        else "请采集当前 800×600 左侧「任务图标集合开关」固定位置坐标；折叠态和展开态共用此坐标。"
    )
    sample = collect_client_coordinate(
        selected.hwnd,
        prompt=prompt,
        foreground_hwnd_for_hover=parent.hwnd,
    )
    click_client = tuple(sample.client)
    output = Path(args.output)
    write_sample(
        output,
        resolution_key=resolution_key,
        target=target,
        sample=sample,
        character_name=selected.character_name,
        identity=selected.account.identity,
    )
    print("\nMANUAL_FIXED_UI_COORDINATE")
    print(f"target={target}")
    print(f"resolution_key={resolution_key}")
    print(f"click_client={click_client}")
    print(f"cursor_screen={sample.screen}")
    print(f"target_hwnd={sample.target_hwnd}")
    print(f"saved_to={output}")
    print("坐标已记录。现在开始按现有规则执行后台点击 + 视觉验证。")

    diagnostic_dir = Path(args.diagnostic_dir) / target
    if target == TARGET_ITEM_PANEL:
        return run_item_panel(
            session,
            click_client,
            diagnostic_dir=diagnostic_dir,
            timeout=args.timeout,
        )
    return run_shortcut_panel(
        session,
        click_client,
        diagnostic_dir=diagnostic_dir,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
