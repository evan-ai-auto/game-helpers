"""MVP-5b CLI: select a 梦幻西游 character and detect 命魂任务 claimed state."""
from __future__ import annotations

import argparse
import ctypes
from pathlib import Path

from PIL import Image

from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .soul_task import detect_soul_task_claimed_icon


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect 命魂任务 claimed state for a 梦幻西游 character.")
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output-dir", default="diagnostic\\soul_task")
    args = parser.parse_args()

    print("[验证] 1/8 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"parent window not found: {args.title!r}")
        return 2
    print(f"parent hwnd={parent.hwnd}")

    print("[验证] 2/8 扫描 WSGAME 实例并识别已登录角色")
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
    print("[验证] 3/8 记录原始 Surface、Tab 与前台")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"foreground_before={foreground_before}")

    print("[验证] 4/8 用户选择角色")
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
    try:
        print("[验证] 5/8 后台切换角色并同步 Surface + Native Tab")
        sync_selected_character(parent.hwnd, selected)
        if manager.current_surface_index() != selected.view_index or manager.current_index() != selected.view_index:
            raise RuntimeError("selected character Surface/Tab is not synchronized")

        print("[验证] 6/8 捕获当前画面并检测命魂任务已领取图标")
        frame = WindowsGraphicsCapture().capture(parent.hwnd)
        output = Path(args.output_dir) / f"character-{selected.view_index}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        save_png(frame, str(output))
        image = Image.open(output)
        observation = detect_soul_task_claimed_icon(image)
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
        if observation.status.value == "claimed":
            print("命魂任务状态：已领取。")
        elif observation.status.value == "not_claimed":
            print("命魂任务状态：未检测到已领取图标，需要进入女娲神使领取流程。")
        else:
            print("命魂任务状态：无法可靠确认，请人工检查截图。")
        if not foreground_ok:
            result_code = 6

    except Exception as exc:
        print(f"detection failed: {type(exc).__name__}: {exc}")
        result_code = 5
    finally:
        print("[验证] 7/8 恢复原始 Surface 与 Tab")
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

    print("[验证] 8/8 结果")
    if result_code:
        print("result=FAILED")
        return result_code
    print("result=PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
