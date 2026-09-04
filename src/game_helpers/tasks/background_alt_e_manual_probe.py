"""Local manual probe for background Alt+E keyboard delivery.

This probe does not restore the game's UI state after Alt+E because the purpose
is visual/manual verification. It always restores the selected game surface,
native tab selection, and the user's foreground window context.
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _window_info(hwnd: int) -> tuple[str, str, int]:
    user32 = ctypes.windll.user32
    title_length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(title_length + 1)
    user32.GetWindowTextW(hwnd, title, title_length + 1)
    class_name = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_name, len(class_name))
    parent = int(user32.GetParent(hwnd))
    return class_name.value, title.value, parent


def _restore_context(manager: GameViewManager, original_surface: int | None, original_tab: int | None) -> None:
    if original_surface is not None:
        manager.switch_surface_to(original_surface)
    if original_tab is not None:
        manager.switch_to(original_tab)


def main() -> int:
    if sys.platform != "win32":
        print("本探针仅支持 Windows。")
        return 2

    title = sys.argv[1] if len(sys.argv) > 1 else "梦幻西游 ONLINE"
    parent = find_window(title)
    if parent is None:
        print(f"parent window not found: {title!r}")
        return 2

    manager = GameViewManager(parent.hwnd, timeout=2.0)
    print(f"parent hwnd={parent.hwnd}")
    result = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(result)
    print(f"logged_in characters={len(accounts)}")
    for i, account in enumerate(accounts, 1):
        print(f"  [{i}] character='{account.character_name}' identity='{account.identity}' view=#{account.view_index}")
    if not accounts:
        return 1

    try:
        choice = int(input("\n请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 1
    if not 1 <= choice <= len(accounts):
        print("角色编号无效。")
        return 1

    selected = select_character(result, accounts[choice - 1].view_index)
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    foreground_before = _foreground_hwnd()
    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"foreground_before={foreground_before}")
    class_name, title_text, parent_hwnd = _window_info(selected.hwnd)
    print(f"target_hwnd={selected.hwnd} class={class_name!r} title={title_text!r} parent={parent_hwnd}")

    result_code = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        time.sleep(0.3)
        capture = WindowsGraphicsCapture()
        output_dir = Path("diagnostic/background_alt_e_manual")
        output_dir.mkdir(parents=True, exist_ok=True)
        frame_before = capture.capture(parent.hwnd)
        save_png(frame_before, str(output_dir / f"before-character-{selected.view_index}.png"))

        print("后台发送 Alt+E …")
        BackgroundInput(selected.hwnd).alt_e_sync()
        time.sleep(0.8)
        frame_after = capture.capture(parent.hwnd)
        save_png(frame_after, str(output_dir / f"after-character-{selected.view_index}.png"))
        foreground_after = _foreground_hwnd()
        print(f"foreground_after={foreground_after}")
        print(f"foreground_unchanged={foreground_after == foreground_before}")
        print(f"screenshot_after={output_dir / f'after-character-{selected.view_index}.png'}")
        print("后台 Alt+E 消息已发送。")
        print("请人工确认：游戏道具栏是否打开/关闭。")
        print("注意：消息发送成功不等于游戏一定处理了快捷键。")
        result_code = 0
    finally:
        restore_error = None
        try:
            _restore_context(manager, original_surface, original_tab)
        except Exception as exc:
            restore_error = exc
            result_code = 1
        foreground_final = _foreground_hwnd()
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_final={foreground_final}")
        print(f"foreground_unchanged={foreground_final == foreground_before}")
        if restore_error is not None:
            print(f"restore_error={restore_error}")
        print("道具栏状态：保留测试后的状态，不自动恢复。")

    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
