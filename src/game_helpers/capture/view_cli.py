"""CLI for switching hosted game views and capturing the parent window."""

from __future__ import annotations

import argparse

from game_helpers.core import GameViewManager, discover_game_views, find_window

from .png import save_png
from .wgc import WindowsGraphicsCapture


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Switch a hosted game view without foreground activation and capture the parent window"
    )
    parser.add_argument("title", help="full or partial top-level window title")
    parser.add_argument("output", nargs="?", default="view.png", help="output PNG path")
    parser.add_argument("--game-index", type=int, required=True, choices=range(1, 100))
    parser.add_argument("--switch-only", action="store_true", help="switch and report the view without capturing")
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="fallback to foreground Ctrl+Tab switching for applications that ignore direct tab selection",
    )
    args = parser.parse_args()

    window = find_window(args.title)
    if window is None:
        parser.error(f"window not found: {args.title!r}")

    views = discover_game_views(window.hwnd)
    if args.game_index > len(views):
        parser.error(
            f"game view index {args.game_index} not found; discovered {len(views)} WSGAME views"
        )

    manager = GameViewManager(
        window.hwnd,
        activate_before_switch=args.foreground,
    )
    before = manager.current_index()
    selected = manager.switch_to(args.game_index)
    after = manager.current_index()
    print(
        f"game view: #{before} -> #{after}; hwnd={selected.hwnd} "
        f"pid-bound view={selected.window.class_name!r}"
    )

    if args.switch_only:
        return 0

    frame = WindowsGraphicsCapture().capture(window)
    save_png(frame, args.output)
    print(
        f"captured parent hwnd={window.hwnd} {frame.width}x{frame.height} "
        f"backend={frame.backend} -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
