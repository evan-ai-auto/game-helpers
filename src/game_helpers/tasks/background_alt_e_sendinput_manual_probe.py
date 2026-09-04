"""Manual probe for system-level SendInput Alt+E while the game stays background."""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path
from ctypes import wintypes

from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
VK_MENU = 0x12
SCANCODE_LALT = 0x38
SCANCODE_E = 0x12


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


def _sendinput_alt_e() -> int:
    """Inject left-Alt+E into the system input stream."""
    user32 = ctypes.windll.user32
    send_input = user32.SendInput
    send_input.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    send_input.restype = wintypes.UINT

    events = (INPUT * 4)()
    events[0].type = INPUT_KEYBOARD
    events[0].ki = KEYBDINPUT(VK_MENU, SCANCODE_LALT, KEYEVENTF_SCANCODE, 0, 0)
    events[1].type = INPUT_KEYBOARD
    events[1].ki = KEYBDINPUT(0, SCANCODE_E, KEYEVENTF_SCANCODE, 0, 0)
    events[2].type = INPUT_KEYBOARD
    events[2].ki = KEYBDINPUT(0, SCANCODE_E, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0)
    events[3].type = INPUT_KEYBOARD
    events[3].ki = KEYBDINPUT(VK_MENU, SCANCODE_LALT, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0)

    sent = int(send_input(len(events), events, ctypes.sizeof(INPUT)))
    if sent != len(events):
        raise ctypes.WinError(ctypes.get_last_error())
    return sent


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
    class_name, title_text, direct_parent = _window_info(selected.hwnd)
    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"target_class={class_name!r}")
    print(f"target_title={title_text!r}")
    print(f"target_parent={direct_parent}")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"foreground_before={foreground_before}")
    print("\n核心假设：SendInput 走系统当前输入目标，无法把真实键盘 Alt+E 定向给后台 WSGAME。")
    print("本实验不会激活游戏；请确保前台仍是其他应用/电影窗口。")

    result_code = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        time.sleep(0.3)
        capture = WindowsGraphicsCapture()
        output_dir = Path("diagnostic/background_alt_e_sendinput_manual")
        output_dir.mkdir(parents=True, exist_ok=True)
        before_path = output_dir / f"before-character-{selected.view_index}.png"
        after_path = output_dir / f"after-character-{selected.view_index}.png"
        frame_before = capture.capture(parent.hwnd)
        save_png(frame_before, str(before_path))

        print("\n后台场景下 SendInput 发送 Alt+E …")
        sent = _sendinput_alt_e()
        print(f"sendinput_events_sent={sent}")
        time.sleep(1.0)
        frame_after = capture.capture(parent.hwnd)
        save_png(frame_after, str(after_path))

        foreground_after = _foreground_hwnd()
        print(f"foreground_after={foreground_after}")
        print(f"foreground_unchanged={foreground_after == foreground_before}")
        print(f"screenshot_before={before_path}")
        print(f"screenshot_after={after_path}")
        print("请人工确认：游戏道具栏是否由开变关/由关变开。")
        print("注意：SendInput 返回 4 只代表系统接受了 4 个输入事件，不代表游戏接受了 Alt+E。")
        print("若道具栏没有变化，则确认 SendInput 也不能作为真正的后台 Alt+E 通道。")
        result_code = 0
    except Exception as exc:
        print(f"probe_error={exc}")
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
