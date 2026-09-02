"""Visible-screen capture backend for Windows."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from game_helpers.core.models import WindowInfo

from .models import Frame


class _BITMAPINFOHEADER(ctypes.Structure):
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


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 1)]


class ScreenCapture:
    """Capture the pixels currently visible on the desktop for a window rectangle.

    Unlike PrintWindow, this reads the compositor's visible pixels. Therefore
    it is useful for validating tabbed/custom-rendered games, but it is not a
    background-safe backend: another window covering the target will be
    captured instead.
    """

    def capture(self, window: WindowInfo) -> Frame:
        if sys.platform != "win32":
            raise RuntimeError("screen capture is only available on Windows")

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        width = window.bounds.width
        height = window.bounds.height
        if width <= 0 or height <= 0:
            raise ValueError("window bounds must be non-empty")

        screen_dc = user32.GetDC(0)
        if not screen_dc:
            raise RuntimeError("GetDC failed")
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        if not mem_dc or not bitmap:
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(0, screen_dc)
            raise RuntimeError("could not create compatible screen bitmap")

        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        try:
            SRCCOPY = 0x00CC0020
            if not gdi32.BitBlt(
                mem_dc,
                0,
                0,
                width,
                height,
                screen_dc,
                window.bounds.left,
                window.bounds.top,
                SRCCOPY,
            ):
                raise RuntimeError("BitBlt failed")

            info = _BITMAPINFO()
            info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            info.bmiHeader.biWidth = width
            info.bmiHeader.biHeight = -height
            info.bmiHeader.biPlanes = 1
            info.bmiHeader.biBitCount = 32
            info.bmiHeader.biCompression = 0  # BI_RGB

            buffer = (ctypes.c_ubyte * (width * height * 4))()
            lines = gdi32.GetDIBits(
                mem_dc,
                bitmap,
                0,
                height,
                ctypes.byref(buffer),
                ctypes.byref(info),
                0,
            )
            if lines != height:
                raise RuntimeError(f"GetDIBits returned {lines} lines, expected {height}")
            return Frame.from_bgra(
                window,
                width,
                height,
                bytes(buffer),
                backend="screen-bitblt",
            )
        finally:
            gdi32.SelectObject(mem_dc, old_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(0, screen_dc)
