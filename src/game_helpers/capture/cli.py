"""Command-line utility for capturing a named top-level window."""

from __future__ import annotations

import argparse

from game_helpers.core import find_window

from .png import save_png
from .printwindow import PrintWindowCapture


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a Windows window to PNG")
    parser.add_argument("title", help="full or partial window title")
    parser.add_argument("output", nargs="?", default="capture.png", help="output PNG path")
    args = parser.parse_args()

    window = find_window(args.title)
    if window is None:
        parser.error(f"window not found: {args.title!r}")

    frame = PrintWindowCapture().capture(window)
    save_png(frame, args.output)
    print(
        f"captured {window.title!r} hwnd={window.hwnd} "
        f"{frame.width}x{frame.height} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
