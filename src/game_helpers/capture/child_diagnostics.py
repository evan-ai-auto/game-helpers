"""Capture each hosted WSGAME child with independent backends for diagnosis."""

from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

from game_helpers.core import discover_game_views, find_window

from .png import save_png
from .printwindow import PrintWindowCapture
from .screen import ScreenCapture
from .wgc import WindowsGraphicsCapture


def _pid(hwnd: int) -> int:
    process_id = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value)


def _try_capture(label: str, backend, window, output: Path) -> str:
    try:
        frame = backend.capture(window)
        save_png(frame, output)
        return f"{label}: OK backend={frame.backend} size={frame.width}x{frame.height} -> {output}"
    except Exception as exc:  # diagnostics must continue after one backend fails
        return f"{label}: FAIL {type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture each WSGAME child directly with PrintWindow, BitBlt and WGC"
    )
    parser.add_argument("title", help="full or partial top-level window title")
    parser.add_argument("output_dir", nargs="?", default="diagnostic", help="output directory")
    parser.add_argument("--index", type=int, choices=range(1, 100), help="only test one WSGAME child")
    args = parser.parse_args()

    if sys.platform != "win32":
        parser.error("this diagnostic requires Windows")

    parent = find_window(args.title)
    if parent is None:
        parser.error(f"window not found: {args.title!r}")

    all_views = discover_game_views(parent.hwnd)
    if not all_views:
        parser.error("no WSGAME child windows found")
    if args.index is not None:
        if args.index > len(all_views):
            parser.error(f"game view index must be between 1 and {len(all_views)}")
        views = [all_views[args.index - 1]]
    else:
        views = all_views

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    backends = [
        ("printwindow", PrintWindowCapture()),
        ("bitblt", ScreenCapture()),
        ("wgc", WindowsGraphicsCapture()),
    ]

    print(f"parent hwnd={parent.hwnd} title={parent.title!r} pid={_pid(parent.hwnd)}")
    print(f"WSGAME children discovered: {len(all_views)}")

    for view in views:
        print(
            f"\nWSGAME #{view.index}: hwnd={view.hwnd} pid={_pid(view.hwnd)} "
            f"visible={view.window.visible} bounds={view.window.bounds}"
        )
        for name, backend in backends:
            output = output_dir / f"wsgame{view.index}_{name}.png"
            print(_try_capture(f"  {name}", backend, view.window, output))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
