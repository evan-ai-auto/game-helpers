"""Geometry and health checks for hosted WSGAME surfaces."""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from ctypes import wintypes

from ..capture.models import Frame
from .models import Point


@dataclass(frozen=True)
class SurfaceGeometry:
    hwnd: int
    client_width: int
    client_height: int
    screen_left: int
    screen_top: int
    dpi: int

    @property
    def aspect_ratio(self) -> float:
        return self.client_width / self.client_height if self.client_height else 0.0

    def screen_to_client(self, x: int, y: int) -> Point:
        return Point(x - self.screen_left, y - self.screen_top)

    def client_to_screen(self, x: int, y: int) -> Point:
        return Point(self.screen_left + x, self.screen_top + y)


@dataclass(frozen=True)
class SurfaceHealth:
    status: str
    expected_size: tuple[int, int]
    frame_size: tuple[int, int]
    scale_x: float
    scale_y: float
    aspect_delta: float
    evidence: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status in {"ready", "scaled"}

    @property
    def geometry_mismatch(self) -> bool:
        return self.status == "mismatch"


def query_surface_geometry(hwnd: int) -> SurfaceGeometry:
    if sys.platform != "win32":
        raise RuntimeError("surface geometry requires Windows")
    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        raise ctypes.WinError()
    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(origin)):
        raise ctypes.WinError()
    get_dpi = getattr(user32, "GetDpiForWindow", None)
    dpi = int(get_dpi(wintypes.HWND(hwnd))) if get_dpi else 96
    return SurfaceGeometry(
        hwnd=int(hwnd),
        client_width=int(rect.right - rect.left),
        client_height=int(rect.bottom - rect.top),
        screen_left=int(origin.x),
        screen_top=int(origin.y),
        dpi=dpi or 96,
    )


def inspect_surface(frame: Frame, geometry: SurfaceGeometry | None = None) -> SurfaceHealth:
    geometry = geometry or query_surface_geometry(frame.window.hwnd)
    ew, eh = geometry.client_width, geometry.client_height
    fw, fh = int(frame.width), int(frame.height)
    if ew <= 0 or eh <= 0 or fw <= 0 or fh <= 0:
        return SurfaceHealth("mismatch", (ew, eh), (fw, fh), 0.0, 0.0, 1.0, ("non_positive_geometry",))

    sx, sy = fw / ew, fh / eh
    expected_aspect = ew / eh
    frame_aspect = fw / fh
    aspect_delta = abs(frame_aspect - expected_aspect) / expected_aspect
    evidence = [f"client_size={ew}x{eh}", f"frame_size={fw}x{fh}", f"scale=({sx:.4f},{sy:.4f})", f"aspect_delta={aspect_delta:.4f}"]

    if fw == ew and fh == eh:
        evidence.append("frame_matches_client_exactly")
        return SurfaceHealth("ready", (ew, eh), (fw, fh), sx, sy, aspect_delta, tuple(evidence))

    uniform_scale = abs(sx - sy) <= 0.02 * max(sx, sy)
    if aspect_delta <= 0.02 and uniform_scale:
        evidence.append("frame_is_uniformly_scaled_relative_to_client")
        return SurfaceHealth("scaled", (ew, eh), (fw, fh), sx, sy, aspect_delta, tuple(evidence))

    evidence.append("frame_and_client_geometry_are_not_compatible")
    return SurfaceHealth("mismatch", (ew, eh), (fw, fh), sx, sy, aspect_delta, tuple(evidence))
