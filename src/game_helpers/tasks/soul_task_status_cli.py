"""MVP-5b CLI: select a 梦幻西游 character and detect 命魂任务 state."""
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
from .soul_task import (
    DEFAULT_SOUL_TASK_UI,
    SoulTaskDetectionReason,
    SoulTaskStatus,
    detect_soul_task_claimed_icon,
    detect_soul_task_panel_collapsed,
)


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _parent_client_offset(parent, child) -> tuple[int, int]:
    """Return child origin in the parent capture coordinate system."""
    if parent.bounds is None or child.window.bounds is None:
        return 0, 0
    return child.window.bounds.left - parent.bounds.left, child.window.bounds.top - parent.bounds.top


def _click_soul_task_toggle(parent, selected_view, frame_width: int, frame_height: int) -> tuple[int, int]:
    """Click the marked toggle using selected WSGAME client coordinates."""
    sx, sy = DEFAULT_SOUL_TASK_UI.task_entry_toggle.pixel(frame_width, frame_height)
    ox, oy = _parent_client_offset(parent, selected_view)
    local_x, local_y = sx - ox, sy - oy
    BackgroundInput(selected_view.hwnd).click(local_x, local_y)
    return local_x, local_y


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect 命魂任务 claimed state for a 梦幻西游 character.")
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output-dir", default="diagnostic\\soul_task")
    args = parser.parse_args()

    print("[验证] 1/10 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"parent window not found: {args.title!r}")
        return 2
    print(f"parent hwnd={parent.hwnd}")

    print("[验证] 2/10 扫描 WSGAME 实例并识别已登录角色")
    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"WSGAME instances={len(scan.accounts)}")
    print(f"logged_in characters={len(accounts)}")
    if not accounts:
        print("未发现已登录角色，无法检测命魂任务状态。")
        return 3
    for option, account in enumerate(accounts, start=1):
        print(f"  [{option}] character={account.character_name!r} identity={account.identity!r} view=#{account.view_index}")

    manager = GameViewManager(parent.hwnd, timeout=2.0)
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    foreground_before = _foreground_hwnd()
    print("[验证] 3/10 记录原始 Surface、Tab 与前台")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"foreground_before={foreground_before}")

    print("[验证] 4/10 用户选择角色")
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

    result_code = 0
    panel_was_open = True
    panel_opened_by_tool = False
    try:
        print("[验证] 5/10 后台切换角色并同步 Surface + Native Tab")
        sync_selected_character(parent.hwnd, selected)
        if manager.current_surface_index() != selected.view_index or manager.current_index() != selected.view_index:
            raise RuntimeError("selected character Surface/Tab is not synchronized")

        print("[验证] 6/10 检测命魂任务界面展开/折叠状态")
        frame_before = WindowsGraphicsCapture().capture(parent.hwnd)
        image_before = Image.frombytes("RGBA", (frame_before.width, frame_before.height), frame_before.data, "raw", "BGRA").convert("RGB")
        panel = detect_soul_task_panel_collapsed(image_before)
        panel_was_open = panel.collapsed is False
        print(f"panel_collapsed={panel.collapsed}")
        print(f"panel_confidence={panel.confidence:.3f}")
        print(f"panel_reason={panel.reason.value}")
        for evidence in panel.evidence:
            print(f"panel_evidence={evidence}")

        if panel.collapsed is None:
            raise RuntimeError("无法可靠判断命魂任务界面展开/折叠状态")
        if panel.collapsed:
            print("检测到折叠状态，后台点击展开开关。")
            local_x, local_y = _click_soul_task_toggle(parent, next(v for v in discover_game_views(parent.hwnd) if v.index == selected.view_index), frame_before.width, frame_before.height)
            panel_opened_by_tool = True
            print(f"toggle_click_client=({local_x},{local_y})")
            time.sleep(0.45)
            frame_opened = WindowsGraphicsCapture().capture(parent.hwnd)
            image_opened = Image.frombytes("RGBA", (frame_opened.width, frame_opened.height), frame_opened.data, "raw", "BGRA").convert("RGB")
            panel_after = detect_soul_task_panel_collapsed(image_opened)
            print(f"panel_collapsed_after_open={panel_after.collapsed}")
            print(f"panel_confidence_after_open={panel_after.confidence:.3f}")
            if panel_after.collapsed is True:
                raise RuntimeError("点击展开开关后仍检测为折叠状态")
            if panel_after.collapsed is None:
                raise RuntimeError("点击展开开关后无法可靠判断面板状态")
            image_for_detection = image_opened
            frame = frame_opened
        else:
            print("检测到面板已经展开，不执行点击。")
            image_for_detection = image_before
            frame = frame_before

        print("[验证] 7/10 捕获当前画面并检测命魂任务已领取图标")
        output = Path(args.output_dir) / f"character-{selected.view_index}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        save_png(frame, str(output))
        observation = detect_soul_task_claimed_icon(image_for_detection)
        print(f"capture={frame.width}x{frame.height} backend={frame.backend}")
        print(f"screenshot={output}")
        print(f"soul_task_status={observation.status.value}")
        print(f"detection_reason={observation.reason.value}")
        print(f"confidence={observation.confidence:.3f}")
        print(f"match_location={observation.match_location}")
        for evidence in observation.evidence:
            print(f"evidence={evidence}")
        foreground_after = _foreground_hwnd()
        foreground_ok = foreground_after == foreground_before
        print(f"foreground_unchanged={foreground_ok}")
        if observation.status == SoulTaskStatus.CLAIMED:
            print("命魂任务状态：已领取。")
        elif observation.status == SoulTaskStatus.NOT_CLAIMED:
            print("命魂任务状态：未检测到已领取图标，需要进入女娲神使领取流程。")
        else:
            print("命魂任务状态：无法可靠确认，请人工检查截图。")
        if not foreground_ok:
            result_code = 6

    except Exception as exc:
        print(f"detection failed: {type(exc).__name__}: {exc}")
        result_code = 5
    finally:
        print("[验证] 8/10 恢复命魂任务界面原始展开状态")
        if panel_opened_by_tool:
            try:
                views = discover_game_views(parent.hwnd)
                view = next(v for v in views if v.index == selected.view_index)
                # Use the same toggle point in the restored selected surface.
                frame_restore = WindowsGraphicsCapture().capture(parent.hwnd)
                local_x, local_y = _click_soul_task_toggle(parent, view, frame_restore.width, frame_restore.height)
                time.sleep(0.35)
                print(f"toggle_restore_client=({local_x},{local_y})")
            except Exception as exc:
                print(f"panel restore failed: {type(exc).__name__}: {exc}")
                result_code = result_code or 8

        print("[验证] 9/10 恢复原始 Surface 与 Tab")
        try:
            manager.switch_surface_to(original_surface)
            manager.switch_to(original_tab)
            restored_surface = manager.current_surface_index() == original_surface
            restored_tab = manager.current_index() == original_tab
        except Exception as exc:
            print(f"restore failed: {type(exc).__name__}: {exc}")
            restored_surface = False
            restored_tab = False
        foreground_final = _foreground_hwnd()
        foreground_ok = foreground_final == foreground_before
        print(f"restored_surface={restored_surface}")
        print(f"restored_tab={restored_tab}")
        print(f"foreground_unchanged={foreground_ok}")
        if not (restored_surface and restored_tab and foreground_ok):
            result_code = result_code or 7

    print("[验证] 10/10 结果")
    if result_code:
        print("result=FAILED")
        return result_code
    print("result=PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
