"""Control experiment: click the item icon while the game is foreground.

This deliberately gives the game foreground ownership only for the input test,
then restores the user's original foreground window. It separates coordinate/UI
correctness from the background-input problem.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character

TARGET_X_RATIO = 0.680
TARGET_Y_RATIO = 0.970


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]


INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
SW_RESTORE = 9
ATTACH_THREAD_INPUT = 0x0001


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _client_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    return int(rect.right), int(rect.bottom)


def _client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = POINT(int(x), int(y))
    if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def _cursor_pos() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def _set_foreground(hwnd: int) -> None:
    """Give a top-level window foreground ownership for this control probe.

    SetForegroundWindow can be rejected by Windows' foreground-lock rules when
    this probe is launched from PowerShell while another application owns the
    foreground. Temporarily attaching the caller and target GUI threads is the
    standard Win32 way to perform this controlled foreground hand-off.
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    current_fg = _foreground_hwnd()
    current_thread = int(user32.GetWindowThreadProcessId(current_fg, None)) if current_fg else 0
    target_thread = int(user32.GetWindowThreadProcessId(hwnd, None))
    attached = False
    if current_thread and target_thread and current_thread != target_thread:
        if not user32.AttachThreadInput(current_thread, target_thread, True):
            raise ctypes.WinError()
        attached = True
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        if not user32.SetForegroundWindow(hwnd):
            err = kernel32.GetLastError()
            raise ctypes.WinError(err)
        deadline = time.monotonic() + 2.0
        while _foreground_hwnd() != hwnd and time.monotonic() < deadline:
            time.sleep(0.02)
        if _foreground_hwnd() != hwnd:
            raise RuntimeError(f"failed to make foreground: hwnd={hwnd}, current={_foreground_hwnd()}")
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def _send_mouse_click(screen_x: int, screen_y: int) -> None:
    user32 = ctypes.windll.user32
    if not user32.SetCursorPos(int(screen_x), int(screen_y)):
        raise ctypes.WinError()

    inputs = (INPUT * 2)()
    inputs[0].type = INPUT_MOUSE
    inputs[0].mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)
    inputs[1].type = INPUT_MOUSE
    inputs[1].mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None)
    sent = user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    if sent != 2:
        raise ctypes.WinError()
    print(f"sendinput_mouse_events_sent={sent}")


def _restore_foreground(hwnd: int) -> None:
    if not hwnd:
        return
    try:
        _set_foreground(hwnd)
    except Exception as exc:
        print(f"foreground_restore_error={exc}")


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
    result = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(result)
    print(f"parent hwnd={parent.hwnd}")
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
    original_foreground = _foreground_hwnd()
    original_cursor = _cursor_pos()

    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"original_foreground={original_foreground}")
    print(f"original_cursor={original_cursor}")
    print("\n控制实验：暂时让游戏获得前台输入焦点，再用真实系统鼠标输入点击道具图标。")
    print("这不是后台方案；目的只是验证坐标/UI本身是否正确。")

    result_code = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        time.sleep(0.3)
        width, height = _client_size(selected.hwnd)
        client_x = round(width * TARGET_X_RATIO)
        client_y = round(height * TARGET_Y_RATIO)
        screen_x, screen_y = _client_to_screen(selected.hwnd, client_x, client_y)
        print(f"selected_client_size=({width},{height})")
        print(f"target_client=({client_x},{client_y})")
        print(f"target_screen=({screen_x},{screen_y})")

        capture = WindowsGraphicsCapture()
        output_dir = Path("diagnostic/foreground_item_click_manual")
        output_dir.mkdir(parents=True, exist_ok=True)
        before_path = output_dir / f"before-character-{selected.view_index}.png"
        after_path = output_dir / f"after-character-{selected.view_index}.png"
        save_png(capture.capture(parent.hwnd), str(before_path))

        print("正在将游戏临时切到前台……")
        _set_foreground(parent.hwnd)
        print(f"foreground_during_test={_foreground_hwnd()}")
        time.sleep(0.3)
        print("真实系统鼠标点击执行中……")
        _send_mouse_click(screen_x, screen_y)
        time.sleep(1.0)
        save_png(capture.capture(parent.hwnd), str(after_path))
        print(f"foreground_after_click={_foreground_hwnd()}")
        print(f"screenshot_before={before_path}")
        print(f"screenshot_after={after_path}")
        print("请人工确认：道具栏是否打开。")
        result_code = 0
    except Exception as exc:
        print(f"probe_error={exc}")
    finally:
        try:
            _restore_context(manager, original_surface, original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
            result_code = 1
        ctypes.windll.user32.SetCursorPos(*original_cursor)
        _restore_foreground(original_foreground)
        foreground_final = _foreground_hwnd()
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_final={foreground_final}")
        print(f"foreground_unchanged={foreground_final == original_foreground}")
        print(f"cursor_restored={_cursor_pos() == original_cursor}")

    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
