"""Probe Win32 state before and after a user-driven hosted-view switch."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import time

from game_helpers.core import current_tab_index, discover_game_views, find_tab_control, find_window

from .printwindow import PrintWindowCapture


def _pid(hwnd: int) -> int:
    value = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(value))
    return int(value.value)


def _z_order(hwnd: int) -> list[int]:
    user32 = ctypes.windll.user32
    result: list[int] = []
    current = user32.GetWindow(user32.GetParent(int(hwnd)), 5) if False else user32.GetWindow(int(hwnd), 0)
    while current:
        result.append(int(current))
        current = user32.GetWindow(current, 2)
    return result


def _snapshot(parent_hwnd: int, tab_hwnd: int, views) -> dict:
    user32 = ctypes.windll.user32
    capture = PrintWindowCapture()
    data = {
        "time": time.time(),
        "foreground": int(user32.GetForegroundWindow()),
        "foreground_pid": _pid(user32.GetForegroundWindow()) if user32.GetForegroundWindow() else 0,
        "parent_visible": bool(user32.IsWindowVisible(parent_hwnd)),
        "parent_active": int(user32.GetActiveWindow()),
        "thread_active": int(user32.GetActiveWindow()),
        "tab_index": current_tab_index(tab_hwnd),
        "children": [],
    }
    for view in views:
        hwnd = int(view.hwnd)
        frame_sha = None
        try:
            frame = capture.capture(view.window)
            frame_sha = hashlib.sha256(frame.data).hexdigest()[:16]
        except Exception as exc:
            frame_sha = f"ERROR:{type(exc).__name__}"
        data["children"].append(
            {
                "index": view.index,
                "hwnd": hwnd,
                "pid": _pid(hwnd),
                "visible": bool(user32.IsWindowVisible(hwnd)),
                "enabled": bool(user32.IsWindowEnabled(hwnd)),
                "active": int(user32.GetActiveWindow()) == hwnd,
                "parent": int(user32.GetParent(hwnd)),
                "frame_sha": frame_sha,
            }
        )
    return data


def _print_snapshot(label: str, snapshot: dict) -> None:
    print(f"\n[{label}]")
    print(f"  foreground={snapshot['foreground']} pid={snapshot['foreground_pid']}")
    print(f"  parent_visible={snapshot['parent_visible']} active_window={snapshot['parent_active']}")
    print(f"  tab_index={snapshot['tab_index']}")
    for child in snapshot["children"]:
        print(
            f"  WSGAME #{child['index']}: hwnd={child['hwnd']} pid={child['pid']} "
            f"visible={child['visible']} enabled={child['enabled']} "
            f"frame_sha={child['frame_sha']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record hosted game-view state; press Enter after manually switching with Ctrl+Tab"
    )
    parser.add_argument("title", help="full or partial top-level window title")
    args = parser.parse_args()

    if __import__("sys").platform != "win32":
        parser.error("this probe requires Windows")

    parent = find_window(args.title)
    if parent is None:
        parser.error(f"window not found: {args.title!r}")
    tab = find_tab_control(parent.hwnd)
    if tab is None:
        parser.error("SysTabControl32 not found")

    views = discover_game_views(parent.hwnd)
    before = _snapshot(parent.hwnd, tab, views)
    _print_snapshot("BEFORE", before)

    print("\n现在请手动在游戏窗口中按一次 Ctrl+Tab，切换到另一个账号。")
    input("切换完成后按 Enter 继续... ")
    time.sleep(0.3)

    views_after = discover_game_views(parent.hwnd)
    after = _snapshot(parent.hwnd, tab, views_after)
    _print_snapshot("AFTER", after)

    print("\n[CHANGES]")
    for key in ("foreground", "foreground_pid", "parent_visible", "parent_active", "tab_index"):
        if before[key] != after[key]:
            print(f"  {key}: {before[key]!r} -> {after[key]!r}")
    for b, a in zip(before["children"], after["children"]):
        for key in ("visible", "enabled", "active", "frame_sha"):
            if b[key] != a[key]:
                print(f"  WSGAME #{b['index']} {key}: {b[key]!r} -> {a[key]!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
