"""Capture each hosted WSGAME child with independent backends for diagnosis."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import sys
from pathlib import Path

from game_helpers.core import discover_game_views, find_window

from .png import save_png
from .printwindow import PrintWindowCapture
from .screen import ScreenCapture
from .wgc import WindowsGraphicsCapture


def _pid(hwnd: int) -> int:
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
    return int(pid.value)


def _try_capture(label: str, backend, window, output: Path):
    try:
        frame = backend.capture(window)
        save_png(frame, output)
        digest = hashlib.sha256(frame.data).hexdigest()[:16]
        return frame, f"{label}: OK backend={frame.backend} size={frame.width}x{frame.height} sha256={digest} -> {output}"
    except Exception as exc:  # diagnostics must continue after one backend fails
        return None, f"{label}: FAIL {type(exc).__name__}: {exc}"


def _diff_ratio(left, right) -> float | None:
    if left is None or right is None or left.width != right.width or left.height != right.height:
        return None
    a, b = left.data, right.data
    if len(a) != len(b) or not a:
        return None
    changed = sum(x != y for x, y in zip(a, b))
    return changed / len(a)


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

    views = discover_game_views(parent.hwnd)
    if not views:
        parser.error("no WSGAME child windows found")

    if args.index is not None:
        if args.index > len(views):
            parser.error(f"game view index must be between 1 and {len(views)}")
        views = [views[args.index - 1]]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    backends = [
        ("printwindow", PrintWindowCapture()),
        ("bitblt", ScreenCapture()),
        ("wgc", WindowsGraphicsCapture()),
    ]
    captures = {}

    print(f"parent hwnd={parent.hwnd} title={parent.title!r} pid={_pid(parent.hwnd)}")
    print(f"WSGAME children discovered: {len(discover_game_views(parent.hwnd))}")

    for view in views:
        print(
            f"\nWSGAME #{view.index}: hwnd={view.hwnd} pid={_pid(view.hwnd)} "
            f"visible={view.window.visible} bounds={view.window.bounds}"
        )
        captures[view.index] = {}
        for name, backend in backends:
            output = output_dir / f"wsgame{view.index}_{name}.png"
            frame, message = _try_capture(f"  {name}", backend, view.window, output)
            captures[view.index][name] = frame
            print(message)

    if len(captures) >= 2:
        print("\nCross-child comparison:")
        for backend_name in ("printwindow", "bitblt", "wgc"):
            left = captures.get(1, {}).get(backend_name)
            right = captures.get(2, {}).get(backend_name)
            ratio = _diff_ratio(left, right)
            if ratio is None:
                print(f"  {backend_name}: unavailable")
            else:
                print(f"  {backend_name}: child #1 vs #2 changed-byte ratio={ratio:.6f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
