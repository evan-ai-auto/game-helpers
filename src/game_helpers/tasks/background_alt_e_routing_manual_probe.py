"""Manual probe for queued Alt+E delivery to WSGAME vs host window.

The probe compares two ordinary Win32 message-routing targets without bringing
the game to the foreground. It intentionally leaves the game's UI state as the
manual test result, while restoring Surface, native Tab, and foreground context.
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path
from ctypes import wintypes

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
    return class_name.value, title.value, int(user32.GetParent(hwnd))


def _post_alt_e(hwnd: int) -> None:
    """Queue a standard left-Alt+E system-key sequence to ``hwnd``."""
    user32 = ctypes.windll.user32
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    VK_MENU = 0x12
    VK_E = 0x45

    post = user32.PostMessageW
    post.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    post.restype = wintypes.BOOL

    def key_lparam(scan_code: int, *, context: bool = False, previous: bool = False, transition: bool = False) -> int:
        value = (scan_code & 0xFF) << 16
        if context:
            value |= 1 << 29
        if previous:
            value |= 1 << 30
        if transition:
            value |= 1 << 31
        return value

    messages = [
        (WM_SYSKEYDOWN, VK_MENU, key_lparam(0x38)),
        (WM_SYSKEYDOWN, VK_E, key_lparam(0x12, context=True)),
        (WM_SYSKEYUP, VK_E, key_lparam(0x12, context=True, previous=True, transition=True)),
        (WM_SYSKEYUP, VK_MENU, key_lparam(0x38, previous=True, transition=True)),
    ]
    for message, vk, lparam in messages:
        if not post(hwnd, message, vk, lparam):
            raise ctypes.WinError()


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

    print("\n本实验只测试一个目标窗口，避免 Alt+E 被发送两次而抵消结果。")
    print("[1] WSGAME")
    print("[2] 宿主 parent")
    try:
        target_choice = int(input("请选择消息目标 1/2：").strip())
    except (EOFError, ValueError):
        print("目标无效。")
        return 1
    if target_choice not in {1, 2}:
        print("目标无效。")
        return 1

    target_hwnd = selected.hwnd if target_choice == 1 else parent.hwnd
    class_name, title_text, direct_parent = _window_info(target_hwnd)
    print(f"target_hwnd={target_hwnd}")
    print(f"target_class={class_name!r}")
    print(f"target_title={title_text!r}")
    print(f"target_parent={direct_parent}")

    result_code = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        time.sleep(0.3)
        capture = WindowsGraphicsCapture()
        output_dir = Path("diagnostic/background_alt_e_routing_manual")
        output_dir.mkdir(parents=True, exist_ok=True)
        before_path = output_dir / f"before-character-{selected.view_index}-target-{target_choice}.png"
        after_path = output_dir / f"after-character-{selected.view_index}-target-{target_choice}.png"
        frame_before = capture.capture(parent.hwnd)
        save_png(frame_before, str(before_path))

        print("后台 PostMessageW 发送 Alt+E …")
        _post_alt_e(target_hwnd)
        time.sleep(1.0)
        frame_after = capture.capture(parent.hwnd)
        save_png(frame_after, str(after_path))

        foreground_after = _foreground_hwnd()
        print(f"foreground_after={foreground_after}")
        print(f"foreground_unchanged={foreground_after == foreground_before}")
        print(f"screenshot_before={before_path}")
        print(f"screenshot_after={after_path}")
        print("后台 Alt+E 已排队到指定 HWND。")
        print("请人工确认：道具栏是否由开变关/由关变开。")
        print("注意：本实验不把 PostMessage 成功视为游戏功能成功。")
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
