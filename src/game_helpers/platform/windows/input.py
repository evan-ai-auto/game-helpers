"""Win32 background input transport."""

from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass
from ctypes import wintypes
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class BackgroundClickVerification:
    dispatched: bool
    verified: bool
    elapsed: float
    timeout: float
    value: T | None = None

    @property
    def timed_out(self) -> bool:
        return self.dispatched and not self.verified


class BackgroundInput:
    """Send ordinary Win32 mouse/keyboard messages to a target child window."""

    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    MK_LBUTTON = 0x0001
    VK_MENU = 0x12
    VK_E = 0x45

    def __init__(self, hwnd: int) -> None:
        if sys.platform != "win32":
            raise RuntimeError("BackgroundInput requires Windows")
        self.hwnd = int(hwnd)
        self.user32 = ctypes.windll.user32
        lresult = ctypes.c_ssize_t
        for name in ("PostMessageW", "SendMessageW"):
            fn = getattr(self.user32, name)
            fn.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            fn.restype = lresult

    @staticmethod
    def _lparam(x: int, y: int) -> int:
        x16 = ctypes.c_short(int(x)).value & 0xFFFF
        y16 = ctypes.c_short(int(y)).value & 0xFFFF
        return x16 | (y16 << 16)

    @staticmethod
    def _key_lparam(*, repeat: int = 1, scan_code: int = 0, extended: bool = False,
                    context: bool = False, previous: bool = False, transition: bool = False) -> int:
        value = int(repeat) & 0xFFFF
        value |= (int(scan_code) & 0xFF) << 16
        if extended:
            value |= 1 << 24
        if context:
            value |= 1 << 29
        if previous:
            value |= 1 << 30
        if transition:
            value |= 1 << 31
        return value

    def mouse_move(self, x: int, y: int) -> None:
        self._post(self.WM_MOUSEMOVE, 0, self._lparam(x, y))

    def click(self, x: int, y: int) -> None:
        lparam = self._lparam(x, y)
        self._post(self.WM_MOUSEMOVE, 0, lparam)
        self._post(self.WM_LBUTTONDOWN, self.MK_LBUTTON, lparam)
        self._post(self.WM_LBUTTONUP, 0, lparam)

    def click_and_verify(self, x: int, y: int, verifier: Callable[[], T | bool | None], *,
                        timeout: float = 3.0, poll_interval: float = 0.10) -> BackgroundClickVerification[T]:
        if timeout < 0:
            raise ValueError("timeout must be >= 0")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")
        started = time.monotonic()
        self.click(x, y)
        while True:
            value = verifier()
            if value is not None and value is not False:
                return BackgroundClickVerification(True, True, time.monotonic() - started, float(timeout), value)
            elapsed = time.monotonic() - started
            if elapsed >= timeout:
                return BackgroundClickVerification(True, False, elapsed, float(timeout), None)
            time.sleep(min(float(poll_interval), max(0.0, timeout - elapsed)))

    def click_sync(self, x: int, y: int) -> None:
        lparam = self._lparam(x, y)
        self._send(self.WM_MOUSEMOVE, 0, lparam)
        self._send(self.WM_LBUTTONDOWN, self.MK_LBUTTON, lparam)
        self._send(self.WM_LBUTTONUP, 0, lparam)

    def key_sync(self, virtual_key: int, *, alt: bool = False, scan_code: int = 0) -> None:
        vk = int(virtual_key)
        if alt:
            self._send(self.WM_SYSKEYDOWN, self.VK_MENU, self._key_lparam(scan_code=0x38))
            self._send(self.WM_SYSKEYDOWN, vk, self._key_lparam(scan_code=scan_code, context=True))
            self._send(self.WM_SYSKEYUP, vk, self._key_lparam(scan_code=scan_code, context=True, previous=True, transition=True))
            self._send(self.WM_SYSKEYUP, self.VK_MENU, self._key_lparam(scan_code=0x38, previous=True, transition=True))
            return
        self._send(self.WM_KEYDOWN, vk, self._key_lparam(scan_code=scan_code))
        self._send(self.WM_KEYUP, vk, self._key_lparam(scan_code=scan_code, previous=True, transition=True))

    def alt_e_sync(self) -> None:
        self.key_sync(self.VK_E, alt=True, scan_code=0x12)

    def _post(self, message: int, wparam: int, lparam: int) -> None:
        if not self.user32.PostMessageW(self.hwnd, message, wparam, lparam):
            raise ctypes.WinError()

    def _send(self, message: int, wparam: int, lparam: int) -> int:
        return int(self.user32.SendMessageW(self.hwnd, message, wparam, lparam))
