"""Diagnostic probe for the 命魂任务 panel toggle.

This probe intentionally does NOT restore the panel, Surface, or native Tab after
clicking. It exists to prove that a collapsed panel can be opened by the
background input path before the production workflow re-enables restoration.
"""
from __future__ import annotations

import argparse
import ctypes
import time
from pathlib import Path

from PIL import Image

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.game_view import discover_game_views
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .soul_task import DEFAULT_SOUL_TASK_UI, detect_soul_task_panel_collapsed


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _parent_client_offset(parent, child) -> tuple[int, int]:
    if parent.bounds is None or child.window.bounds is None:
        return 0, 0
    return child.window.bounds.left - parent.bounds.left, child.window.bounds.top - parent.bounds.top


def _capture_image() -> tuple[object, Image.Image]:
    frame = WindowsGraphicsCapture().capture(parent_hwnd)
    image = Image.frombytes("RGBA", (frame.width, frame.height), frame.data, "raw", "BGRA").convert("RGB")
    return frame, image


parent_hwnd = 0


def main() -> int:
    global parent_hwnd
    parser = argparse.ArgumentParser(description="Prove background expansion of the collapsed 梦幻西游 命魂任务 panel.")
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output-dir", default="diagnostic\\soul_task_toggle_probe")
    parser.add_argument("--wait", type=float, default=0.8)
    args = parser.parse_args()

    print("[验证] 1/9 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"parent window not found: {args.title!r}")
        return 2
    parent_hwnd = parent.hwnd
    print(f"parent hwnd={parent.hwnd}")

    print("[验证] 2/9 扫描 WSGAME 实例并识别已登录角色")
    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"WSGAME instances={len(scan.accounts)}")
    print(f"logged_in characters={len(accounts)}")
    if not accounts:
        print("未发现已登录角色，无法验证命魂任务展开触发。")
        return 3
    for option, account in enumerate(accounts, start=1):
        print(f"  [{option}] character={account.character_name!r} identity={account.identity!r} view=#{account.view_index}")

    manager = GameViewManager(parent.hwnd, timeout=2.0)
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    foreground_before = _foreground_hwnd()
    print("[验证] 3/9 记录当前 Surface、Tab 与前台")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"foreground_before={foreground_before}")

    print("[验证] 4/9 用户选择角色")
    try:
        choice = int(input("请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 4
    if not 1 <= choice <= len(accounts):
        print(f"角色编号必须在 1 到 {len(accounts)} 之间。")
        return 4
    selected = select_character(scan, accounts[choice - 1].view_index)
    print(f"selected character={selected.character_name!r} view_index={selected.view_index} hwnd={selected.hwnd} pid={selected.process_id}")

    print("[验证] 5/9 后台切换角色并同步 Surface + Native Tab")
    sync_selected_character(parent.hwnd, selected)

    print("[验证] 6/9 确认当前确实为折叠态，并保存点击前截图")
    frame_before, image_before = _capture_image()
    panel_before = detect_soul_task_panel_collapsed(image_before)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    before_path = output_dir / f"before-character-{selected.view_index}.png"
    save_png(frame_before, str(before_path))
    print(f"panel_before={panel_before.collapsed}")
    print(f"panel_confidence_before={panel_before.confidence:.3f}")
    print(f"panel_reason_before={panel_before.reason.value}")
    for evidence in panel_before.evidence:
        print(f"before_evidence={evidence}")
    print(f"screenshot_before={before_path}")
    if panel_before.collapsed is not True:
        print("当前不是可验证的折叠态；为避免误点击，本探针不会继续。")
        return 5

    print("[验证] 7/9 后台触发展开开关（本探针故意不恢复）")
    view = next(v for v in discover_game_views(parent.hwnd) if v.index == selected.view_index)
    sx, sy = DEFAULT_SOUL_TASK_UI.task_entry_toggle.pixel(frame_before.width, frame_before.height)
    ox, oy = _parent_client_offset(parent, view)
    local_x, local_y = sx - ox, sy - oy
    print(f"parent_toggle_pixel=({sx},{sy})")
    print(f"child_origin_in_parent=({ox},{oy})")
    print(f"toggle_click_client=({local_x},{local_y})")
    BackgroundInput(selected.hwnd).click_sync(local_x, local_y)
    time.sleep(args.wait)

    print("[验证] 8/9 截图复检展开结果")
    frame_after, image_after = _capture_image()
    panel_after = detect_soul_task_panel_collapsed(image_after)
    after_path = output_dir / f"after-character-{selected.view_index}.png"
    save_png(frame_after, str(after_path))
    foreground_after = _foreground_hwnd()
    print(f"panel_after={panel_after.collapsed}")
    print(f"panel_confidence_after={panel_after.confidence:.3f}")
    print(f"panel_reason_after={panel_after.reason.value}")
    for evidence in panel_after.evidence:
        print(f"after_evidence={evidence}")
    print(f"screenshot_after={after_path}")
    print(f"foreground_unchanged={foreground_after == foreground_before}")

    print("[验证] 9/9 结果")
    if panel_after.collapsed is False and foreground_after == foreground_before:
        print("result=PASSED")
        print("注意：本探针故意不恢复面板、Surface、Tab；请人工观察游戏当前画面是否已经展开。")
        return 0
    print("result=FAILED")
    print("注意：本探针故意不恢复状态，请根据截图人工检查。")
    return 6


if __name__ == "__main__":
    raise SystemExit(main())
