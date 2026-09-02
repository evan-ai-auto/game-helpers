"""Command-line utilities for inspecting and capturing a named window."""

from __future__ import annotations

import argparse

from game_helpers.core import find_window, list_child_windows

from .png import save_png
from .printwindow import PrintWindowCapture


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture or inspect a Windows window")
    parser.add_argument("title", help="full or partial top-level window title")
    parser.add_argument("output", nargs="?", default="capture.png", help="output PNG path")
    parser.add_argument(
        "--children",
        action="store_true",
        help="list child windows and do not capture",
    )
    args = parser.parse_args()

    window = find_window(args.title)
    if window is None:
        parser.error(f"window not found: {args.title!r}")

    if args.children:
        children = list_child_windows(window.hwnd)
        print(
            f"parent hwnd={window.hwnd} title={window.title!r}: "
            f"{len(children)} child windows"
        )
        for child in children:
            print(
                f"  hwnd={child.hwnd} visible={child.visible} "
                f"class={child.class_name!r} title={child.title!r} "
                f"bounds={child.bounds}"
            )
        return 0

    frame = PrintWindowCapture().capture(window)
    save_png(frame, args.output)
    print(
        f"captured {window.title!r} hwnd={window.hwnd} "
        f"{frame.width}x{frame.height} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
