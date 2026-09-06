"""MVP-5c CLI: select a character and detect 命魂任务 state (800×600 baseline)."""
from __future__ import annotations

import argparse

from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character
from .soul_task import SOUL_TASK_BASELINE_SIZE
from .soul_task_flow import run_soul_task_claim_diagnosis


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect 命魂任务 claimed state for a 梦幻西游 character.")
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output-dir", default="diagnostic\\soul_task")
    args = parser.parse_args()

    print("[验证] 1/5 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"parent window not found: {args.title!r}")
        return 2
    print(f"parent hwnd={parent.hwnd}")

    print("[验证] 2/5 扫描已登录角色")
    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"logged_in characters={len(accounts)}")
    if not accounts:
        print("未发现已登录角色，无法检测命魂任务状态。")
        return 3
    for option, account in enumerate(accounts, start=1):
        resolution = account.expected_resolution
        res_text = f"{resolution[0]}x{resolution[1]}" if resolution else "unknown"
        print(
            f"  [{option}] character={account.character_name!r} "
            f"identity={account.identity!r} view=#{account.view_index} client={res_text}"
        )

    print("[验证] 3/5 选择角色")
    try:
        choice = int(input("请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 4
    if not 1 <= choice <= len(accounts):
        print(f"角色编号必须在 1 到 {len(accounts)} 之间。")
        return 4
    selected = select_character(scan, accounts[choice - 1].view_index)
    print(
        f"selected character={selected.character_name!r} "
        f"view_index={selected.view_index} hwnd={selected.hwnd}"
    )
    resolution = selected.account.expected_resolution
    if resolution != SOUL_TASK_BASELINE_SIZE:
        print(
            f"当前角色分辨率不是基线 {SOUL_TASK_BASELINE_SIZE[0]}x{SOUL_TASK_BASELINE_SIZE[1]}，"
            "请先统一到 800×600。"
        )
        return 8

    print("[验证] 4/5 后台检测命魂领取状态")
    result = run_soul_task_claim_diagnosis(
        parent.hwnd,
        selected,
        output_dir=args.output_dir,
        require_baseline=True,
    )
    print(f"client_size={result.client_size}")
    print(f"soul_task_status={result.status.value}")
    if result.observation is not None:
        print(f"detection_reason={result.observation.reason.value}")
        print(f"confidence={result.observation.confidence:.3f}")
        print(f"match_location={result.observation.match_location}")
        for evidence in result.observation.evidence:
            print(f"evidence={evidence}")
    print(f"screenshot={result.screenshot_path}")
    print(f"foreground_unchanged={result.foreground_unchanged}")
    print(f"restored_surface={result.restored_surface}")
    print(f"restored_tab={result.restored_tab}")
    print(result.message)
    if result.error:
        print(f"error={result.error}")

    print("[验证] 5/5 结果")
    if result.ok:
        print("result=PASSED")
        return 0
    print("result=FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
