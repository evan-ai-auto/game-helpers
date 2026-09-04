"""Real-scene probe: background-click the item icon and verify item panel open.

The operator manually hovers the actual ``道具`` icon while the game is
foreground. After F8, the probe restores the original foreground window,
posts the click to the selected WSGAME child, then uses the generic visual
state detector to search the complete captured parent frame for
``item_panel_open``. The panel may appear anywhere in the frame.

If the click changes the game state but the background WGC surface does not
repaint immediately, the probe performs a background-safe surface refresh
(when another WSGAME view exists) and retries visual verification. A remaining
visual timeout is reported as ``pending_visual`` rather than as a click
failure.

The probe intentionally leaves the item panel in the resulting state.
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
from .visual_state import detect_visual_state, load_visual_state, make_visual_state_verifier

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
            raise RuntimeError(f"failed to make foreground hwnd={hwnd}: current={_foreground_hwnd()}")
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


def _wait_for_f8() -> bool:
    user32 = ctypes.windll.user32
    while True:
        if user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001:
            return False
        if user32.GetAsyncKeyState(VK_F8) & 0x0001:
            while user32.GetAsyncKeyState(VK_F8) & 0x8000:
                time.sleep(0.02)
            return True
        time.sleep(0.03)


def _restore_context(manager: GameViewManager, surface: int | None, tab: int | None) -> None:
    if surface is not None:
        manager.switch_surface_to(surface)
    if tab is not None:
        manager.switch_to(tab)


def _verify_capture(capture, hwnd: int, profile, *, timeout: float, poll_interval: float):
    """Poll visual state against one known capture target without clicking."""
    verifier = make_visual_state_verifier(lambda: capture.capture(hwnd), profile)
    deadline = time.monotonic() + timeout
    while True:
        value = verifier()
        if value is not None:
            return value
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(poll_interval, remaining))


def _refresh_surface_for_capture(manager: GameViewManager, selected_view_index: int, original_foreground: int) -> bool:
    """Force a background-safe WSGAME repaint by switching away and back."""
    views = manager.views()
    if len(views) <= 1:
        return False

    refresh_index = next(index for index in range(1, len(views) + 1) if index != selected_view_index)
    manager.switch_surface_to(refresh_index)
    manager.switch_surface_to(selected_view_index)

    foreground = _foreground_hwnd()
    if foreground != original_foreground:
        raise RuntimeError(
            "foreground window changed during visual refresh: "
            f"before={original_foreground}, after={foreground}"
        )
    return True


def _print_visual_diagnostic(label: str, frame, profile) -> None:
    """Print one-shot detector evidence so false negatives are distinguishable."""
    observation = detect_visual_state(frame, profile)
    print(f"visual_diagnostic_{label}_status={observation.status}")
    print(f"visual_diagnostic_{label}_confidence={observation.confidence:.6f}")
    print(f"visual_diagnostic_{label}_origin={observation.origin}")
    print(f"visual_diagnostic_{label}_anchor_scores={observation.anchor_scores}")
    print(f"visual_diagnostic_{label}_evidence={observation.evidence}")


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
    original_foreground = _foreground_hwnd()
    original_cursor = _cursor_pos()
    result_code = 1

    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"original_foreground={original_foreground}")

    try:
        sync_selected_character(parent.hwnd, selected)
        capture = WindowsGraphicsCapture()
        output_dir = Path("diagnostic/background_item_panel_open")
        output_dir.mkdir(parents=True, exist_ok=True)
        before_path = output_dir / f"before-character-{selected.view_index}.png"
        after_path = output_dir / f"after-character-{selected.view_index}.png"
        refresh_path = output_dir / f"after-refresh-character-{selected.view_index}.png"
        save_png(capture.capture(parent.hwnd), str(before_path))

        _set_foreground(parent.hwnd)
        print(f"foreground_for_hover={_foreground_hwnd()}")
        print("请手动把真实鼠标移动到‘道具’图标。")
        print("确认‘道具 (Alt+E)’ tooltip 出现后保持鼠标不动，按 F8。")
        print("按 ESC 取消。")
        if not _wait_for_f8():
            print("收到 ESC，取消实验。")
            return 0

        screen_x, screen_y = _cursor_pos()
        client_x, client_y = _screen_to_client(selected.hwnd, screen_x, screen_y)
        print("\nMANUAL_HOVER_MARK")
        print(f"cursor_screen=({screen_x},{screen_y})")
        print(f"selected_client=({client_x},{client_y})")
        print("坐标来自真实 tooltip 命中位置，不猜测图标中心。")

        if not _restore_foreground(original_foreground):
            raise RuntimeError(
                f"cannot restore original foreground before background click: expected={original_foreground} actual={_foreground_hwnd()}"
            )
        if _foreground_hwnd() != original_foreground:
            raise RuntimeError("foreground changed before background click")

        profile_path = Path("data/assets/ui/visual_states/item_panel_open.json")
        profile = load_visual_state(profile_path)
        verifier = make_visual_state_verifier(lambda: capture.capture(parent.hwnd), profile)

        timeout = 5.0
        poll_interval = 0.10
        print("\n开始后台点击 + 视觉状态验证")
        print(f"verification_state={profile.name}")
        print(f"verification_timeout={timeout:.1f}s")
        print(f"verification_poll_interval={poll_interval:.2f}s")
        outcome = BackgroundInput(selected.hwnd).click_and_verify(
            client_x,
            client_y,
            verifier,
            timeout=timeout,
            poll_interval=poll_interval,
        )

        after_frame = capture.capture(parent.hwnd)
        save_png(after_frame, str(after_path))
        print(f"click_dispatched={outcome.dispatched}")
        print(f"verification_verified={outcome.verified}")
        print(f"verification_timed_out={outcome.timed_out}")
        print(f"verification_elapsed={outcome.elapsed:.3f}s")
        print(f"foreground_after_click={_foreground_hwnd()}")
        print(f"foreground_unchanged={_foreground_hwnd() == original_foreground}")
        print(f"screenshot_before={before_path}")
        print(f"screenshot_after={after_path}")
        _print_visual_diagnostic("after", after_frame, profile)

        observation = outcome.value if outcome.verified else None
        refresh_attempted = False
        if observation is None and outcome.timed_out:
            print("\n视觉验证超时：不重发点击，先尝试后台安全的 Surface 刷新。")
            refresh_attempted = _refresh_surface_for_capture(manager, selected.view_index, original_foreground)
            print(f"visual_refresh_attempted={refresh_attempted}")
            if refresh_attempted:
                refresh_frame = capture.capture(parent.hwnd)
                save_png(refresh_frame, str(refresh_path))
                observation = _verify_capture(
                    capture,
                    parent.hwnd,
                    profile,
                    timeout=2.0,
                    poll_interval=poll_interval,
                )
                print(f"visual_refresh_screenshot={refresh_path}")
                print(f"verification_after_refresh={observation is not None}")
                _print_visual_diagnostic("after_refresh", refresh_frame, profile)

        if observation is not None:
            print(f"visual_state={observation.state}")
            print(f"visual_status={observation.status}")
            print(f"visual_confidence={observation.confidence:.4f}")
            print(f"visual_origin={observation.origin}")
            print(f"visual_anchor_scores={observation.anchor_scores}")
            print("verification_result=verified")
            print("结果：道具栏已打开（视觉特征确认）。")
            result_code = 0
        elif outcome.timed_out:
            print("verification_result=pending_visual")
            print("结果：后台点击已发送，但后台画面仍未提供可确认的道具栏打开标志。")
            print("这表示视觉确认仍处于 pending，不把它解释成后台点击失败。")
            result_code = 1
        else:
            print("verification_result=incomplete")
            print("结果：后台点击验证未完成。")
            result_code = 1
    except Exception as exc:
        print(f"probe_error={exc}")
        result_code = 1
    finally:
        try:
            _restore_context(manager, original_surface, original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
            result_code = 1
        try:
            foreground_restored = _restore_foreground(original_foreground)
        except Exception as exc:
            print(f"foreground_restore_error={exc}")
            foreground_restored = False
            result_code = 1
        try:
            ctypes.windll.user32.SetCursorPos(*original_cursor)
            cursor_restored = _cursor_pos() == original_cursor
        except Exception as exc:
            print(f"cursor_restore_error={exc}")
            cursor_restored = False
            result_code = 1
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_restore_ok={foreground_restored}")
        print(f"foreground_final={_foreground_hwnd()}")
        print(f"foreground_unchanged={_foreground_hwnd() == original_foreground}")
        print(f"cursor_restored={cursor_restored}")
        print("道具栏状态：保留测试后的状态，不自动恢复。")

    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
