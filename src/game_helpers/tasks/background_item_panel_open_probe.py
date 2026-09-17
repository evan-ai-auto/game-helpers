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
from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .background_item_panel_open_probe_visual import (
    print_visual_diagnostic,
    refresh_surface_for_capture,
    verify_capture,
)
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .probe_win32 import (
    cursor_pos,
    foreground_hwnd,
    restore_context,
    restore_foreground,
    screen_to_client,
    set_foreground,
    wait_for_f8,
)
from .visual_state import load_visual_state, make_visual_state_verifier


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
    original_foreground = foreground_hwnd()
    original_cursor = cursor_pos()
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

        set_foreground(parent.hwnd)
        print(f"foreground_for_hover={foreground_hwnd()}")
        print("请手动把真实鼠标移动到‘道具’图标。")
        print("确认‘道具 (Alt+E)’ tooltip 出现后保持鼠标不动，按 F8。")
        print("按 ESC 取消。")
        if not wait_for_f8():
            print("收到 ESC，取消实验。")
            return 0

        screen_x, screen_y = cursor_pos()
        client_x, client_y = screen_to_client(selected.hwnd, screen_x, screen_y)
        print("\nMANUAL_HOVER_MARK")
        print(f"cursor_screen=({screen_x},{screen_y})")
        print(f"selected_client=({client_x},{client_y})")
        print("坐标来自真实 tooltip 命中位置，不猜测图标中心。")

        if not restore_foreground(original_foreground):
            raise RuntimeError(
                f"cannot restore original foreground before background click: expected={original_foreground} actual={foreground_hwnd()}"
            )
        if foreground_hwnd() != original_foreground:
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
        print(f"foreground_after_click={foreground_hwnd()}")
        print(f"foreground_unchanged={foreground_hwnd() == original_foreground}")
        print(f"screenshot_before={before_path}")
        print(f"screenshot_after={after_path}")
        print_visual_diagnostic("after", after_frame, profile)

        observation = outcome.value if outcome.verified else None
        refresh_attempted = False
        if observation is None and outcome.timed_out:
            print("\n视觉验证超时：不重发点击，先尝试后台安全的 Surface 刷新。")
            refresh_attempted = refresh_surface_for_capture(manager, selected.view_index, original_foreground)
            print(f"visual_refresh_attempted={refresh_attempted}")
            if refresh_attempted:
                refresh_frame = capture.capture(parent.hwnd)
                save_png(refresh_frame, str(refresh_path))
                observation = verify_capture(
                    capture,
                    parent.hwnd,
                    profile,
                    timeout=2.0,
                    poll_interval=poll_interval,
                )
                print(f"visual_refresh_screenshot={refresh_path}")
                print(f"verification_after_refresh={observation is not None}")
                print_visual_diagnostic("after_refresh", refresh_frame, profile)

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
            restore_context(manager, original_surface, original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
            result_code = 1
        try:
            foreground_restored = restore_foreground(original_foreground)
        except Exception as exc:
            print(f"foreground_restore_error={exc}")
            foreground_restored = False
            result_code = 1
        try:
            ctypes.windll.user32.SetCursorPos(*original_cursor)
            cursor_restored = cursor_pos() == original_cursor
        except Exception as exc:
            print(f"cursor_restore_error={exc}")
            cursor_restored = False
            result_code = 1
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_restore_ok={foreground_restored}")
        print(f"foreground_final={foreground_hwnd()}")
        print(f"foreground_unchanged={foreground_hwnd() == original_foreground}")
        print(f"cursor_restored={cursor_restored}")
        print("道具栏状态：保留测试后的状态，不自动恢复。")

    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
