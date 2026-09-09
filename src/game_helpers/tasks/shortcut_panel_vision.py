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


# The arrow is flush with the left edge of the real 800×600 client. The
# previous ROI started at x=8, which clipped the real arrow and could select a
# false-positive match farther to the right. Keep the ROI deliberately local,
# but include x=0 so the actual control can be matched at the client edge.
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
