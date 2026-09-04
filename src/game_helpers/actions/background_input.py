"""Background input adapter for Win32 child windows."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class BackgroundInput:
    """Send ordinary mouse messages directly to a target Win32 window."""

    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    MK_LBUTTON = 0x0001

    def __init__(self, hwnd: int) -> None:
        if sys.platform != "win32":
            raise RuntimeError("BackgroundInput requires Windows")
        self.hwnd = int(hwnd)
        self.user32 = ctypes.windll.user32
        # ctypes.wintypes does not define LRESULT on all Python/Windows builds.
        # LRESULT is pointer-sized signed integer on Win64.
        lresult = ctypes.c_ssize_t
        for name in ("PostMessageW", "SendMessageW"):
            fn = getattr(self.user32, name)
            fn.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            fn.restype = lresult

    @staticmethod
    def _lparam(x: int, y: int) -> int:
        """Pack signed 16-bit client coordinates into LPARAM."""
        x16 = ctypes.c_short(int(x)).value & 0xFFFF
        y16 = ctypes.c_short(int(y)).value & 0xFFFF
        return x16 | (y16 << 16)

    def mouse_move(self, x: int, y: int) -> None:
        self._post(self.WM_MOUSEMOVE, 0, self._lparam(x, y))

    def click(self, x: int, y: int) -> None:
        """Post a left click at child-client coordinates."""
        lparam = self._lparam(x, y)
        self._post(self.WM_MOUSEMOVE, 0, lparam)
        self._post(self.WM_LBUTTONDOWN, self.MK_LBUTTON, lparam)
        self._post(self.WM_LBUTTONUP, 0, lparam)

    def click_sync(self, x: int, y: int) -> None:
        """Synchronously deliver a left click without activating the window."""
        lparam = self._lparam(x, y)
        self._send(self.WM_MOUSEMOVE, 0, lparam)
        self._send(self.WM_LBUTTONDOWN, self.MK_LBUTTON, lparam)
        self._send(self.WM_LBUTTONUP, 0, lparam)

    def _post(self, message: int, wparam: int, lparam: int) -> None:
        if not self.user32.PostMessageW(self.hwnd, message, wparam, lparam):
            raise ctypes.WinError()

    def _send(self, message: int, wparam: int, lparam: int) -> int:
        return int(self.user32.SendMessageW(self.hwnd, message, wparam, lparam))
