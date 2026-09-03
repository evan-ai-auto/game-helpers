"""Probe the relationship between WSGAME identity and the rendered surface.

This is intentionally a diagnostic tool, not a task executor. A WSGAME child
window's title/PID identify the hosted game instance, but the pixels returned
by a child capture API may belong to the currently rendered tab. The probe
therefore switches the visible WSGAME surface without foreground activation
and captures the *parent* window after each switch.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time

from game_helpers.core import GameViewManager, discover_game_views, find_window

from .png import save_png
from .wgc import WindowsGraphicsCapture


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate WSGAME identity against the actually rendered parent surface"
    )
    parser.add_argument("title", help="full or partial top-level window title")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="diagnostic\\render_binding",
        help="directory for captured parent-window PNGs",
    )
    parser.add_argument(
        "--settle-ms",
        type=int,
        default=300,
        help="delay after background surface switching before capture",
    )
    args = parser.parse_args()

    if sys.platform != "win32":
        parser.error("render_binding_probe requires Windows")

    window = find_window(args.title)
    if window is None:
        parser.error(f"top-level window not found: {args.title!r}")

    views = discover_game_views(window.hwnd)
    if not views:
        parser.error("no WSGAME children were discovered")

    manager = GameViewManager(window.hwnd)
    capture = WindowsGraphicsCapture()

    import ctypes
    import os

    user32 = ctypes.windll.user32
    foreground_before = int(user32.GetForegroundWindow())
    original_surface = manager.current_surface_index()
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"parent hwnd={window.hwnd} title={window.title!r}")
    print(f"foreground before={foreground_before}")
    print(f"original visible WSGAME=#{original_surface}")
    print(f"WSGAME children discovered: {len(views)}")
    print()

    results: list[tuple[int, str, str, int]] = []
    try:
        for index, view in enumerate(views, start=1):
            # Re-discover immediately before switching so stale child metadata
            # is less likely to be mistaken for the current window state.
            current_views = manager.views()
            if index > len(current_views):
                raise RuntimeError("WSGAME child count changed during probe")
            view = current_views[index - 1]

            print(f"WSGAME #{index}")
            print(f"  hwnd={view.hwnd}")
            print(f"  pid={view.window.pid}")
            print(f"  title={view.window.title!r}")
            print(f"  bounds={view.window.bounds.width}x{view.window.bounds.height}")

            selected = manager.switch_surface_to(index)
            time.sleep(max(args.settle_ms, 0) / 1000.0)

            foreground_after_switch = int(user32.GetForegroundWindow())
            if foreground_after_switch != foreground_before:
                raise RuntimeError(
                    "foreground window changed during background switch: "
                    f"before={foreground_before}, after={foreground_after_switch}"
                )

            frame = capture.capture(window)
            digest = _sha256(frame.data)
            output = os.path.join(args.output_dir, f"surface{index}.png")
            save_png(frame, output)
            results.append((index, view.window.title, digest, len(frame.data)))

            print(f"  visible surface=#{manager.current_surface_index()}")
            print(f"  parent capture={frame.width}x{frame.height}")
            print(f"  frame_sha256={digest}")
            print(f"  output={output}")
            print()

    finally:
        # Restore the originally visible child. Do not activate the host.
        try:
            manager.switch_surface_to(original_surface)
        except Exception as exc:  # pragma: no cover - diagnostic cleanup path
            print(f"WARNING: failed to restore WSGAME #{original_surface}: {exc}")

    foreground_final = int(user32.GetForegroundWindow())
    print("Render binding comparison:")
    if len(results) >= 2:
        first_sha = results[0][2]
        for index, title, digest, _ in results:
            relation = "SAME_AS_#1" if digest == first_sha else "DIFFERENT_FROM_#1"
            print(f"  #{index}: {relation}; title={title!r}; sha={digest}")
    else:
        print("  only one WSGAME child was discovered")

    print()
    print(f"foreground final={foreground_final}")
    print(f"foreground unchanged={foreground_final == foreground_before}")
    print(f"surface restored=#{manager.current_surface_index()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
