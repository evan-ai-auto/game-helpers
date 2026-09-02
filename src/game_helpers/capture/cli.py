"""Command-line utilities for inspecting and capturing a named window."""

from __future__ import annotations

import argparse

from game_helpers.core import discover_game_views, find_window, list_child_windows

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
    parser.add_argument(
        "--game-index",
        type=int,
        choices=range(1, 100),
        help="capture the Nth WSGAME child instead of the top-level window",
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

    target = window
    if args.game_index is not None:
        views = discover_game_views(window.hwnd)
        if args.game_index > len(views):
            parser.error(
                f"game view index {args.game_index} not found; "
                f"discovered {len(views)} WSGAME views"
            )
        view = views[args.game_index - 1]
        target = view.window
        print(
            f"selected game view #{view.index}: hwnd={view.hwnd} "
            f"active={view.active} bounds={view.window.bounds}"
        )

    frame = PrintWindowCapture().capture(target)
    save_png(frame, args.output)
    print(
        f"captured {target.title!r} hwnd={target.hwnd} "
        f"{frame.width}x{frame.height} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
