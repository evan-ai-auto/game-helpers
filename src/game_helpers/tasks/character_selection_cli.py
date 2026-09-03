"""Interactive CLI for selecting a logged-in 梦幻西游 character instance."""

from __future__ import annotations

import argparse

from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select a logged-in 梦幻西游 character without taking the foreground."
    )
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    args = parser.parse_args()

    print("[验证] 1/8 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"parent window not found: {args.title!r}")
        return 2
    print(f"parent hwnd={parent.hwnd}")

    print("[验证] 2/8 扫描 WSGAME 实例")
    result = scan_game_accounts(parent.hwnd)
    print(f"WSGAME instances={len(result.accounts)}")

    print("[验证] 3/8 筛选已登录角色")
    accounts = logged_in_accounts(result)
    print(f"logged_in characters={len(accounts)}")
    if not accounts:
        print("未发现已登录角色，验证结束。")
        return 3

    for option, account in enumerate(accounts, start=1):
        print(
            f"  [{option}] character={account.character_name!r} "
            f"identity={account.identity!r} view=#{account.view_index} "
            f"hwnd={account.hwnd} pid={account.process_id}"
        )

    print("[验证] 4/8 用户选择角色")
    try:
        choice = int(input("请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 4
    if not 1 <= choice <= len(accounts):
        print(f"角色编号必须在 1 到 {len(accounts)} 之间。")
        return 4

    selected = select_character(result, accounts[choice - 1].view_index)
    print(
        f"selected character={selected.character_name!r} "
        f"view_index={selected.view_index} hwnd={selected.hwnd} "
        f"pid={selected.process_id} identity={selected.account.identity!r}"
    )

    print("[验证] 5/8 后台切换 Surface")
    print("[验证] 6/8 同步 Native Tab，并验证前台不变")
    try:
        sync_selected_character(parent.hwnd, selected)
    except Exception as exc:
        print(f"selection verification failed: {type(exc).__name__}: {exc}")
        return 5

    from ..core.view_manager import GameViewManager

    manager = GameViewManager(parent.hwnd, timeout=2.0)
    surface = manager.current_surface_index()
    tab = manager.current_index()
    print(f"surface_index={surface}")
    print(f"tab_index={tab}")
    print("foreground_unchanged=True")
    print("selection_verified=" + str(surface == selected.view_index and tab == selected.view_index))

    print("[验证] 7/8 角色选择完成（不执行任何任务操作）")
    print("[验证] 8/8 结果")
    if surface != selected.view_index or tab != selected.view_index:
        print("result=FAILED")
        return 6
    print("result=PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
