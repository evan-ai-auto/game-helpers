"""Background click probe using a manually confirmed tooltip coordinate.

The user first moves the real mouse over the in-game item icon while the game
is foreground and presses F8 only after the "道具 (Alt+E)" tooltip is visible.
The probe then converts that exact screen coordinate to WSGAME client
coordinates and sends the click to the background WSGAME window without
activating it.

This isolates two questions:
1. Is the coordinate itself correct? (proved by the foreground control probe.)
2. Can the game accept a background mouse message at that exact coordinate?
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


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _cursor_pos() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
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


def _window_from_point(x: int, y: int) -> int:
    return int(ctypes.windll.user32.WindowFromPoint(POINT(int(x), int(y))))


def _ancestor_chain(hwnd: int, limit: int = 8) -> list[int]:
    result: list[int] = []
    current = int(hwnd)
    while current and len(result) < limit:
        result.append(current)
        current = _parent(current)
    return result


def _print_window(label: str, hwnd: int) -> None:
    if not hwnd:
        print(f"{label}=0")
        return
    print(
        f"{label}={hwnd} class='{_window_class(hwnd)}' title='{_window_text(hwnd)}' "
        f"parent={_parent(hwnd)} root={_root(hwnd)}"
    )


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
    print(f"parent hwnd={parent.hwnd}")

    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
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
    foreground_before = _foreground_hwnd()

    print(
        f"selected character='{selected.character_name}' "
        f"view_index={selected.view_index} hwnd={selected.hwnd}"
    )
    _print_window("selected_info", selected.hwnd)
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"original_foreground={foreground_before}")
    print("\n本实验先人工记录真正触发 tooltip 的鼠标位置，再把同一个位置换成后台 WSGAME 点击。")
    print("这次不再猜图标中心坐标；坐标来自你刚刚已经验证成功的真实鼠标位置。")
    print("本实验不会激活游戏；记录完成后会立即恢复其他窗口到前台。")

    result_code = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        capture = WindowsGraphicsCapture()
        output_dir = Path("diagnostic/background_item_click_at_hover_manual")
        output_dir.mkdir(parents=True, exist_ok=True)
        before_path = output_dir / f"before-character-{selected.view_index}.png"
        hover_path = output_dir / f"hover-character-{selected.view_index}.png"
        after_path = output_dir / f"after-character-{selected.view_index}.png"

        save_png(capture.capture(parent.hwnd), str(before_path))

        # Foreground is required only for the manual coordinate acquisition.
        user32 = ctypes.windll.user32
        current = _foreground_hwnd()
        current_thread = int(user32.GetWindowThreadProcessId(current, None)) if current else 0
        target_thread = int(user32.GetWindowThreadProcessId(parent.hwnd, None))
        attached = False
        try:
            if current_thread and target_thread and current_thread != target_thread:
                if not user32.AttachThreadInput(current_thread, target_thread, True):
                    raise ctypes.WinError()
                attached = True
            user32.BringWindowToTop(parent.hwnd)
            user32.SetForegroundWindow(parent.hwnd)
            deadline = time.monotonic() + 2.0
            while _foreground_hwnd() != parent.hwnd and time.monotonic() < deadline:
                time.sleep(0.02)
            if _foreground_hwnd() != parent.hwnd:
                raise RuntimeError(
                    f"failed to make game foreground: current={_foreground_hwnd()} target={parent.hwnd}"
                )
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, target_thread, False)

        print(f"foreground_during_coordinate_capture={_foreground_hwnd()}")
        print("\n请手动把真实鼠标移动到‘道具’图标。")
        print("等‘道具 (Alt+E)’ tooltip 已经明确显示后，保持鼠标不动，按 F8。")
        print("按 ESC 取消。")
        if not _wait_for_f8():
            print("收到 ESC，取消实验。")
            return 0

        screen_x, screen_y = _cursor_pos()
        client_x, client_y = _screen_to_client(selected.hwnd, screen_x, screen_y)
        client_w, client_h = _client_size(selected.hwnd)
        hit_hwnd = _window_from_point(screen_x, screen_y)

        print("\nMANUAL_HOVER_MARK")
        print(f"cursor_screen=({screen_x},{screen_y})")
        print(f"selected_client=({client_x},{client_y})")
        print(f"selected_client_size=({client_w},{client_h})")
        print(f"selected_ratio=({client_x / client_w:.6f},{client_y / client_h:.6f})")
        _print_window("hit_test", hit_hwnd)
        print(f"hit_root_is_game_parent={_root(hit_hwnd) == parent.hwnd if hit_hwnd else False}")
        print(f"hit_is_selected={hit_hwnd == selected.hwnd}")
        print("hit_ancestor_chain:")
        for index, hwnd in enumerate(_ancestor_chain(hit_hwnd), 1):
            print(
                f"  [{index}] hwnd={hwnd} class='{_window_class(hwnd)}' "
                f"title='{_window_text(hwnd)}' parent={_parent(hwnd)}"
            )

        save_png(capture.capture(parent.hwnd), str(hover_path))
        print(f"screenshot_hover={hover_path}")
        print("\n接下来程序不会移动真实鼠标，也不会激活游戏。")
        print("它只把刚才这个人工确认的 screen 坐标转换成 WSGAME client 坐标，并发送后台 PostMessageW 点击。")
        print(f"background_click_target_hwnd={selected.hwnd} class='WSGAME'")
        print(f"background_click_target_client=({client_x},{client_y})")
        print("后台 PostMessageW 点击执行中……")
        BackgroundInput(selected.hwnd).click(client_x, client_y)
        time.sleep(1.5)

        foreground_after = _foreground_hwnd()
        save_png(capture.capture(parent.hwnd), str(after_path))
        print(f"foreground_after_click={foreground_after}")
        print(f"foreground_unchanged={foreground_after == foreground_before}")
        print(f"screenshot_before={before_path}")
        print(f"screenshot_after={after_path}")
        print("请人工确认：道具栏是否由关变开（或由开变关）。")
        print("\n结论判定：")
        print("- 如果现在打开：此前失败主要是坐标计算错误；后台鼠标通道至少对这个按钮可用。")
        print("- 如果现在仍未打开：坐标问题基本排除，后台输入通道本身仍未被游戏接受。")
        result_code = 0
    except Exception as exc:
        print(f"probe_error={exc}")
    finally:
        try:
            _restore_context(manager, original_surface, original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
            result_code = 1
        foreground_final = _foreground_hwnd()
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_final={foreground_final}")
        print(f"foreground_unchanged={foreground_final == foreground_before}")
        print("道具栏状态：保留测试后的状态，不自动恢复。")

    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
