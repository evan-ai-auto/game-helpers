"""Shared verification-session context and composable workflow nodes."""
from __future__ import annotations

from dataclasses import dataclass

from ..capture import WindowsGraphicsCapture
from ..capture.models import Frame
from ..core.surface import SurfaceGeometry, SurfaceHealth, inspect_surface, query_surface_geometry
from ..core.view_manager import GameViewManager
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
        # Capture the selected WSGAME itself, not the parent host. This avoids
        # treating unused host area as part of the game's visual canvas.
        return self.capture.capture(self.selected.hwnd)

    def health(self, frame: Frame | None = None) -> SurfaceHealth:
        frame = frame or self.capture_frame()
        return inspect_surface(frame, self.geometry())

    def require_healthy_surface(self, frame: Frame | None = None) -> SurfaceHealth:
        health = self.health(frame)
        if not health.ready:
            details = "; ".join(health.evidence)
            raise RuntimeError(f"selected WSGAME surface is not capture-ready: {details}")
        return health
