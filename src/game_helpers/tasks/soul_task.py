"""命魂任务领取状态检测。"""
from __future__ import annotations

import base64
import binascii
import io
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
from PIL import Image

from ..capture.models import Frame


class SoulTaskStatus(str, Enum):
    CLAIMED = "claimed"
    NOT_CLAIMED = "not_claimed"
    UNKNOWN = "unknown"
    CLAIM_FAILED = "claim_failed"


class SoulTaskDetectionReason(str, Enum):
    ICON_FOUND = "claimed_icon_found"
    ICON_NOT_FOUND = "claimed_icon_not_found"
    IMAGE_INVALID = "invalid_image"
    ROI_INVALID = "invalid_detection_region"
    TEMPLATE_MISSING = "claimed_icon_template_missing"
    TEMPLATE_INVALID = "claimed_icon_template_invalid"
    TOGGLE_TEMPLATE_MISSING = "collapsed_toggle_template_missing"
    TOGGLE_TEMPLATE_INVALID = "collapsed_toggle_template_invalid"
    PANEL_ALREADY_OPEN = "panel_already_open"
    PANEL_EXPANDED = "panel_expanded"
    CLAIM_VERIFICATION_FAILED = "claim_verification_failed"


@dataclass(frozen=True)
class UiPoint:
    x: float
    y: float


@dataclass(frozen=True)
class UiRegion:
    left: float
    top: float
    right: float
    bottom: float

    def pixel(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            int(self.left * width),
            int(self.top * height),
            int(self.right * width),
            int(self.bottom * height),
        )


@dataclass(frozen=True)
class SoulTaskUiProfile:
    collapsed_toggle_region: UiRegion
    task_entry_toggle: UiPoint
    claimed_icon_region: UiRegion


@dataclass(frozen=True)
class SoulTaskPanelObservation:
    collapsed: bool | None
    confidence: float
    match_location: tuple[int, int] | None
    reason: SoulTaskDetectionReason
    evidence: tuple[str, ...] = ()


# The normalized coordinates are based on the supplied 1036x831 game capture.
DEFAULT_SOUL_TASK_UI = SoulTaskUiProfile(
    collapsed_toggle_region=UiRegion(0.0, 0.11, 0.032, 0.19),
    task_entry_toggle=UiPoint(0.024, 0.184),
    claimed_icon_region=UiRegion(0.0, 0.19, 0.11, 0.40),
)


def _as_pil_image(image: Image.Image | Frame) -> Image.Image:
    """Convert a PIL image or capture-layer Frame into a PIL RGB image."""
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, Frame):
        expected = image.width * image.height * 4
        if len(image.data) != expected:
            raise ValueError("invalid Frame BGRA payload")
        return Image.frombytes("RGBA", (image.width, image.height), image.data, "raw", "BGRA").convert("RGB")
    raise TypeError(f"unsupported image type: {type(image).__name__}")


def detect_soul_task_panel_collapsed(
    image: Image.Image | Frame,
    *,
    profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI,
) -> SoulTaskPanelObservation:
    """Detect panel state from the dedicated toggle region."""
    try:
        image = _as_pil_image(image)
    except (TypeError, ValueError):
        return SoulTaskPanelObservation(None, 0.0, None, SoulTaskDetectionReason.IMAGE_INVALID)
    if image.width <= 0 or image.height <= 0:
        return SoulTaskPanelObservation(None, 0.0, None, SoulTaskDetectionReason.IMAGE_INVALID)
    left, top, right, bottom = profile.collapsed_toggle_region.pixel(image.width, image.height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    if right <= left or bottom <= top:
        return SoulTaskPanelObservation(None, 0.0, None, SoulTaskDetectionReason.ROI_INVALID)
    roi = np.asarray(image, dtype=np.uint8)[top:bottom, left:right]
    if roi.size == 0:
        return SoulTaskPanelObservation(None, 0.0, None, SoulTaskDetectionReason.ROI_INVALID)

    r = roi[..., 0].astype(np.int16)
    g = roi[..., 1].astype(np.int16)
    b = roi[..., 2].astype(np.int16)
    red_mask = (r >= 120) & ((r - g) >= 45) & ((r - b) >= 25)
    red_ratio = float(red_mask.mean())
    red_pixels = int(red_mask.sum())
    expanded = red_pixels >= 25 and red_ratio >= 0.025
    confidence = min(1.0, abs(red_ratio - 0.025) / 0.12 + 0.55) if expanded else min(1.0, 0.55 + (0.025 - red_ratio) / 0.05)
    reason = SoulTaskDetectionReason.PANEL_EXPANDED if expanded else SoulTaskDetectionReason.PANEL_ALREADY_OPEN
    evidence = (
        f"toggle red_pixels={red_pixels}",
        f"toggle red_ratio={red_ratio:.4f}",
        "expanded toggle is identified by the red control; collapsed state by its absence",
    )
    return SoulTaskPanelObservation(not expanded, confidence, None, reason, evidence)
