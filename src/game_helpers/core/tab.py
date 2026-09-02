"""Win32 tab-control helpers for hosted game views.

The game application uses a standard ``SysTabControl32`` and keeps only the
selected ``WSGAME`` child visible. A hidden WSGAME child may not have an
independent rendered surface, so capturing it directly can return the
currently displayed game's pixels. The safe first implementation therefore
selects the requested tab through the normal tab-control state/notification
path, waits for the corresponding child to become visible, and restores the
original tab on exit.
"""

from __future__ import annotations

import sys
import time

from .children import list_child_windows


def find_tab_control(parent_hwnd: int) -> int | None:
    """Return the first standard SysTabControl32 child of ``parent_hwnd``."""
    for child in list_child_windows(parent_hwnd, visible_only=False):
        if child.class_name.lower() == "systabcontrol32":
            return child.hwnd
    return None


def current_tab_index(tab_hwnd: int) -> int:
    """Return the zero-based selected tab index."""
    if sys.platform != "win32":
        raise RuntimeError("tab control operations are only available on Windows")

    import ctypes

    TCM_GETCURSEL = 0x130B
    return int(ctypes.windll.user32.SendMessageW(tab_hwnd, TCM_GETCURSEL, 0, 0))


def _notify_tab_parent(tab_hwnd: int, code: int) -> int:
    """Send a standard tab-control notification to its parent window."""
    import ctypes
    from ctypes import wintypes

    class NMHDR(ctypes.Structure):
        _fields_ = [
            ("hwndFrom", wintypes.HWND),
            ("idFrom", wintypes.UINT_PTR),
            ("code", wintypes.UINT),
        ]

    WM_NOTIFY = 0x004E
    parent = ctypes.windll.user32.GetParent(tab_hwnd)
    if not parent:
        raise RuntimeError(f"could not find parent for tab control {tab_hwnd}")

    hdr = NMHDR(
        hwndFrom=tab_hwnd,
        idFrom=ctypes.windll.user32.GetDlgCtrlID(tab_hwnd),
        code=code,
    )
    return int(ctypes.windll.user32.SendMessageW(parent, WM_NOTIFY, hdr.idFrom, ctypes.byref(hdr)))


def select_tab(tab_hwnd: int, index: int) -> None:
    """Select a tab through TCM_SETCURSEL and send normal tab notifications.

    ``TCM_SETCURSEL`` changes the tab selection but, by design, does not send
    ``TCN_SELCHANGING``/``TCN_SELCHANGE``. The hosted game appears to use those
    notifications to switch the visible WSGAME child. Sending mouse messages
    to the tab control was unreliable here: the tab item rectangle could not
    be queried, and the attempted click could destabilize the game window.
    """
    if sys.platform != "win32":
        raise RuntimeError("tab control operations are only available on Windows")
    if index < 0:
        raise ValueError("tab index must be non-negative")

    import ctypes

    TCN_SELCHANGING = -551
    TCN_SELCHANGE = -552
    TCM_SETCURSEL = 0x130C

    # Let the parent veto the transition using the normal tab-control
    # notification protocol before changing the selection.
    if _notify_tab_parent(tab_hwnd, TCN_SELCHANGING):
        raise RuntimeError(f"tab {index} change was vetoed by the parent")

    result = ctypes.windll.user32.SendMessageW(tab_hwnd, TCM_SETCURSEL, index, 0)
    if result == -1:
        raise RuntimeError(f"could not select tab {index}")

    # TCM_SETCURSEL intentionally does not emit TCN_SELCHANGE, so notify the
    # parent explicitly so applications that switch child pages from this
    # notification can perform their normal view activation.
    _notify_tab_parent(tab_hwnd, TCN_SELCHANGE)


def wait_for_game_view(parent_hwnd: int, game_hwnd: int, *, timeout: float = 2.0) -> bool:
    """Wait until the requested WSGAME child becomes visible."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for child in list_child_windows(parent_hwnd, visible_only=False):
            if child.hwnd == game_hwnd:
                return child.visible
        time.sleep(0.02)
    return False


class GameViewTabSession:
    """Temporarily activate a game tab and restore the original tab on exit."""

    def __init__(self, parent_hwnd: int, target_game_hwnd: int, *, timeout: float = 2.0):
        self.parent_hwnd = parent_hwnd
        self.target_game_hwnd = target_game_hwnd
        self.timeout = timeout
        self.tab_hwnd: int | None = None
        self.original_index: int | None = None

    def __enter__(self) -> "GameViewTabSession":
        self.tab_hwnd = find_tab_control(self.parent_hwnd)
        if self.tab_hwnd is None:
            raise RuntimeError("SysTabControl32 was not found")

        from .game_view import discover_game_views

        views = discover_game_views(self.parent_hwnd)
        target_index = next((i for i, view in enumerate(views) if view.hwnd == self.target_game_hwnd), None)
        if target_index is None:
            raise RuntimeError(f"game window {self.target_game_hwnd} is not a discovered WSGAME child")

        self.original_index = current_tab_index(self.tab_hwnd)
        if self.original_index != target_index:
            select_tab(self.tab_hwnd, target_index)
            if not wait_for_game_view(self.parent_hwnd, self.target_game_hwnd, timeout=self.timeout):
                raise RuntimeError(f"game view {target_index + 1} did not become visible")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.tab_hwnd is None or self.original_index is None:
            return
        if current_tab_index(self.tab_hwnd) != self.original_index:
            try:
                select_tab(self.tab_hwnd, self.original_index)
                wait_for_game_view(self.parent_hwnd, self._current_game_hwnd(), timeout=self.timeout)
            except Exception:
                # Never mask the original capture/action exception while
                # attempting best-effort restoration of the previous tab.
                pass

    def _current_game_hwnd(self) -> int:
        """Return the WSGAME HWND corresponding to the current tab index."""
        from .game_view import discover_game_views

        views = discover_game_views(self.parent_hwnd)
        index = current_tab_index(self.tab_hwnd)  # type: ignore[arg-type]
        if index < 0 or index >= len(views):
            return self.target_game_hwnd
        return views[index].hwnd
