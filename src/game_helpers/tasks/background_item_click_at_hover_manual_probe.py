"""Background click probe using a manually confirmed tooltip coordinate.

The user first moves the real mouse over the in-game item icon while the game
is foreground and presses F8 only after the "道具 (Alt+E)" tooltip is visible.
The probe then converts that exact screen coordinate to WSGAME client
coordinates and sends the click to the background WSGAME window without
activating it. Verification is bounded by a timeout and is based on a caller-
selected observable state, not on the assumption that a background WGC frame
must repaint immediately.
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


def _set_foreground(hwnd: int, timeout: float = 2.0) -> None:
    """Best-effort foreground handoff used only by this diagnostic probe."""
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    current = _foreground_hwnd()
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
        while _foreground_hwnd() != hwnd and time.monotonic() < deadline:
            time.sleep(0.02)
        if _foreground_hwnd() != hwnd:
            raise RuntimeError(
                f"failed to make foreground hwnd={hwnd}: current={_foreground_hwnd()}"
            )
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def _restore_foreground(hwnd: int | None) -> bool:
    if not hwnd:
        return True
    _set_foreground(int(hwnd))
    return _foreground_hwnd() == int(hwnd)


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

    selected = select_character(scan, accounts[choice - 1].view_index)
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    foreground_before = _foreground_hwnd()
    original_cursor = _cursor_pos()

    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    _print_window("selected_info", selected.hwnd)
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"original_foreground={foreground_before}")
    print(f"original_cursor={original_cursor}")
    print("\n本实验先人工记录真正触发 tooltip 的鼠标位置，再把同一个位置换成后台 WSGAME 点击。")
    print("这次不再猜图标中心坐标；坐标来自已经验证成功的真实鼠标位置。")
    print("F8 后程序会立即恢复原前台窗口，然后发送后台点击。")

    result_code = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        capture = WindowsGraphicsCapture()
        output_dir = Path("diagnostic/background_item_click_at_hover_manual")
        output_dir.mkdir(parents=True, exist_ok=True)
        before_path = output_dir / f"before-character-{selected.view_index}.png"
        hover_path = output_dir / f"hover-character-{selected.view_index}.png"
        during_path = output_dir / f"during-background-character-{selected.view_index}.png"

        save_png(capture.capture(parent.hwnd), str(before_path))

        _set_foreground(parent.hwnd)
        print(f"foreground_during_coordinate_capture={_foreground_hwnd()}")
        print("\n请手动把真实鼠标移动到‘道具’图标。")
        print("等‘道具 (Alt+E)’ tooltip 已明确显示后，保持鼠标不动，按 F8。")
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
            print(f"  [{index}] hwnd={hwnd} class='{_window_class(hwnd)}' title='{_window_text(hwnd)}' parent={_parent(hwnd)}")
        save_png(capture.capture(parent.hwnd), str(hover_path))
        print(f"screenshot_hover={hover_path}")

        if not _restore_foreground(foreground_before):
            raise RuntimeError(f"cannot restore original foreground before background click: expected={foreground_before} actual={_foreground_hwnd()}")
        print(f"foreground_before_background_click={_foreground_hwnd()}")
        if _foreground_hwnd() != foreground_before:
            raise RuntimeError("foreground changed before background click")

        timeout = 5.0
        poll_interval = 0.10
        print("\n发送后台 PostMessageW 点击，并在限定时限内进行结果检测。")
        print(f"verification_timeout={timeout:.1f}s")
        print(f"verification_poll_interval={poll_interval:.2f}s")
        print("注意：后台 WGC 画面可能暂时不重绘，因此‘截图未立即变化’不会直接判定点击失败。")
        clicker = BackgroundInput(selected.hwnd)
        started = time.monotonic()
        clicker.click(client_x, client_y)
        dispatched_at = time.monotonic()
        print(f"click_dispatched=True elapsed={dispatched_at - started:.3f}s")

        # This diagnostic verifier deliberately checks only the hard invariant
        # available without stealing foreground: the click must not have
        # changed the user's foreground application. A later production caller
        # should replace this with a semantic detector for its target state.
        verified = False
        elapsed = 0.0
        while True:
            foreground_now = _foreground_hwnd()
            if foreground_now != foreground_before:
                print(f"verification_foreground_changed={foreground_now}")
                break
            elapsed = time.monotonic() - dispatched_at
            if elapsed >= timeout:
                break
            time.sleep(min(poll_interval, timeout - elapsed))

        save_png(capture.capture(parent.hwnd), str(during_path))
        print(f"foreground_after_click={_foreground_hwnd()}")
        print(f"foreground_unchanged={_foreground_hwnd() == foreground_before}")
        print(f"screenshot_during_background={during_path}")
        if _foreground_hwnd() != foreground_before:
            print("结果：后台点击后前台窗口发生变化，检测失败。")
            result_code = 1
        else:
            print("结果：后台点击已发送，且在检测时限内前台保持不变。")
            print("注意：当前探针不能仅靠后台截图判断道具栏是否已经打开；截图变化属于辅助证据。")
            print("如果需要语义确认，请在下一步接入‘道具栏已打开’的专用视觉检测器。")
            verified = True
            result_code = 0
        print(f"verification_verified={verified}")
        print(f"verification_elapsed={elapsed:.3f}s")
        print(f"verification_timeout={timeout:.3f}s")
    except Exception as exc:
        print(f"probe_error={exc}")
    finally:
        try:
            _restore_context(manager, original_surface, original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
            result_code = 1
        try:
            foreground_restored = _restore_foreground(foreground_before)
        except Exception as exc:
            print(f"foreground_restore_error={exc}")
            foreground_restored = False
            result_code = 1
        try:
            ctypes.windll.user32.SetCursorPos(int(original_cursor[0]), int(original_cursor[1]))
            cursor_restored = _cursor_pos() == original_cursor
        except Exception as exc:
            print(f"cursor_restore_error={exc}")
            cursor_restored = False
            result_code = 1
        foreground_final = _foreground_hwnd()
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_restore_ok={foreground_restored}")
        print(f"foreground_final={foreground_final}")
        print(f"foreground_unchanged={foreground_final == foreground_before}")
        print(f"cursor_restored={cursor_restored}")
        print("道具栏状态：保留测试后的状态，不自动恢复。")
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
