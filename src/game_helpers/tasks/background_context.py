"""Reusable background session helpers verified by the 800x600 min chain."""
from __future__ import annotations

import sys
from dataclasses import dataclass

from ..core.view_manager import GameViewManager


def foreground_hwnd() -> int:
    if sys.platform != "win32":
        raise RuntimeError("foreground query requires Windows")
    import ctypes

    return int(ctypes.windll.user32.GetForegroundWindow())


@dataclass
class ViewRestorePoint:
    """Surface + tab indices to restore after a background operation."""

    surface_index: int
    tab_index: int


def capture_view_restore_point(manager: GameViewManager) -> ViewRestorePoint:
    return ViewRestorePoint(
        surface_index=manager.current_surface_index(),
        tab_index=manager.current_index(),
    )


def restore_view(manager: GameViewManager, point: ViewRestorePoint) -> tuple[bool, bool]:
    """Restore surface then tab. Returns (surface_ok, tab_ok)."""
    manager.switch_surface_to(point.surface_index)
    manager.switch_to(point.tab_index)
    return (
        manager.current_surface_index() == point.surface_index,
        manager.current_index() == point.tab_index,
    )


@dataclass
class BackgroundRunGuard:
    """Save foreground + view, then restore after a background workflow step."""

    manager: GameViewManager
    foreground_before: int
    restore_point: ViewRestorePoint

    @classmethod
    def begin(cls, manager: GameViewManager) -> "BackgroundRunGuard":
        return cls(
            manager=manager,
            foreground_before=foreground_hwnd(),
            restore_point=capture_view_restore_point(manager),
        )

    def finish(self, *, restore_foreground: bool = True) -> dict[str, bool]:
        try:
            surface_ok, tab_ok = restore_view(self.manager, self.restore_point)
        except Exception:
            surface_ok, tab_ok = False, False

        foreground_restored = True
        if restore_foreground and self.foreground_before and foreground_hwnd() != self.foreground_before:
            # Surface/tab flips can occasionally steal focus; put the original
            # foreground window back so normal automation stays background-safe.
            try:
                from .manual_coordinate import set_foreground

                set_foreground(self.foreground_before)
                foreground_restored = foreground_hwnd() == self.foreground_before
            except Exception:
                foreground_restored = False

        foreground_ok = foreground_hwnd() == self.foreground_before
        return {
            "restored_surface": surface_ok,
            "restored_tab": tab_ok,
            "foreground_unchanged": foreground_ok,
            "foreground_restored": foreground_restored,
        }
