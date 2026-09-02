"""Probe background mouse delivery using a hover-state change."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import sys
import time

from game_helpers.actions import BackgroundInput
from game_helpers.core import discover_game_views, find_window

from .png import save_png
from .wgc import WindowsGraphicsCapture


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post background mouse-move messages and inspect the hover state"
    )
    parser.add_argument("title")
    parser.add_argument("x", type=int, help="x in target WSGAME client coordinates")
    parser.add_argument("y", type=int, help="y in target WSGAME client coordinates")
    parser.add_argument("output_dir", nargs="?", default="background-hover")
    parser.add_argument("--game-index", type=int, required=True, choices=range(1, 100))
    parser.add_argument("--settle-ms", type=int, default=250)
    args = parser.parse_args()

    if sys.platform != "win32":
        parser.error("this probe requires Windows")

    window = find_window(args.title)
    if window is None:
        parser.error(f"window not found: {args.title!r}")
    views = discover_game_views(window.hwnd)
    if not 1 <= args.game_index <= len(views):
        parser.error(f"game index must be between 1 and {len(views)}")

    target = views[args.game_index - 1]
    user32 = ctypes.windll.user32
    foreground_before = int(user32.GetForegroundWindow())
    capture = WindowsGraphicsCapture()
    original = {view.hwnd: bool(user32.IsWindowVisible(view.hwnd)) for view in views}
    os.makedirs(args.output_dir, exist_ok=True)
    SW_HIDE = 0
    SW_SHOWNOACTIVATE = 4

    try:
        for view in views:
            user32.ShowWindow(view.hwnd, SW_SHOWNOACTIVATE if view.hwnd == target.hwnd else SW_HIDE)

        idle = capture.capture(window)
        idle_path = os.path.join(args.output_dir, "idle.png")
        save_png(idle, idle_path)
        print(f"idle sha={_sha(idle.data)} output={idle_path}")

        BackgroundInput(target.hwnd).mouse_move(args.x, args.y)
        time.sleep(max(0, args.settle_ms) / 1000.0)

        hover = capture.capture(window)
        hover_path = os.path.join(args.output_dir, "hover.png")
        save_png(hover, hover_path)
        print(f"hover sha={_sha(hover.data)} output={hover_path}")

        foreground_after = int(user32.GetForegroundWindow())
        print(f"foreground: {foreground_before} -> {foreground_after}")
        if foreground_after != foreground_before:
            raise RuntimeError("background hover probe changed the foreground window")

        print("result: pixels changed; inspect idle.png vs hover.png for a deterministic hover-state change")
    finally:
        for hwnd, visible in original.items():
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE if visible else SW_HIDE)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
