"""Standalone CLI: manually collect a client click coordinate for asset calibration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .manual_coordinate import collect_client_coordinate
from .soul_task import SOUL_TASK_BASELINE_SIZE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="人工协助采集子窗客户区坐标（F8）。用于新资产标定，不属于正常自动化流程。"
    )
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument(
        "--prompt",
        default="请把鼠标移到目标控件上（出现 tooltip 后保持不动）。",
        help="提示文案",
    )
    parser.add_argument(
        "--asset",
        default="",
        help="可选：资产 JSON 路径；采集后打印建议写入的字段片段（不自动改文件）",
    )
    args = parser.parse_args()

    print("[采坐标] 1/3 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"未找到游戏主窗口: {args.title!r}")
        return 2
    print(f"parent hwnd={parent.hwnd}")

    print("[采坐标] 2/3 选择已登录角色")
    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    if not accounts:
        print("未发现已登录角色。")
        return 3
    for option, account in enumerate(accounts, start=1):
        resolution = account.expected_resolution
        res_text = f"{resolution[0]}x{resolution[1]}" if resolution else "unknown"
        print(
            f"  [{option}] {account.character_name!r} | "
            f"实例=#{account.view_index} | client={res_text}"
        )
    try:
        choice = int(input("请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 4
    if not 1 <= choice <= len(accounts):
        print("角色编号无效。")
        return 4
    selected = select_character(scan, accounts[choice - 1].view_index)
    resolution = selected.account.expected_resolution
    print(
        f"selected character={selected.character_name!r} "
        f"view_index={selected.view_index} hwnd={selected.hwnd} "
        f"client={resolution}"
    )
    sync_selected_character(parent.hwnd, selected)

    print("[采坐标] 3/3 人工悬停 + F8")
    sample = collect_client_coordinate(
        selected.hwnd,
        prompt=args.prompt,
        foreground_hwnd_for_hover=parent.hwnd,
    )
    res_key = (
        f"{resolution[0]}x{resolution[1]}"
        if resolution
        else f"{SOUL_TASK_BASELINE_SIZE[0]}x{SOUL_TASK_BASELINE_SIZE[1]}"
    )
    suggestion = {
        "verification_status": "pending",
        "verified_resolutions": [],
        "click_client_by_resolution": {res_key: list(sample.client)},
        "verification_notes": "人工 F8 采点；通过点击验证后再改为 verified。",
    }
    print("suggested_asset_fields=")
    print(json.dumps(suggestion, ensure_ascii=False, indent=2))
    if args.asset:
        path = Path(args.asset)
        print(f"asset_path={path}（未自动写入；请人工合并后验证）")
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                print(f"asset_name={payload.get('name') or payload.get('id')}")
                print(f"asset_verification_status={payload.get('verification_status')}")
            except Exception as exc:
                print(f"asset_read_warning={exc}")
    print("result=CAPTURED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
