"""Background input adapter for Win32 child windows."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class BackgroundInput:
    """Send ordinary mouse/keyboard messages directly to a target Win32 window."""

    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    MK_LBUTTON = 0x0001
    VK_MENU = 0x12
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_E = 0x45

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

    @staticmethod
    def _key_lparam(*, repeat: int = 1, scan_code: int = 0, extended: bool = False, previous: bool = False, transition: bool = False) -> int:
        """Build the standard keyboard message LPARAM bit fields."""
        value = int(repeat) & 0xFFFF
        value |= (int(scan_code) & 0xFF) << 16
        if extended:
            value |= 1 << 24
        if previous:
            value |= 1 << 30
        if transition:
            value |= 1 << 31
        return value

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

    def key_sync(self, virtual_key: int, *, alt: bool = False, scan_code: int = 0) -> None:
        """Synchronously deliver one ordinary key, optionally with Alt held."""
        vk = int(virtual_key)
        if alt:
            self._send(self.WM_SYSKEYDOWN, self.VK_MENU, self._key_lparam(scan_code=0x38))
        message_down = self.WM_SYSKEYDOWN if alt else self.WM_KEYDOWN
        message_up = self.WM_SYSKEYUP if alt else self.WM_KEYUP
        self._send(message_down, vk, self._key_lparam(scan_code=scan_code))
        self._send(message_up, vk, self._key_lparam(scan_code=scan_code, previous=True, transition=True))
        if alt:
            self._send(self.WM_SYSKEYUP, self.VK_MENU, self._key_lparam(scan_code=0x38, previous=True, transition=True))

    def alt_e_sync(self) -> None:
        """Synchronously send the Alt+E system-key sequence to this HWND."""
        self.key_sync(self.VK_E, alt=True, scan_code=0x12)

    def _post(self, message: int, wparam: int, lparam: int) -> None:
        if not self.user32.PostMessageW(self.hwnd, message, wparam, lparam):
            raise ctypes.WinError()

    def _send(self, message: int, wparam: int, lparam: int) -> int:
        return int(self.user32.SendMessageW(self.hwnd, message, wparam, lparam))
