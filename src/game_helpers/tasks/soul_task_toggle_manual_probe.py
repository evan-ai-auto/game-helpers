"""Manual bidirectional probe for the soul-task expand/collapse toggle.

The probe leaves the UI in the post-click state for visual verification and
intentionally does not restore Surface, Tab, or panel state.
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


def _window_origin_in_parent(parent_hwnd: int, child_hwnd: int) -> tuple[int, int]:
    """Return child top-left relative to the parent client origin."""
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(parent_hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    parent_point = wintypes.POINT(rect.left, rect.top)
    if not user32.ScreenToClient(parent_hwnd, ctypes.byref(parent_point)):
        raise ctypes.WinError()
    if not user32.GetWindowRect(child_hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    child_point = wintypes.POINT(rect.left, rect.top)
    if not user32.ScreenToClient(parent_hwnd, ctypes.byref(child_point)):
        raise ctypes.WinError()
    return child_point.x - parent_point.x, child_point.y - parent_point.y


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
    origin_x, origin_y = _window_origin_in_parent(parent.hwnd, selected.hwnd)
    local_x = point[0] - origin_x
    local_y = point[1] - origin_y
    print(f"parent_toggle_pixel={point}")
    print(f"child_origin_in_parent=({origin_x},{origin_y})")
    print(f"toggle_click_client=({local_x},{local_y})")
    print("后台点击执行中……")
    BackgroundInput(selected.hwnd).click_sync(local_x, local_y)
    time.sleep(0.8)

    frame_after = capture.capture(parent.hwnd)
    save_png(frame_after, str(output_dir / f"after-character-{selected.view_index}.png"))
    foreground_after = _foreground_hwnd()
    print(f"foreground_after={foreground_after}")
    print(f"foreground_unchanged={foreground_after == foreground_before}")
    print(f"screenshot_after={output_dir / f'after-character-{selected.view_index}.png'}")
    print("\n点击已经完成。")
    print("本探针故意不恢复 Surface、Tab 或面板状态。")
    print("请直接观察游戏画面：面板是否发生预期的展开/折叠。")
    print("本探针不使用 panel_after 自动判定，人工观察结果为准。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
