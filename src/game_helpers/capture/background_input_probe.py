"""Probe whether a WSGAME child accepts background mouse messages."""

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
    parser = argparse.ArgumentParser(description="Post a background mouse click to one WSGAME child")
    parser.add_argument("title")
    parser.add_argument("x", type=int, help="x in target WSGAME client coordinates")
    parser.add_argument("y", type=int, help="y in target WSGAME client coordinates")
    parser.add_argument("output", nargs="?", default="background-input-after.png")
    parser.add_argument("--game-index", type=int, required=True, choices=range(1, 100))
    parser.add_argument("--settle-ms", type=int, default=500)
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

    # Expose only the requested render child without activating it.
    original = {view.hwnd: bool(user32.IsWindowVisible(view.hwnd)) for view in views}
    SW_HIDE = 0
    SW_SHOWNOACTIVATE = 4
    try:
        for view in views:
            user32.ShowWindow(view.hwnd, SW_SHOWNOACTIVATE if view.hwnd == target.hwnd else SW_HIDE)

        before = capture.capture(window)
        before_path = os.path.splitext(args.output)[0] + "-before.png"
        save_png(before, before_path)
        print(f"before sha={_sha(before.data)} output={before_path}")

        BackgroundInput(target.hwnd).click(args.x, args.y)
        time.sleep(max(0, args.settle_ms) / 1000.0)

        after = capture.capture(window)
        save_png(after, args.output)
        print(f"after sha={_sha(after.data)} output={args.output}")

        foreground_after = int(user32.GetForegroundWindow())
        print(f"foreground: {foreground_before} -> {foreground_after}")
        if foreground_after != foreground_before:
            raise RuntimeError("background input probe changed the foreground window")

        if before.data == after.data:
            print("result: no captured-pixel change; target may ignore WM_* mouse messages")
        else:
            print("result: captured pixels changed after background click")
    finally:
        for hwnd, visible in original.items():
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE if visible else SW_HIDE)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
