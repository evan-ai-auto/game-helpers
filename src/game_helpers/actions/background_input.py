"""Background input adapter for Win32 child windows."""

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
    """Outcome of a background click followed by bounded verification."""

    dispatched: bool
    verified: bool
    elapsed: float
    timeout: float
    value: T | None = None

    @property
    def timed_out(self) -> bool:
        return self.dispatched and not self.verified


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
        lresult = ctypes.c_ssize_t
        for name in ("PostMessageW", "SendMessageW"):
            fn = getattr(self.user32, name)
            fn.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            fn.restype = lresult

    @staticmethod
    def _lparam(x: int, y: int) -> int:
        """Pack signed 16-bit client coordinates into LPARAM."""
        x16 = ctypes.c_short(int(x)).value & 0xFFFF
        y16 = ctypes.c_short(int(y)).value & 0xFFFF
        return x16 | (y16 << 16)

    @staticmethod
    def _key_lparam(*, repeat: int = 1, scan_code: int = 0, extended: bool = False,
                    context: bool = False, previous: bool = False, transition: bool = False) -> int:
        """Build the standard keyboard-message LPARAM bit fields."""
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
        """Post a left click at child-client coordinates."""
        lparam = self._lparam(x, y)
        self._post(self.WM_MOUSEMOVE, 0, lparam)
        self._post(self.WM_LBUTTONDOWN, self.MK_LBUTTON, lparam)
        self._post(self.WM_LBUTTONUP, 0, lparam)

    def click_and_verify(
        self,
        x: int,
        y: int,
        verifier: Callable[[], T | bool | None],
        *,
        timeout: float = 3.0,
        poll_interval: float = 0.10,
    ) -> BackgroundClickVerification[T]:
        """Post a background click and poll a caller-supplied state verifier.

        The click itself is considered dispatched once all three mouse
        messages are queued successfully. Verification is deliberately kept
        outside this adapter: callers decide what observable state proves that
        their action succeeded. This prevents a stale/background capture frame
        from being treated as a failed click.

        The verifier is never allowed to run past ``timeout``. A return value
        of ``True`` (or any non-False/non-None value) is considered success and
        is preserved in ``value``. Exceptions from the verifier propagate so a
        real capture/detector error is not silently converted into a timeout.
        """
        if timeout < 0:
            raise ValueError("timeout must be >= 0")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")

        started = time.monotonic()
        self.click(x, y)
        while True:
            value = verifier()
            if value is not None and value is not False:
                return BackgroundClickVerification(
                    dispatched=True,
                    verified=True,
                    elapsed=time.monotonic() - started,
                    timeout=float(timeout),
                    value=value,
                )
            elapsed = time.monotonic() - started
            if elapsed >= timeout:
                return BackgroundClickVerification(
                    dispatched=True,
                    verified=False,
                    elapsed=elapsed,
                    timeout=float(timeout),
                    value=None,
                )
            time.sleep(min(float(poll_interval), max(0.0, timeout - elapsed)))

    def click_sync(self, x: int, y: int) -> None:
        """Synchronously deliver a left click without activating the window."""
        lparam = self._lparam(x, y)
        self._send(self.WM_MOUSEMOVE, 0, lparam)
        self._send(self.WM_LBUTTONDOWN, self.MK_LBUTTON, lparam)
        self._send(self.WM_LBUTTONUP, 0, lparam)

    def key_sync(self, virtual_key: int, *, alt: bool = False, scan_code: int = 0) -> None:
        """Synchronously deliver one key, optionally with the Alt context."""
        vk = int(virtual_key)
        if alt:
            # Left Alt down: WM_SYSKEYDOWN with scan code 0x38, context=0.
            self._send(self.WM_SYSKEYDOWN, self.VK_MENU, self._key_lparam(scan_code=0x38))
            # A real Alt+key WM_SYSKEYDOWN carries context code bit 29 = 1.
            self._send(self.WM_SYSKEYDOWN, vk, self._key_lparam(scan_code=scan_code, context=True))
            self._send(self.WM_SYSKEYUP, vk, self._key_lparam(scan_code=scan_code, context=True, previous=True, transition=True))
            # Release left Alt. For a focused keyboard path, context is 0 here.
            self._send(self.WM_SYSKEYUP, self.VK_MENU, self._key_lparam(scan_code=0x38, previous=True, transition=True))
            return

        self._send(self.WM_KEYDOWN, vk, self._key_lparam(scan_code=scan_code))
        self._send(self.WM_KEYUP, vk, self._key_lparam(scan_code=scan_code, previous=True, transition=True))

    def alt_e_sync(self) -> None:
        """Synchronously send a correctly shaped Alt+E system-key sequence."""
        self.key_sync(self.VK_E, alt=True, scan_code=0x12)

    def _post(self, message: int, wparam: int, lparam: int) -> None:
        if not self.user32.PostMessageW(self.hwnd, message, wparam, lparam):
            raise ctypes.WinError()

    def _send(self, message: int, wparam: int, lparam: int) -> int:
        return int(self.user32.SendMessageW(self.hwnd, message, wparam, lparam))
