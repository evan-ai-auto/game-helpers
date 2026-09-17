"""Shortcut-panel arrow vision for the 梦幻西游 800×600 client baseline."""
from __future__ import annotations

from dataclasses import replace

from PIL import Image

from ..capture.models import Frame
from .soul_task import (
    DEFAULT_SOUL_TASK_UI,
    SoulTaskPanelObservation,
    SoulTaskUiProfile,
    UiRect,
    detect_soul_task_panel_collapsed,
)


# The arrow is flush with the left edge of the real 800×600 client. Keep this
# ROI as a small tolerance band around the production click candidate (14, 122).
# Visual match centers found here are diagnostic only; the main flow clicks the
# calibrated/default fixed client point, not the match center.
SHORTCUT_PANEL_TOGGLE_REGION = UiRect(
    0 / 800,
    80 / 600,
    40 / 800,
    128 / 600,
)


def detect_shortcut_panel_state(
    image: Image.Image | Frame,
    *,
    profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI,
) -> SoulTaskPanelObservation:
    """Detect shortcut-panel state using the edge-inclusive real-game ROI."""
    adjusted = replace(
        profile,
        collapsed_toggle_region=SHORTCUT_PANEL_TOGGLE_REGION,
    )
    return detect_soul_task_panel_collapsed(image, profile=adjusted)


__all__ = [
    "SHORTCUT_PANEL_TOGGLE_REGION",
    "detect_shortcut_panel_state",
]
