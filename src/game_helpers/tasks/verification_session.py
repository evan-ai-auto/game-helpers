"""Shared verification-session context and composable workflow nodes."""
from __future__ import annotations

import numpy as np

from dataclasses import dataclass

from ..capture import WindowsGraphicsCapture
from ..capture.models import Frame
from ..core.surface import SurfaceGeometry, SurfaceHealth, inspect_surface, query_surface_geometry
from ..core.view_manager import GameViewManager
from ..core.window import get_window_info
from .character_selection import CharacterSelectionResult


@dataclass
class VerificationSession:
    """One selected-character verification context shared by every flow node."""

    parent_hwnd: int
    selected: CharacterSelectionResult
    manager: GameViewManager
    capture: WindowsGraphicsCapture

    def sync_character(self) -> None:
        from .character_selection import sync_selected_character
        sync_selected_character(self.parent_hwnd, self.selected)

    def geometry(self) -> SurfaceGeometry:
        return query_surface_geometry(self.selected.hwnd)

    def capture_frame(self) -> Frame:
        """Capture the host and crop the selected child WSGAME surface.

        Windows Graphics Capture's ``window_hwnd`` path is designed around
        capturable application windows; a hosted child WSGAME HWND may fail
        when converted to ``GraphicsCaptureItem``. The host is the stable
        capturable window, so capture it and derive the selected child's
        visible client rectangle from screen coordinates. The returned Frame
        still identifies the selected WSGAME as its logical source.
        """
        parent = get_window_info(self.parent_hwnd)
        selected_geometry = self.geometry()
        parent_geometry = query_surface_geometry(self.parent_hwnd)
        host_frame = self.capture.capture(self.parent_hwnd)

        left = selected_geometry.screen_left - parent_geometry.screen_left
        top = selected_geometry.screen_top - parent_geometry.screen_top
        right = left + selected_geometry.client_width
        bottom = top + selected_geometry.client_height

        x0 = max(0, left)
        y0 = max(0, top)
        x1 = min(host_frame.width, right)
        y1 = min(host_frame.height, bottom)
        if x1 <= x0 or y1 <= y0:
            raise RuntimeError(
                "selected WSGAME client rectangle is outside the captured host frame: "
                f"selected=({left},{top},{right},{bottom}) "
                f"host={host_frame.width}x{host_frame.height}"
            )

        source = np.frombuffer(host_frame.data, dtype=np.uint8).reshape(
            host_frame.height, host_frame.width, 4
        )
        cropped = np.ascontiguousarray(source[y0:y1, x0:x1, :])
        return Frame(
            window=get_window_info(self.selected.hwnd),
            width=int(cropped.shape[1]),
            height=int(cropped.shape[0]),
            data=cropped.tobytes(),
            captured_at=host_frame.captured_at,
            backend=host_frame.backend,
        )

    def health(self, frame: Frame | None = None) -> SurfaceHealth:
        frame = frame or self.capture_frame()
        return inspect_surface(frame, self.geometry())

    def require_healthy_surface(self, frame: Frame | None = None) -> SurfaceHealth:
        health = self.health(frame)
        if not health.ready:
            details = "; ".join(health.evidence)
            raise RuntimeError(f"selected WSGAME surface is not capture-ready: {details}")
        return health
