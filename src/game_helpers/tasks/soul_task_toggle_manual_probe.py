"""Local manual probe for the soul-task expand/collapse toggle.

Only the soul-task panel state is intentionally left changed. Surface, native
Tab selection, and the user's foreground window are restored even on failure.
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
from .soul_task import DEFAULT_SOUL_TASK_UI, detect_soul_task_panel_collapsed


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _screen_point_from_parent_client(parent_hwnd: int, x: int, y: int) -> tuple[int, int]:
    user32 = ctypes.windll.user32
    point = wintypes.POINT(int(x), int(y))
    if not user32.ClientToScreen(parent_hwnd, ctypes.byref(point)):
        raise ctypes.WinError()
    return point.x, point.y


def _window_metadata(hwnd: int) -> tuple[str, str, int, int]:
    user32 = ctypes.windll.user32
    title_length = user32.GetWindowTextLengthW(hwnd)
    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
    user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)
    class_buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
    parent_hwnd = int(user32.GetParent(hwnd))
    root_hwnd = int(user32.GetAncestor(hwnd, 2))  # GA_ROOT
    return class_buffer.value, title_buffer.value, parent_hwnd, root_hwnd


def _resolve_toggle_target(parent_hwnd: int, selected_hwnd: int, x: int, y: int) -> tuple[int, tuple[int, int], str]:
    """Resolve the actual window under the visual toggle point.

    WindowFromPoint is authoritative for the visual target. We only accept a
    hit that belongs to the host parent; we never silently redirect an in-host
    hit back to WSGAME. This makes a bad HWND/coordinate diagnosis explicit.
    """
    user32 = ctypes.windll.user32
    screen_x, screen_y = _screen_point_from_parent_client(parent_hwnd, x, y)
    point = wintypes.POINT(screen_x, screen_y)
    hit_hwnd = int(user32.WindowFromPoint(point))
    if not hit_hwnd:
        raise RuntimeError("WindowFromPoint returned null")

    belongs_to_parent = bool(user32.IsChild(parent_hwnd, hit_hwnd) or hit_hwnd == parent_hwnd)
    class_name, title, direct_parent, root_hwnd = _window_metadata(hit_hwnd)
    if not belongs_to_parent:
        raise RuntimeError(
            f"visual toggle point hit hwnd={hit_hwnd}, but it is outside host parent={parent_hwnd}; "
            f"class={class_name!r}, title={title!r}, root={root_hwnd}"
        )

    client = wintypes.POINT(screen_x, screen_y)
    if not user32.ScreenToClient(hit_hwnd, ctypes.byref(client)):
        raise ctypes.WinError()
    evidence = (
        f"hit hwnd={hit_hwnd} class={class_name!r} title={title!r} "
        f"parent={direct_parent} root={root_hwnd} selected={selected_hwnd}"
    )
    return hit_hwnd, (client.x, client.y), evidence


def _restore_context(manager: GameViewManager, original_surface: int | None, original_tab: int | None) -> None:
    """Restore automation context without touching the soul-task panel state."""
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

    selected = select_character(result, accounts[choice - 1].view_index)
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    foreground_before = _foreground_hwnd()
    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"foreground_before={foreground_before}")

    panel_state_changed = False
    foreground_unchanged = True
    result_code = 1
    try:
        sync_selected_character(parent.hwnd, selected)
        time.sleep(0.3)
        capture = WindowsGraphicsCapture()
        frame_before = capture.capture(parent.hwnd)
        panel_before = detect_soul_task_panel_collapsed(frame_before)
        print(f"panel_before_collapsed={panel_before.collapsed}")
        print(f"panel_before_confidence={panel_before.confidence:.3f}")
        print(f"before_evidence={panel_before.evidence}")

        output_dir = Path("diagnostic/soul_task_toggle_manual")
        output_dir.mkdir(parents=True, exist_ok=True)
        save_png(frame_before, str(output_dir / f"before-character-{selected.view_index}.png"))

        direction = input("执行 [e] 展开 / [c] 折叠（输入 e/c）：").strip().lower()
        if direction not in {"e", "c"}:
            print("无效操作。")
            return 1
        if direction == "e" and not panel_before.collapsed:
            print("当前已经是展开态，请先手动折叠后重试。")
            return 1
        if direction == "c" and panel_before.collapsed:
            print("当前已经是折叠态，请先手动展开后重试。")
            return 1

        point = DEFAULT_SOUL_TASK_UI.task_entry_toggle.pixel(frame_before.width, frame_before.height)
        print(f"parent_toggle_pixel={point}")
        hit_hwnd, hit_client, hit_evidence = _resolve_toggle_target(
            parent.hwnd, selected.hwnd, point[0], point[1]
        )
        print(f"toggle_target_hwnd={hit_hwnd}")
        print(f"toggle_target_client={hit_client}")
        print(f"toggle_target_evidence={hit_evidence}")
        print("后台点击执行中……")
        BackgroundInput(hit_hwnd).click_sync(hit_client[0], hit_client[1])
        panel_state_changed = True
        time.sleep(0.8)

        frame_after = capture.capture(parent.hwnd)
        save_png(frame_after, str(output_dir / f"after-character-{selected.view_index}.png"))
        foreground_after_click = _foreground_hwnd()
        foreground_unchanged = foreground_after_click == foreground_before
        print(f"foreground_after_click={foreground_after_click}")
        print(f"foreground_unchanged_after_click={foreground_unchanged}")
        print(f"screenshot_after={output_dir / f'after-character-{selected.view_index}.png'}")
        print("\n后台输入消息已发送。")
        print("是否真正触发游戏控件，需要通过面板状态/截图人工确认。")
        print("本探针只保留命魂任务面板的展开/折叠变化。")
        print("Surface、Tab 将恢复到测试前状态；Foreground 不应发生变化。")
        result_code = 0
    finally:
        restore_error = None
        try:
            _restore_context(manager, original_surface, original_tab)
        except Exception as exc:  # pragma: no cover - diagnostic safety path
            restore_error = exc
            result_code = 1
        foreground_final = _foreground_hwnd()
        foreground_unchanged = foreground_unchanged and foreground_final == foreground_before
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_final={foreground_final}")
        print(f"foreground_unchanged={foreground_unchanged}")
        print("panel_state_restored=False (intentional)")
        if restore_error is not None:
            print(f"restore_error={restore_error}")
        if panel_state_changed:
            print("命魂任务面板状态：保留点击后的状态，不恢复。")

    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
