"""Minimal diagnostic for WGC stability across WSGAME surface switches."""

from __future__ import annotations

import argparse
import ctypes
import time

from ..capture import WindowsGraphicsCapture, save_png
from ..core.game_view import discover_game_views
from ..core.view_manager import GameViewManager
from ..core.window import find_window


def log(step: str, message: str) -> None:
    print(f"[诊断] {step} {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="top-level game window title")
    parser.add_argument("--game-index", type=int, default=2)
    parser.add_argument("--output-dir", default="diagnostic/wgc_surface_probe")
    args = parser.parse_args()

    import pathlib

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log("1/9", "查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"找不到游戏主窗口: {args.title}")
        return 2

    views = discover_game_views(parent.hwnd)
    log("2/9", f"扫描 WSGAME 实例: {len(views)} 个")
    if not 1 <= args.game_index <= len(views):
        print(f"game-index 必须在 1..{len(views)}")
        return 2

    manager = GameViewManager(parent.hwnd, timeout=2.0)
    capture = WindowsGraphicsCapture()
    original = manager.current_surface_index()
    foreground = int(ctypes.windll.user32.GetForegroundWindow())
    print(f"parent hwnd={parent.hwnd}")
    print(f"original_surface={original}")
    print(f"foreground_before={foreground}")

    def capture_step(label: str) -> bool:
        log(label, "WGC 捕获")
        try:
            frame = capture.capture(parent.hwnd)
            path = output_dir / f"{label.replace('/', '-')}.png"
            save_png(frame, path)
            print(f"  size={frame.width}x{frame.height}")
            print(f"  output={path}")
            return True
        except Exception as exc:
            print(f"  ERROR={type(exc).__name__}: {exc}")
            return False

    ok1 = capture_step("3-9 before-1")
    ok2 = capture_step("4-9 before-2")

    log("5/9", f"后台切换 WSGAME #{args.game_index}（只改 Surface，不改原生 Tab）")
    manager.switch_surface_to(args.game_index)
    time.sleep(0.25)
    print(f"surface_after_switch={manager.current_surface_index()}")
    print(f"tab_index_observed={manager.current_index()}")

    ok3 = capture_step("6-9 after-switch")

    log("7/9", f"恢复原始 Surface #{original}")
    manager.switch_surface_to(original)
    time.sleep(0.25)
    print(f"surface_after_restore={manager.current_surface_index()}")
    ok4 = capture_step("8-9 after-restore")

    foreground_after = int(ctypes.windll.user32.GetForegroundWindow())
    log("9/9", "诊断完成")
    print(f"capture_results=before1:{ok1},before2:{ok2},after_switch:{ok3},after_restore:{ok4}")
    print(f"foreground_after={foreground_after}")
    print(f"foreground_unchanged={foreground_after == foreground}")
    return 0 if all((ok1, ok2, ok3, ok4)) and foreground_after == foreground else 1


if __name__ == "__main__":
    raise SystemExit(main())
