"""Manual probe for recording the real screen/client coordinate of a hovered UI item.

The probe does not click or send keyboard/mouse messages to the game. It selects a
character, temporarily makes the game foreground, then lets the user move the
real mouse over a UI element. Press F8 while the tooltip is visible to record the
current cursor position, WSGAME client coordinates, hit-test HWND and ancestor
chain, plus a screenshot.
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
SW_RESTORE = 9
GA_PARENT = 1
GA_ROOT = 2


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _cursor_pos() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def _screen_to_client(hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
    point = POINT(screen_x, screen_y)
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
    user32 = ctypes.windll.user32
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def _parent(hwnd: int) -> int:
    return int(ctypes.windll.user32.GetParent(hwnd))


def _root(hwnd: int) -> int:
    return int(ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT))


def _ancestor_chain(hwnd: int, limit: int = 8) -> list[int]:
    chain: list[int] = []
    current = int(hwnd)
    while current and len(chain) < limit:
        chain.append(current)
        current = _parent(current)
    return chain


def _describe(hwnd: int) -> str:
    return (
        f"hwnd={hwnd} class='{_window_class(hwnd)}' title='{_window_text(hwnd)}' "
        f"parent={_parent(hwnd)} root={_root(hwnd)}"
    )


def _set_foreground(hwnd: int) -> None:
    user32 = ctypes.windll.user32
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
        user32.SetForegroundWindow(hwnd)
        deadline = time.monotonic() + 2.0
        while _foreground_hwnd() != hwnd and time.monotonic() < deadline:
            time.sleep(0.02)
        if _foreground_hwnd() != hwnd:
            raise RuntimeError(f"failed to make foreground: hwnd={hwnd}, current={_foreground_hwnd()}")
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def _wait_for_f8_release() -> None:
    user32 = ctypes.windll.user32
    while user32.GetAsyncKeyState(VK_F8) & 0x8000:
        time.sleep(0.03)


def _f8_pressed() -> bool:
    return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F8) & 0x0001)


def _record_mark(capture: WindowsGraphicsCapture, parent_hwnd: int, selected_hwnd: int, output_dir: Path, index: int) -> None:
    screen_x, screen_y = _cursor_pos()
    client_x, client_y = _screen_to_client(selected_hwnd, screen_x, screen_y)
    width, height = _client_size(selected_hwnd)
    hit = int(ctypes.windll.user32.WindowFromPoint(POINT(screen_x, screen_y)))

    print(f"\nMARK #{index}")
    print(f"cursor_screen=({screen_x},{screen_y})")
    print(f"selected_client=({client_x},{client_y})")
    print(f"selected_client_size=({width},{height})")
    print(f"selected_ratio=({client_x / width:.6f},{client_y / height:.6f})")
    print(f"hit_test={_describe(hit)}")
    print(f"hit_root_is_game_parent={_root(hit) == parent_hwnd}")
    print(f"hit_is_selected={hit == selected_hwnd}")
    print("hit_ancestor_chain:")
    for level, hwnd in enumerate(_ancestor_chain(hit), 1):
        print(f"  [{level}] {_describe(hwnd)}")

    path = output_dir / f"mark-{index:02d}-screen-{screen_x}-{screen_y}.png"
    save_png(capture.capture(parent_hwnd), str(path))
    print(f"screenshot={path}")


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
    output_dir = Path("diagnostic/manual_hover_coordinate")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"original_foreground={original_foreground}")
    print("\n本探针不会点击游戏，也不会发送后台鼠标消息。")
    print("程序会暂时让游戏前台，然后请你用真实鼠标移动到目标图标。")
    print("当目标 tooltip 已经显示时，按一次 F8，程序会记录当前鼠标屏幕坐标、WSGAME client 坐标、命中 HWND 和父链。")
    print("可以连续记录多个位置；按 ESC 退出。")

    result_code = 0
    try:
        sync_selected_character(parent.hwnd, selected)
        capture = WindowsGraphicsCapture()
        _set_foreground(parent.hwnd)
        print(f"foreground_during_probe={_foreground_hwnd()}")
        print("现在请手动移动鼠标到‘道具’图标，等‘道具 (Alt+E)’ tooltip 出现后按 F8。")

        mark_index = 0
        user32 = ctypes.windll.user32
        while True:
            if user32.GetAsyncKeyState(0x1B) & 0x0001:  # ESC
                print("收到 ESC，结束探针。")
                break
            if _f8_pressed():
                mark_index += 1
                _record_mark(capture, parent.hwnd, selected.hwnd, output_dir, mark_index)
                _wait_for_f8_release()
                print("继续移动鼠标；再次看到 tooltip 时可再次按 F8。")
            time.sleep(0.03)
    except Exception as exc:
        print(f"probe_error={exc}")
        result_code = 1
    finally:
        try:
            if original_surface is not None:
                manager.switch_surface_to(original_surface)
            if original_tab is not None:
                manager.switch_to(original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
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

    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
