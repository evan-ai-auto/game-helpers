"""MVP-5a validation CLI: character -> binding -> background screenshot snapshot."""

from __future__ import annotations

import argparse
import ctypes
from pathlib import Path

from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .game_state_snapshot import capture_selected_game_state


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate background game-state snapshot capture for 梦幻西游.")
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output-dir", default="diagnostic\\game_state_snapshot")
    args = parser.parse_args()

    print("[验证] 1/9 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"parent window not found: {args.title!r}")
        return 2
    print(f"parent hwnd={parent.hwnd}")

    print("[验证] 2/9 扫描 WSGAME 实例并识别已登录角色")
    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"WSGAME instances={len(scan.accounts)}")
    print(f"logged_in characters={len(accounts)}")
    if not accounts:
        print("未发现已登录角色，无法执行 MVP-5a。")
        return 3
    for option, account in enumerate(accounts, start=1):
        print(
            f"  [{option}] character={account.character_name!r} "
            f"identity={account.identity!r} view=#{account.view_index} "
            f"hwnd={account.hwnd} pid={account.process_id}"
        )

    manager = GameViewManager(parent.hwnd, timeout=2.0)
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    foreground_before = _foreground_hwnd()
    print("[验证] 3/9 记录原始 Surface、Tab 与前台")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"foreground_before={foreground_before}")

    print("[验证] 4/9 用户选择角色")
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
        f"view_index={selected.view_index} hwnd={selected.hwnd} "
        f"pid={selected.process_id} identity={selected.account.identity!r}"
    )

    result_code = 0
    try:
        print("[验证] 5/9 后台切换角色并同步 Surface + Native Tab")
        sync_selected_character(parent.hwnd, selected)
        print(f"surface_index={manager.current_surface_index()}")
        print(f"tab_index={manager.current_index()}")

        print("[验证] 6/9 验证 RenderBinding")
        print("注意：本步骤验证的是‘选中实例 ↔ 当前渲染 Surface’，不把窗口标题当作像素身份证明。")
        print("WGC 超时属于当前机器的捕获后端异常，不应被解释为任务诊断失败。")

        print("[验证] 7/9 捕获 GameStateSnapshot")
        output = Path(args.output_dir) / f"character-{selected.view_index}.png"
        snapshot = capture_selected_game_state(parent.hwnd, selected, output_path=output)
        foreground_after = _foreground_hwnd()
        print(f"snapshot_status={snapshot.status}")
        print(f"character={snapshot.character_name!r}")
        print(f"identity={snapshot.identity!r}")
        print(f"surface_index={snapshot.surface_index}")
        print(f"tab_index={snapshot.tab_index}")
        print(f"capture={snapshot.width}x{snapshot.height} backend={snapshot.backend}")
        print(f"frame_sha256={snapshot.frame_sha256}")
        print(f"screenshot={snapshot.screenshot_path}")
        print(f"foreground_unchanged={foreground_after == foreground_before}")
        verified = (
            snapshot.surface_index == selected.view_index
            and snapshot.tab_index == selected.view_index
            and foreground_after == foreground_before
            and snapshot.status == "captured"
        )
        print(f"snapshot_verified={verified}")
        if not verified:
            result_code = 6
    except Exception as exc:
        print(f"snapshot verification failed: {type(exc).__name__}: {exc}")
        result_code = 5
    finally:
        print("[验证] 8/9 恢复原始 Surface 与 Tab")
        try:
            manager.switch_surface_to(original_surface)
            manager.switch_to(original_tab)
            restored_surface = manager.current_surface_index() == original_surface
            restored_tab = manager.current_index() == original_tab
        except Exception as exc:
            print(f"restore failed: {type(exc).__name__}: {exc}")
            restored_surface = False
            restored_tab = False
        foreground_final = _foreground_hwnd()
        foreground_unchanged = foreground_final == foreground_before
        print(f"restored_surface={restored_surface}")
        print(f"restored_tab={restored_tab}")
        print(f"foreground_final={foreground_final}")
        print(f"foreground_unchanged={foreground_unchanged}")
        if not (restored_surface and restored_tab and foreground_unchanged):
            result_code = result_code or 7

    print("[验证] 9/9 结果")
    if result_code:
        print("result=FAILED")
        return result_code
    print("result=PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
