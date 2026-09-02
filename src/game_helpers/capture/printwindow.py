"""Win32 ``PrintWindow`` capture backend."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from game_helpers.core.models import WindowInfo

from .models import Frame


class PrintWindowCapture:
    """Capture a top-level window through the Win32 PrintWindow API.

    This targets the window handle instead of taking a screen crop, so the
    source window does not need to be the foreground window. Some GPU-backed
    applications may return an empty or incomplete frame; those cases will be
    handled by later capture backends.
    """

    name = "printwindow"
    PW_RENDERFULLCONTENT = 0x00000002

    def capture(self, window: WindowInfo) -> Frame:
        """Capture ``window`` and return its pixels as tightly packed BGRA."""
        if sys.platform != "win32":
            raise RuntimeError("PrintWindowCapture is only available on Windows")
        if window.bounds.width <= 0 or window.bounds.height <= 0:
            raise ValueError("cannot capture a window with empty bounds")

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hwnd = wintypes.HWND(window.hwnd)
        width = window.bounds.width
        height = window.bounds.height

        hdc_window = user32.GetWindowDC(hwnd)
        if not hdc_window:
            raise OSError("GetWindowDC failed")

        hdc_mem = None
        hbitmap = None
        old_bitmap = None
        try:
            hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
            if not hdc_mem:
                raise OSError("CreateCompatibleDC failed")

            hbitmap = gdi32.CreateCompatibleBitmap(hdc_window, width, height)
            if not hbitmap:
                raise OSError("CreateCompatibleBitmap failed")

            old_bitmap = gdi32.SelectObject(hdc_mem, hbitmap)
            if not old_bitmap:
                raise OSError("SelectObject failed")

            ok = user32.PrintWindow(hwnd, hdc_mem, self.PW_RENDERFULLCONTENT)
            if not ok:
                raise OSError("PrintWindow failed")

            class BitmapInfoHeader(ctypes.Structure):
                _fields_ = [
                    ("biSize", wintypes.DWORD),
                    ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD),
                ]

            class BitmapInfo(ctypes.Structure):
                _fields_ = [
                    ("bmiHeader", BitmapInfoHeader),
                    ("bmiColors", wintypes.DWORD * 3),
                ]

            info = BitmapInfo()
            info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader)
            info.bmiHeader.biWidth = width
            info.bmiHeader.biHeight = -height  # top-down bitmap
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = 0  # BI_RGB

            size = width * height * 4
            buffer = (ctypes.c_ubyte * size)()
            copied = gdi32.GetDIBits(
                hdc_mem,
                hbitmap,
                0,
                height,
                ctypes.byref(buffer),
                ctypes.byref(info),
                0,
            )
            if copied != height:
                raise OSError(f"GetDIBits failed: copied {copied} of {height} rows")

            return Frame.from_bgra(
                window,
                width,
                height,
                bytes(buffer),
                backend=self.name,
            )
        finally:
            if old_bitmap and hdc_mem:
                gdi32.SelectObject(hdc_mem, old_bitmap)
            if hbitmap:
                gdi32.DeleteObject(hbitmap)
            if hdc_mem:
                gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(hwnd, hdc_window)
