"""Interactive verification menu: choose character once, then compose flow nodes."""
from __future__ import annotations

import sys

from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .background_item_panel_toggle_probe import run as verify_item_panel_toggle
from .character_selection import logged_in_accounts, select_character
from .soul_task_toggle_auto_probe import run as verify_soul_toggle

OPTIONS = {
    "1": "命魂任务面板：自动识别并切换折叠/展开",
    "2": "道具栏：自动识别当前状态并执行反向切换",
}


def main() -> int:
    title = sys.argv[1] if len(sys.argv) > 1 else "梦幻西游 ONLINE"
    parent = find_window(title)
    if parent is None:
        print(f"parent window not found: {title!r}")
        return 2

    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"parent hwnd={parent.hwnd}")
    for i, account in enumerate(accounts, 1):
        print(f"  [{i}] character='{account.character_name}' identity='{account.identity}' view=#{account.view_index}")
    if not accounts:
        print("没有找到已登录角色。")
        return 1

    try:
        character_choice = int(input("\n请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 1
    if not 1 <= character_choice <= len(accounts):
        print("角色编号无效。")
        return 1

    selected = select_character(scan, accounts[character_choice - 1].view_index)
    print(f"已选择角色：'{selected.character_name}' (view=#{selected.view_index})")

    print("\n可选手动验证流程：")
    for key, label in OPTIONS.items():
        print(f"  {key}. {label}")
    print("  q. 退出")
    choice = input("请选择验证流程：").strip().lower()
    if choice == "q":
        return 0
    if choice not in OPTIONS:
        print("无效选项。")
        return 1

    # CharacterSelectionResult is the session context. Individual workflow
    # nodes must not rescan or prompt for a character again.
    if choice == "1":
        return verify_soul_toggle(title, selected, GameViewManager(parent.hwnd, timeout=2.0))
    return verify_item_panel_toggle(parent.hwnd, selected)


if __name__ == "__main__":
    raise SystemExit(main())
