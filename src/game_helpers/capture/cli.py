"""Command-line utilities for inspecting and capturing a named window."""

from __future__ import annotations

import argparse

from game_helpers.core import (
    GameViewTabSession,
    diagnose_window,
    discover_game_views,
    find_window,
    list_child_windows,
)

from .printwindow import PrintWindowCapture
from .screen import ScreenCapture
from .png import save_png


def _print_diagnostics(hwnd: int, label: str) -> None:
    info = diagnose_window(hwnd)
    print(
        f"{label}: hwnd={info.hwnd} parent={info.parent_hwnd} owner={info.owner_hwnd} "
        f"root={info.root_hwnd} pid={info.process_id} tid={info.thread_id} "
        f"visible={info.visible} cloaked={info.cloaked} "
        f"style=0x{info.style:X} exstyle=0x{info.exstyle:X} "
        f"class={info.class_name!r} title={info.title!r}"
    )


def _capture_selected_view(window, view, output: str, *, backend: str) -> None:
    """Select a tab, capture its pixels, and crop the game surface."""
    capture = ScreenCapture() if backend == "screen" else PrintWindowCapture()
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
            f"captured {view.window.title!r} hwnd={view.hwnd} "
            f"{cropped_frame.width}x{cropped_frame.height} -> {output}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture or inspect a Windows window")
    parser.add_argument("title", help="full or partial top-level window title")
    parser.add_argument("output", nargs="?", default="capture.png", help="output PNG path")
    parser.add_argument("--children", action="store_true", help="list child windows and do not capture")
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="print Win32 hierarchy/process/style diagnostics and do not capture",
    )
    parser.add_argument(
        "--game-index",
        type=int,
        choices=range(1, 100),
        help="capture the Nth WSGAME child by selecting its tab first",
    )
    parser.add_argument(
        "--backend",
        choices=("printwindow", "screen"),
        default="printwindow",
        help="capture backend; screen reads the pixels currently visible on the desktop",
    )
    args = parser.parse_args()

    window = find_window(args.title)
    if window is None:
        parser.error(f"window not found: {args.title!r}")

    if args.diagnose:
        _print_diagnostics(window.hwnd, "top-level")
        for index, child in enumerate(list_child_windows(window.hwnd), 1):
            _print_diagnostics(child.hwnd, f"child[{index}]")
        return 0

    if args.children:
        children = list_child_windows(window.hwnd)
        print(f"parent hwnd={window.hwnd} title={window.title!r}: {len(children)} child windows")
        for child in children:
            print(
                f"  hwnd={child.hwnd} visible={child.visible} "
                f"class={child.class_name!r} title={child.title!r} bounds={child.bounds}"
            )
        return 0

    if args.game_index is None:
        capture = ScreenCapture() if args.backend == "screen" else PrintWindowCapture()
        frame = capture.capture(window)
        save_png(frame, args.output)
        print(f"captured {window.title!r} hwnd={window.hwnd} {frame.width}x{frame.height} -> {args.output}")
        return 0

    views = discover_game_views(window.hwnd)
    if args.game_index > len(views):
        parser.error(
            f"game view index {args.game_index} not found; discovered {len(views)} WSGAME views"
        )
    view = views[args.game_index - 1]
    print(
        f"selected game view #{view.index}: hwnd={view.hwnd} "
        f"active={view.active} bounds={view.window.bounds}"
    )
    _capture_selected_view(window, view, args.output, backend=args.backend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
