"""Foreground control probe using a manually recorded hover coordinate.

The user first moves the real mouse over the item icon until the game shows
"道具 (Alt+E)", then presses F8 without moving the mouse. The exact cursor
position that produced the visible tooltip is reused for the foreground click.

This avoids guessing the icon center or mixing screen coordinates with capture
pixels. If this click opens the item panel, the coordinate is proven correct
and the remaining problem is background input delivery.
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

VK_F8 = 0x77
VK_ESCAPE = 0x1B
SW_RESTORE = 9


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


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _cursor_pos() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def _client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = POINT(int(x), int(y))
    if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def _screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = POINT(int(x), int(y))
    if not ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def _client_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    return int(rect.right), int(rect.bottom)


def _window_text(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    length = int(user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def _parent(hwnd: int) -> int:
    return int(ctypes.windll.user32.GetParent(hwnd))


def _root(hwnd: int) -> int:
    return int(ctypes.windll.user32.GetAncestor(hwnd, 2))


def _set_foreground(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    current = _foreground_hwnd()
    current_thread = int(user32.GetWindowThreadProcessId(current, None)) if current else 0
    target_thread = int(user32.GetWindowThreadProcessId(hwnd, None))
    attached = False
    if current_thread and target_thread and current_thread != target_thread:
        if not user32.AttachThreadInput(current_thread, target_thread, True):
            raise ctypes.WinError()
        attached = True
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        deadline = time.monotonic() + 2.0
        while _foreground_hwnd() != hwnd and time.monotonic() < deadline:
            time.sleep(0.02)
        if _foreground_hwnd() != hwnd:
            raise RuntimeError(
                f"failed to make foreground: hwnd={hwnd}, current={_foreground_hwnd()}"
            )
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def _send_mouse_click(screen_x: int, screen_y: int) -> int:
    user32 = ctypes.windll.user32
    if not user32.SetCursorPos(int(screen_x), int(screen_y)):
        raise ctypes.WinError()

    inputs = (INPUT * 2)()
    inputs[0].type = INPUT_MOUSE
    inputs[0].mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)
    inputs[1].type = INPUT_MOUSE
    inputs[1].mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None)
    sent = int(user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT)))
    if sent != 2:
        raise ctypes.WinError()
    return sent


def _wait_for_key_release(vk: int) -> None:
    user32 = ctypes.windll.user32
    while user32.GetAsyncKeyState(vk) & 0x8000:
        time.sleep(0.03)


def _wait_for_f8() -> bool:
    user32 = ctypes.windll.user32
    while True:
        if user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001:
            return False
        if user32.GetAsyncKeyState(VK_F8) & 0x0001:
            _wait_for_key_release(VK_F8)
            return True
        time.sleep(0.03)


def _describe_hit(screen_x: int, screen_y: int) -> int:
    user32 = ctypes.windll.user32
    hit = int(user32.WindowFromPoint(POINT(screen_x, screen_y)))
    print(
        f"hit_test=hwnd={hit} class='{_window_class(hit)}' "
        f"title='{_window_text(hit)}' parent={_parent(hit)} root={_root(hit)}"
    )
    return hit


def _restore_context(manager: GameViewManager, surface: int | None, tab: int | None) -> None:
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
    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"parent hwnd={parent.hwnd}")
    for i, account in enumerate(accounts, 1):
        print(
            f"  [{i}] character='{account.character_name}' "
            f"identity='{account.identity}' view=#{account.view_index}"
        )
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

    selected = select_character(scan, accounts[choice - 1].view_index)
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    original_foreground = _foreground_hwnd()
    original_cursor = _cursor_pos()

    print(
        f"selected character='{selected.character_name}' "
        f"view_index={selected.view_index} hwnd={selected.hwnd}"
    )
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"original_foreground={original_foreground}")
    print(f"original_cursor={original_cursor}")
    print("\n本实验先人工记录真正触发 tooltip 的鼠标位置，再使用同一个位置点击。")
    print("控制实验：游戏暂时前台；不是后台方案。")
    print("请把其他窗口准备好，程序会在记录后自动点击，并最终恢复原状态。")

    result_code = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        capture = WindowsGraphicsCapture()
        output_dir = Path("diagnostic/foreground_item_click_at_hover")
        output_dir.mkdir(parents=True, exist_ok=True)

        before_path = output_dir / f"before-character-{selected.view_index}.png"
        hover_path = output_dir / f"hover-character-{selected.view_index}.png"
        after_path = output_dir / f"after-character-{selected.view_index}.png"

        save_png(capture.capture(parent.hwnd), str(before_path))
        _set_foreground(parent.hwnd)
        print(f"foreground_during_test={_foreground_hwnd()}")
        time.sleep(0.3)

        print("\n现在请手动把真实鼠标移动到‘道具’图标。")
        print("等‘道具 (Alt+E)’ tooltip 已经明确显示后，保持鼠标不动，按 F8。")
        print("如果没有显示 tooltip，不要按 F8；可继续移动。按 ESC 取消。")

        if not _wait_for_f8():
            print("收到 ESC，取消点击实验。")
            return 0

        screen_x, screen_y = _cursor_pos()
        client_x, client_y = _screen_to_client(selected.hwnd, screen_x, screen_y)
        client_w, client_h = _client_size(selected.hwnd)
        hit = _describe_hit(screen_x, screen_y)

        print("\nMANUAL_HOVER_MARK")
        print(f"cursor_screen=({screen_x},{screen_y})")
        print(f"selected_client=({client_x},{client_y})")
        print(f"selected_client_size=({client_w},{client_h})")
        print(f"selected_ratio=({client_x / client_w:.6f},{client_y / client_h:.6f})")
        print(f"hit_is_selected={hit == selected.hwnd}")
        print(f"target_screen=({screen_x},{screen_y})")
        print("注意：这里完全不根据截图像素猜中心点，直接复用刚才人工触发 tooltip 的屏幕坐标。")

        save_png(capture.capture(parent.hwnd), str(hover_path))
        print(f"screenshot_hover={hover_path}")
        print("准备点击同一个坐标。请观察道具栏是否打开。")
        time.sleep(0.3)
        sent = _send_mouse_click(screen_x, screen_y)
        print(f"sendinput_mouse_events_sent={sent}")
        time.sleep(1.0)
        print(f"foreground_after_click={_foreground_hwnd()}")
        save_png(capture.capture(parent.hwnd), str(after_path))
        print(f"screenshot_before={before_path}")
        print(f"screenshot_after={after_path}")
        print("请人工确认：道具栏是否由关变开（或由开变关）。")
        result_code = 0
    except Exception as exc:
        print(f"probe_error={exc}")
    finally:
        try:
            _restore_context(manager, original_surface, original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
            result_code = 1
        try:
            if original_cursor:
                ctypes.windll.user32.SetCursorPos(*original_cursor)
        except Exception as exc:
            print(f"cursor_restore_error={exc}")
            result_code = 1
        try:
            if original_foreground:
                _set_foreground(original_foreground)
        except Exception as exc:
            print(f"foreground_restore_error={exc}")
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        foreground_final = _foreground_hwnd()
        print(f"foreground_final={foreground_final}")
        print(f"foreground_unchanged={foreground_final == original_foreground}")
        print(f"cursor_restored={_cursor_pos() == original_cursor}")

    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
