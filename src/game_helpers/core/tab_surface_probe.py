"""Isolated diagnostic for native Tab selection versus the proven Surface switch."""

from __future__ import annotations

import argparse
import ctypes
import time

from .game_view import discover_game_views
from .tab import current_tab_index, find_tab_control, select_tab
from .view_manager import GameViewManager
from .window import find_window


def _foreground() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _state(manager: GameViewManager, tab_hwnd: int) -> tuple[int, int]:
    return manager.current_surface_index(), current_tab_index(tab_hwnd) + 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="top-level game window title")
    parser.add_argument("--game-index", type=int, default=2)
    args = parser.parse_args()

    print("[验证] 1/6 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"找不到游戏主窗口: {args.title}")
        return 2

    print("[验证] 2/6 扫描 WSGAME 与原生 Tab")
    manager = GameViewManager(parent.hwnd, timeout=2.0)
    views = discover_game_views(parent.hwnd)
    tab_hwnd = find_tab_control(parent.hwnd)
    if tab_hwnd is None:
        print("找不到 SysTabControl32")
        return 2
    if not 1 <= args.game_index <= len(views):
        print(f"game-index 必须在 1..{len(views)}")
        return 2

    original_surface, original_tab = _state(manager, tab_hwnd)
    foreground_before = _foreground()
    print(f"parent hwnd={parent.hwnd}")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"foreground_before={foreground_before}")

    print(f"[验证] 3/6 建立已验证基线：后台切换 Surface #{args.game_index}")
    manager.switch_surface_to(args.game_index)
    time.sleep(0.25)
    surface_before_tab, tab_before_tab = _state(manager, tab_hwnd)
    print(f"surface_before_tab={surface_before_tab}")
    print(f"tab_before_tab={tab_before_tab}")

    print(f"[验证] 4/6 仅修改原生 Tab → #{args.game_index}")
    select_tab(tab_hwnd, args.game_index - 1)
    time.sleep(0.25)
    surface_after_tab, tab_after_tab = _state(manager, tab_hwnd)
    foreground_after_tab = _foreground()
    print(f"surface_after_tab={surface_after_tab}")
    print(f"tab_after_tab={tab_after_tab}")
    print(f"foreground_after_tab={foreground_after_tab}")

    print("[验证] 5/6 恢复原始 Surface 与 Tab")
    manager.switch_surface_to(original_surface)
    time.sleep(0.15)
    select_tab(tab_hwnd, original_tab - 1)
    time.sleep(0.15)
    restored_surface, restored_tab = _state(manager, tab_hwnd)
    foreground_final = _foreground()
    print(f"restored_surface={restored_surface}")
    print(f"restored_tab={restored_tab}")
    print(f"foreground_final={foreground_final}")

    print("[验证] 6/6 结果")
    print(f"surface_preserved_after_tab={surface_after_tab == args.game_index}")
    print(f"tab_reached_target={tab_after_tab == args.game_index}")
    print(f"foreground_unchanged={foreground_final == foreground_before}")
    print(f"restored={restored_surface == original_surface and restored_tab == original_tab}")

    success = (
        surface_before_tab == args.game_index
        and surface_after_tab == args.game_index
        and tab_after_tab == args.game_index
        and foreground_final == foreground_before
        and restored_surface == original_surface
        and restored_tab == original_tab
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
