"""Probe background hosted-view switching and repaint strategies."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import sys
import time
from dataclasses import dataclass

from game_helpers.core import discover_game_views, find_window

from .png import save_png
from .wgc import WindowsGraphicsCapture


@dataclass(frozen=True)
class Variant:
    name: str
    z_order: bool
    repaint: bool


VARIANTS = (
    Variant("visibility", z_order=False, repaint=False),
    Variant("visibility-repaint", z_order=False, repaint=True),
    Variant("visibility-zorder-repaint", z_order=True, repaint=True),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _set_visibility(user32, views, target_hwnd: int) -> None:
    SW_HIDE = 0
    SW_SHOWNOACTIVATE = 4
    for view in views:
        user32.ShowWindow(view.hwnd, SW_SHOWNOACTIVATE if view.hwnd == target_hwnd else SW_HIDE)


def _repaint(user32, hwnd: int) -> None:
    RDW_INVALIDATE = 0x0001
    RDW_ERASE = 0x0004
    RDW_UPDATENOW = 0x0100
    RDW_ALLCHILDREN = 0x0080
    RDW_FRAME = 0x0400
    flags = RDW_INVALIDATE | RDW_ERASE | RDW_UPDATENOW | RDW_ALLCHILDREN | RDW_FRAME
    user32.RedrawWindow(hwnd, None, None, flags)
    user32.UpdateWindow(hwnd)


def _raise_child_to_front(user32, hwnd: int, parent_hwnd: int) -> None:
    HWND_TOP = 0
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    if not user32.SetWindowPos(
        hwnd,
        HWND_TOP,
        0,
        0,
        0,
        0,
        SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
    ):
        raise ctypes.WinError()


def _capture_parent(user32, capture, window, output, *, foreground_before: int) -> str:
    frame = capture.capture(window)
    foreground_after = int(user32.GetForegroundWindow())
    if foreground_after != foreground_before:
        raise RuntimeError(
            "foreground window changed during probe: "
            f"before={foreground_before}, after={foreground_after}"
        )
    save_png(frame, output)
    return _sha256(frame.data)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe background WSGAME visibility, repaint and z-order strategies"
    )
    parser.add_argument("title", help="full or partial top-level window title")
    parser.add_argument("output_dir", nargs="?", default="surface-probe")
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
    capture = WindowsGraphicsCapture()
    original_visible = {view.hwnd: bool(user32.IsWindowVisible(view.hwnd)) for view in views}
    original_prev = {
        view.hwnd: int(user32.GetWindow(view.hwnd, 3))  # GW_HWNDPREV
        for view in views
    }
    foreground_before = int(user32.GetForegroundWindow())

    import os

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"parent hwnd={window.hwnd} title={window.title!r}")
    print(f"target game #{args.game_index} hwnd={target.hwnd} pid={target.metadata.get('pid', '?') if hasattr(target, 'metadata') else '?'}")
    print(f"foreground before={foreground_before}")

    try:
        for variant in VARIANTS:
            _set_visibility(user32, views, target.hwnd)
            if variant.z_order:
                _raise_child_to_front(user32, target.hwnd, window.hwnd)
            if variant.repaint:
                _repaint(user32, target.hwnd)
                _repaint(user32, window.hwnd)
            time.sleep(max(0, args.settle_ms) / 1000.0)

            output = os.path.join(args.output_dir, f"game-{args.game_index}-{variant.name}.png")
            sha = _capture_parent(user32, capture, window, output, foreground_before=foreground_before)
            print(f"{variant.name}: sha={sha} output={output}")
    finally:
        for hwnd, visible in original_visible.items():
            user32.ShowWindow(hwnd, 4 if visible else 0)  # SW_SHOWNOACTIVATE / SW_HIDE
        # Best-effort restoration of each child's previous sibling relationship.
        for hwnd, prev in original_prev.items():
            if prev:
                SWP_NOSIZE = 0x0001
                SWP_NOMOVE = 0x0002
                SWP_NOACTIVATE = 0x0010
                user32.SetWindowPos(hwnd, prev, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
