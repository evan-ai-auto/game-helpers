"""Command-line utilities for inspecting and capturing a named window."""

from __future__ import annotations

import argparse

from game_helpers.core import (
    GameViewTabSession,
    discover_game_views,
    find_window,
    list_child_windows,
)

from .png import save_png
from .printwindow import PrintWindowCapture


def _capture_selected_view(window, view, output: str) -> None:
    """Capture the tabbed parent and crop the selected 800x600 game surface."""
    capture = PrintWindowCapture()
    with GameViewTabSession(window.hwnd, view.hwnd):
        frame = capture.capture(window)

        parent = window.bounds
        target = view.window.bounds
        left = target.left - parent.left
        top = target.top - parent.top
        right = target.right - parent.left
        bottom = target.bottom - parent.top
        if not (0 <= left < right <= frame.width and 0 <= top < bottom <= frame.height):
            raise RuntimeError(
                "selected game view is outside the captured parent window: "
                f"parent={parent} target={target} frame={frame.width}x{frame.height}"
            )

        row_bytes = frame.width * 4
        crop_width = right - left
        cropped = bytearray()
        for y in range(top, bottom):
            start = y * row_bytes + left * 4
            cropped.extend(frame.data[start : start + crop_width * 4])

        from game_helpers.capture.models import Frame

        cropped_frame = Frame(
            window=view.window,
            width=crop_width,
            height=bottom - top,
            data=bytes(cropped),
            captured_at=frame.captured_at,
            backend=f"{frame.backend}:parent-crop",
        )
        save_png(cropped_frame, output)
        print(
            f"captured {view.title!r} hwnd={view.hwnd} "
            f"{cropped_frame.width}x{cropped_frame.height} -> {output}"
        )


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
        help="capture the Nth WSGAME child by selecting its tab first",
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

    if args.game_index is None:
        frame = PrintWindowCapture().capture(window)
        save_png(frame, args.output)
        print(
            f"captured {window.title!r} hwnd={window.hwnd} "
            f"{frame.width}x{frame.height} -> {args.output}"
        )
        return 0

    views = discover_game_views(window.hwnd)
    if args.game_index > len(views):
        parser.error(
            f"game view index {args.game_index} not found; "
            f"discovered {len(views)} WSGAME views"
        )
    view = views[args.game_index - 1]
    print(
        f"selected game view #{view.index}: hwnd={view.hwnd} "
        f"active={view.active} bounds={view.window.bounds}"
    )
    _capture_selected_view(window, view, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
