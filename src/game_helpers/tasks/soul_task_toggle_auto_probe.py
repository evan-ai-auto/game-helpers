"""Automatic manual-verification probe for the soul-task panel toggle."""
from __future__ import annotations
import ctypes, sys, time
from pathlib import Path
from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .soul_task import DEFAULT_SOUL_TASK_UI, detect_soul_task_panel_collapsed


def _fg() -> int: return int(ctypes.windll.user32.GetForegroundWindow())

def _parent_to_child(parent: int, child: int, x: int, y: int) -> tuple[int,int]:
    p = ctypes.wintypes.POINT(x, y)
    u = ctypes.windll.user32
    if not u.ClientToScreen(parent, ctypes.byref(p)) or not u.ScreenToClient(child, ctypes.byref(p)):
        raise ctypes.WinError()
    return int(p.x), int(p.y)

def main() -> int:
    if sys.platform != "win32": print("本探针仅支持 Windows。"); return 2
    title = sys.argv[1] if len(sys.argv) > 1 else "梦幻西游 ONLINE"
    parent = find_window(title)
    if parent is None: print(f"parent window not found: {title!r}"); return 2
    manager = GameViewManager(parent.hwnd, timeout=2.0)
    scan = scan_game_accounts(parent.hwnd); accounts = logged_in_accounts(scan)
    print(f"parent hwnd={parent.hwnd}")
    for i,a in enumerate(accounts,1): print(f"  [{i}] character='{a.character_name}' identity='{a.identity}' view=#{a.view_index}")
    if not accounts: return 1
    try: choice=int(input("\n请选择角色编号：").strip())
    except (EOFError,ValueError): print("角色编号无效。"); return 1
    if not 1 <= choice <= len(accounts): print("角色编号无效。"); return 1
    selected=select_character(scan, accounts[choice-1].view_index)
    original_surface=manager.current_surface_index(); original_tab=manager.current_index(); original_fg=_fg()
    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"original_surface={original_surface}\noriginal_tab={original_tab}\noriginal_foreground={original_fg}")
    result=1
    try:
        sync_selected_character(parent.hwnd, selected); time.sleep(.3)
        cap=WindowsGraphicsCapture(); before=cap.capture(parent.hwnd)
        obs=detect_soul_task_panel_collapsed(before)
        print(f"panel_before_collapsed={obs.collapsed}")
        print(f"panel_before_confidence={obs.confidence:.3f}")
        print(f"before_evidence={obs.evidence}")
        target_expanded=bool(obs.collapsed); print(f"target_state={'expanded' if target_expanded else 'collapsed'}")
        point=DEFAULT_SOUL_TASK_UI.task_entry_toggle.pixel(before.width,before.height)
        child_xy=_parent_to_child(parent.hwnd, selected.hwnd, *point)
        print(f"parent_toggle_pixel={point}"); print(f"selected_toggle_client={child_xy}")
        BackgroundInput(selected.hwnd).click_sync(*child_xy)
        time.sleep(.8)
        after=cap.capture(parent.hwnd); after_obs=detect_soul_task_panel_collapsed(after)
        print(f"panel_after_collapsed={after_obs.collapsed}")
        print(f"panel_after_confidence={after_obs.confidence:.3f}")
        print(f"after_evidence={after_obs.evidence}")
        expected_collapsed=not target_expanded
        success=after_obs.collapsed == expected_collapsed
        print(f"toggle_verified={success}")
        print(f"foreground_unchanged_after_click={_fg()==original_fg}")
        out=Path("diagnostic/soul_task_toggle_auto"); out.mkdir(parents=True,exist_ok=True)
        save_png(before,str(out/f"before-character-{selected.view_index}.png")); save_png(after,str(out/f"after-character-{selected.view_index}.png"))
        result=0 if success else 1
    except Exception as exc: print(f"probe_error={exc}")
    finally:
        try: manager.switch_surface_to(original_surface); manager.switch_to(original_tab)
        except Exception as exc: print(f"context_restore_error={exc}"); result=1
        try: manager.switch_surface_to(original_surface); manager.switch_to(original_tab)
        except Exception: pass
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index()==original_surface}")
        print(f"restored_tab={manager.current_index()==original_tab}")
        print(f"foreground_final={_fg()}")
        print(f"foreground_unchanged={_fg()==original_fg}")
        print("panel_state_restored=False (intentional)")
    return result

if __name__ == "__main__": raise SystemExit(main())
