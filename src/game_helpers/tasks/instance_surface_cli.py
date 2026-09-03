"""Diagnose distinct rendered surfaces for 梦幻西游 WSGAME instances."""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

from ..capture import WindowsGraphicsCapture, save_png
from ..core.game_view import discover_game_views
from ..core.view_manager import GameViewManager
from ..core.window import find_window


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare rendered surfaces of 梦幻西游 WSGAME instances."
    )
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output-dir", default="diagnostic/instance_surfaces")
    parser.add_argument("--settle-delay", type=float, default=0.35)
    args = parser.parse_args()

    if sys.platform != "win32":
        print("instance surface diagnosis requires Windows")
        return 2

    print("[验证] 1/7 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"parent window not found: {args.title!r}")
        return 2
    print(f"parent hwnd={parent.hwnd}")

    print("[验证] 2/7 扫描 WSGAME 实例")
    views = discover_game_views(parent.hwnd)
    print(f"WSGAME instances={len(views)}")
    if len(views) < 2:
        print("至少需要两个 WSGAME 实例才能验证实例 Surface 可区分性。")
        return 3
    for view in views:
        print(
            f"  #{view.index} hwnd={view.hwnd} visible={view.window.visible} "
            f"title={view.window.title!r}"
        )

    print("[验证] 3/7 记录原始 Surface 与前台")
    import ctypes

    manager = GameViewManager(parent.hwnd, timeout=2.0)
    foreground_before = int(ctypes.windll.user32.GetForegroundWindow())
    original_surface = manager.current_surface_index()
    print(f"original_surface={original_surface}")
    print(f"foreground_before={foreground_before}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    capture = WindowsGraphicsCapture()
    frames: list[tuple[int, str]] = []
    result = 0
    try:
        print("[验证] 4/7 逐个后台切换并捕获实际 Surface")
        for view in views:
            manager.switch_surface_to(view.index)
            time.sleep(args.settle_delay)
            surface = manager.current_surface_index()
            foreground_now = int(ctypes.windll.user32.GetForegroundWindow())
            print(
                f"  Surface #{view.index}: visible_surface={surface} "
                f"foreground={foreground_now}"
            )
            if surface != view.index:
                print(f"  FAILED: requested Surface #{view.index}, got #{surface}")
                result = 4
                break
            if foreground_now != foreground_before:
                print("  FAILED: foreground window changed")
                result = 5
                break

            frame = capture.capture(parent.hwnd)
            digest = hashlib.sha256(frame.data).hexdigest()
            output = output_dir / f"surface-{view.index}.png"
            save_png(frame, output)
            frames.append((view.index, digest))
            print(f"    sha256={digest[:16]}")
            print(f"    output={output}")
    except Exception as exc:
        print(f"capture failed: {type(exc).__name__}: {exc}")
        result = 6
    finally:
        print("[验证] 5/7 恢复原始 Surface")
        try:
            manager.switch_surface_to(original_surface)
            restored = manager.current_surface_index() == original_surface
        except Exception as exc:
            print(f"restore failed: {type(exc).__name__}: {exc}")
            restored = False
        foreground_final = int(ctypes.windll.user32.GetForegroundWindow())
        print(f"restored_surface={manager.current_surface_index() if restored else None}")
        print(f"foreground_final={foreground_final}")

    print("[验证] 6/7 比较不同实例的实际画面")
    unique_hashes = len({digest for _, digest in frames})
    distinct = len(frames) == len(views) and unique_hashes == len(frames)
    foreground_unchanged = foreground_final == foreground_before
    restored_ok = restored and manager.current_surface_index() == original_surface
    print(f"unique_surface_frames={unique_hashes}/{len(frames)}")
    print(f"surfaces_distinct={distinct}")
    print(f"foreground_unchanged={foreground_unchanged}")
    print(f"restored={restored_ok}")

    print("[验证] 7/7 结果")
    passed = result == 0 and distinct and foreground_unchanged and restored_ok
    print(f"result={'PASSED' if passed else 'FAILED'}")
    return 0 if passed else (result or 7)


if __name__ == "__main__":
    raise SystemExit(main())
