"""Probe whether background WSGAME click is queued and only rendered later.

The previous experiment showed that a PostMessageW click did not visibly open
the item panel while the game stayed in the background, but the panel was
found open after the user later switched the game window to the foreground.
This probe measures that distinction explicitly without adding any new input
mechanism.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character

VK_F8 = 0x77
VK_ESCAPE = 0x1B


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def foreground() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def cursor_pos() -> tuple[int, int]:
    p = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(p)):
        raise ctypes.WinError()
    return int(p.x), int(p.y)


def screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    p = POINT(x, y)
    if not ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(p)):
        raise ctypes.WinError()
    return int(p.x), int(p.y)


def set_foreground(hwnd: int, timeout: float = 2.0) -> None:
    user32 = ctypes.windll.user32
    current = foreground()
    if current == hwnd:
        return
    current_thread = int(user32.GetWindowThreadProcessId(current, None)) if current else 0
    target_thread = int(user32.GetWindowThreadProcessId(hwnd, None))
    attached = False
    try:
        if current_thread and target_thread and current_thread != target_thread:
            if not user32.AttachThreadInput(current_thread, target_thread, True):
                raise ctypes.WinError()
            attached = True
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        deadline = time.monotonic() + timeout
        while foreground() != hwnd and time.monotonic() < deadline:
            time.sleep(0.02)
        if foreground() != hwnd:
            raise RuntimeError(f"failed to set foreground: expected={hwnd} actual={foreground()}")
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def restore_foreground(hwnd: int) -> bool:
    set_foreground(hwnd)
    return foreground() == hwnd


def wait_f8() -> bool:
    user32 = ctypes.windll.user32
    while True:
        if user32.GetAsyncKeyState(VK_ESCAPE) & 1:
            return False
        if user32.GetAsyncKeyState(VK_F8) & 1:
            while user32.GetAsyncKeyState(VK_F8) & 0x8000:
                time.sleep(0.03)
            return True
        time.sleep(0.03)


def restore_context(manager: GameViewManager, surface: int | None, tab: int | None) -> None:
    if surface is not None:
        manager.switch_surface_to(surface)
    if tab is not None:
        manager.switch_to(tab)


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
    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    for i, account in enumerate(accounts, 1):
        print(f"  [{i}] character='{account.character_name}' identity='{account.identity}' view=#{account.view_index}")
    if not accounts:
        return 1

    try:
        choice = int(input("\n请选择角色编号：").strip())
    except (EOFError, ValueError):
        return 1
    if not 1 <= choice <= len(accounts):
        return 1

    selected = select_character(scan, accounts[choice - 1].view_index)
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    original_foreground = foreground()
    original_cursor = cursor_pos()

    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"original_foreground={original_foreground}")

    result = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        capture = WindowsGraphicsCapture()
        out = Path("diagnostic/background_item_click_pending_state")
        out.mkdir(parents=True, exist_ok=True)
        before = out / f"before-character-{selected.view_index}.png"
        during = out / f"during-background-character-{selected.view_index}.png"
        after_foreground = out / f"after-foreground-character-{selected.view_index}.png"
        save_png(capture.capture(parent.hwnd), str(before))

        set_foreground(parent.hwnd)
        print(f"foreground_during_coordinate_capture={foreground()}")
        print("\n请手动移动鼠标到‘道具’图标，等‘道具 (Alt+E)’ tooltip 出现后按 F8。")
        if not wait_f8():
            print("收到 ESC，取消。")
            return 0

        screen = cursor_pos()
        client = screen_to_client(selected.hwnd, *screen)
        print(f"manual_hover_screen={screen}")
        print(f"manual_hover_client={client}")

        if not restore_foreground(original_foreground):
            raise RuntimeError(f"failed to restore original foreground before click: {foreground()}")
        print(f"foreground_before_background_click={foreground()}")

        print("发送后台 PostMessageW 点击，然后保持游戏后台。")
        BackgroundInput(selected.hwnd).click(*client)
        time.sleep(1.5)
        print(f"foreground_after_background_click={foreground()}")
        save_png(capture.capture(parent.hwnd), str(during))
        print(f"screenshot_background_state={during}")
        print("\n现在不要立即手动点击游戏，请按一次 ENTER 让程序把游戏临时切到前台。")
        input()
        set_foreground(parent.hwnd)
        time.sleep(1.0)
        print(f"foreground_after_manual_reveal={foreground()}")
        save_png(capture.capture(parent.hwnd), str(after_foreground))
        print(f"screenshot_after_foreground={after_foreground}")
        print("请人工确认：")
        print("1) 游戏保持后台时，道具栏是否已经打开；")
        print("2) 切回游戏前台后，道具栏是否突然出现。")
        result = 0
    except Exception as exc:
        print(f"probe_error={exc}")
    finally:
        try:
            restore_context(manager, original_surface, original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
            result = 1
        try:
            fg_ok = restore_foreground(original_foreground)
        except Exception as exc:
            print(f"foreground_restore_error={exc}")
            fg_ok = False
            result = 1
        try:
            ctypes.windll.user32.SetCursorPos(*original_cursor)
            cursor_ok = cursor_pos() == original_cursor
        except Exception as exc:
            print(f"cursor_restore_error={exc}")
            cursor_ok = False
            result = 1
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_restore_ok={fg_ok}")
        print(f"foreground_final={foreground()}")
        print(f"foreground_unchanged={foreground() == original_foreground}")
        print(f"cursor_restored={cursor_ok}")
        print("道具栏状态：保留测试后的状态，不自动恢复。")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
