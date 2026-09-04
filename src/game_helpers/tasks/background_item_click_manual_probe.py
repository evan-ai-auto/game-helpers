"""Manual probe for clicking the in-game item-bar icon in the background.

This probe intentionally tests the mouse path rather than Alt+E. The target is
based on the normalized location of the larger "道具 (Alt+E)" toolbar icon seen
in the supplied game screenshots. The probe does not activate the game and
restores Surface/native Tab afterwards.
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


# The supplied screenshots show the larger 道具 toolbar icon around this
# normalized client location. Normalization tolerates small size differences.
TARGET_X_RATIO = 0.680
TARGET_Y_RATIO = 0.970


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


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


def _client_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    return int(rect.right - rect.left), int(rect.bottom - rect.top)


def _client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = POINT(int(x), int(y))
    if not ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def _window_from_point(x: int, y: int) -> int:
    point = POINT(int(x), int(y))
    return int(ctypes.windll.user32.WindowFromPoint(point))


def _root_ancestor(hwnd: int) -> int:
    return int(ctypes.windll.user32.GetAncestor(hwnd, 2))


def _ancestor_chain(hwnd: int, limit: int = 8) -> list[int]:
    user32 = ctypes.windll.user32
    result: list[int] = []
    current = int(hwnd)
    while current and len(result) < limit:
        result.append(current)
        current = int(user32.GetParent(current))
    return result


def _print_window(label: str, hwnd: int) -> None:
    if not hwnd:
        print(f"{label}=0")
        return
    class_name, title, parent = _window_info(hwnd)
    root = _root_ancestor(hwnd)
    print(f"{label}={hwnd} class={class_name!r} title={title!r} parent={parent} root={root}")


def _screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = POINT(int(x), int(y))
    if not ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


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
    _print_window("parent_info", parent.hwnd)

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
    _print_window("selected_info", selected.hwnd)
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"foreground_before={foreground_before}")
    print("\n目标：底部快捷栏较大的「道具 (Alt+E)」图标。")
    print(f"target_ratio=({TARGET_X_RATIO:.3f},{TARGET_Y_RATIO:.3f})")
    print("本实验只发送后台鼠标消息，不激活游戏；请确保其他应用/电影保持前台。")

    result_code = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        time.sleep(0.3)

        width, height = _client_size(selected.hwnd)
        target_client_x = round(width * TARGET_X_RATIO)
        target_client_y = round(height * TARGET_Y_RATIO)
        target_screen_x, target_screen_y = _client_to_screen(selected.hwnd, target_client_x, target_client_y)
        hit_hwnd = _window_from_point(target_screen_x, target_screen_y)

        print(f"selected_client_size=({width},{height})")
        print(f"target_client=({target_client_x},{target_client_y})")
        print(f"target_screen=({target_screen_x},{target_screen_y})")
        _print_window("hit_test", hit_hwnd)
        print(f"hit_root_is_parent={_root_ancestor(hit_hwnd) == parent.hwnd if hit_hwnd else False}")
        print(f"hit_is_selected={hit_hwnd == selected.hwnd}")
        print("hit_ancestor_chain:")
        for index, hwnd in enumerate(_ancestor_chain(hit_hwnd), 1):
            class_name, title_text, direct_parent = _window_info(hwnd)
            print(f"  [{index}] hwnd={hwnd} class={class_name!r} title={title_text!r} parent={direct_parent}")

        capture = WindowsGraphicsCapture()
        output_dir = Path("diagnostic/background_item_click_manual")
        output_dir.mkdir(parents=True, exist_ok=True)
        before_path = output_dir / f"before-character-{selected.view_index}.png"
        after_path = output_dir / f"after-character-{selected.view_index}.png"
        frame_before = capture.capture(parent.hwnd)
        save_png(frame_before, str(before_path))

        # WindowFromPoint is only meaningful for the currently visible screen
        # surface. When the game is deliberately backgrounded, the same screen
        # coordinate may belong to the foreground application. The target is
        # nevertheless a known point inside the selected WSGAME client, so for
        # this diagnostic we intentionally route the click to WSGAME itself.
        hit_client_x, hit_client_y = _screen_to_client(selected.hwnd, target_screen_x, target_screen_y)
        print(f"click_target_hwnd={selected.hwnd} (WSGAME)")
        print(f"click_target_client=({hit_client_x},{hit_client_y})")
        print("后台点击道具图标执行中……")
        BackgroundInput(selected.hwnd).click_sync(hit_client_x, hit_client_y)
        time.sleep(1.0)

        foreground_after = _foreground_hwnd()
        frame_after = capture.capture(parent.hwnd)
        save_png(frame_after, str(after_path))

        print(f"foreground_after={foreground_after}")
        print(f"foreground_unchanged={foreground_after == foreground_before}")
        print(f"screenshot_before={before_path}")
        print(f"screenshot_after={after_path}")
        print("请人工确认：道具栏是否由关变开（或由开变关）。")
        print("注意：本次验证刻意不使用 WindowFromPoint 的前台命中结果，而直接向后台 WSGAME 发送点击。")
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
