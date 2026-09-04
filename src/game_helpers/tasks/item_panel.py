"""Visual result detection for the in-game item panel.

This module deliberately detects a *state change* against a caller-supplied
baseline instead of pretending that one hard-coded screenshot is universally
valid. It is suitable for bounded post-click verification: if WGC exposes the
updated background frame, a sufficiently large change in the configurable
panel ROI is evidence that the click changed the UI. If WGC keeps returning a
stale background frame, callers receive ``NOT_DETECTED`` and can report a
verification timeout rather than falsely declaring the click failed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..capture.models import Frame


class ItemPanelStatus(str):
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    INVALID = "invalid"


@dataclass(frozen=True)
class ItemPanelUiProfile:
    """Normalized ROI and thresholds for item-panel change detection."""

    left: float = 0.12
    top: float = 0.16
    right: float = 0.94
    bottom: float = 0.92
    pixel_delta: float = 18.0
    changed_ratio: float = 0.045
    mean_delta: float = 4.0


DEFAULT_ITEM_PANEL_UI = ItemPanelUiProfile()


@dataclass(frozen=True)
class ItemPanelObservation:
    status: str
    confidence: float
    changed_ratio: float
    mean_delta: float
    evidence: tuple[str, ...] = ()

    @property
    def detected(self) -> bool:
        return self.status == ItemPanelStatus.DETECTED


def _frame_array(frame: Frame) -> np.ndarray:
    expected = frame.width * frame.height * 4
    if frame.width <= 0 or frame.height <= 0 or len(frame.data) != expected:
        raise ValueError("invalid Frame")
    return np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 4)[..., :3]


def _roi(frame: Frame, profile: ItemPanelUiProfile) -> np.ndarray:
    image = _frame_array(frame)
    h, w = image.shape[:2]
    left = max(0, min(w, round(profile.left * w)))
    top = max(0, min(h, round(profile.top * h)))
    right = max(0, min(w, round(profile.right * w)))
    bottom = max(0, min(h, round(profile.bottom * h)))
    if right <= left or bottom <= top:
        raise ValueError("invalid item panel ROI")
    return image[top:bottom, left:right]


def compare_item_panel_state(
    baseline: Frame,
    current: Frame,
    *,
    profile: ItemPanelUiProfile = DEFAULT_ITEM_PANEL_UI,
) -> ItemPanelObservation:
    """Compare the panel ROI between two WGC frames.

    A change is accepted only when both the fraction of significantly changed
    pixels and the mean RGB delta cross their thresholds. This reduces false
    positives from ordinary character animation while remaining sensitive to a
    large inventory-panel transition.
    """
    if (baseline.width, baseline.height) != (current.width, current.height):
        return ItemPanelObservation(ItemPanelStatus.INVALID, 0.0, 0.0, 0.0, ("frame dimensions differ",))
    try:
        before = _roi(baseline, profile).astype(np.int16)
        after = _roi(current, profile).astype(np.int16)
    except ValueError as exc:
        return ItemPanelObservation(ItemPanelStatus.INVALID, 0.0, 0.0, 0.0, (str(exc),))

    delta = np.abs(after - before)
    pixel_delta = delta.mean(axis=2)
    changed_ratio = float((pixel_delta >= profile.pixel_delta).mean())
    mean_delta = float(pixel_delta.mean())
    ratio_score = min(1.0, changed_ratio / max(profile.changed_ratio, 1e-6))
    mean_score = min(1.0, mean_delta / max(profile.mean_delta, 1e-6))
    confidence = min(ratio_score, mean_score)
    detected = changed_ratio >= profile.changed_ratio and mean_delta >= profile.mean_delta
    status = ItemPanelStatus.DETECTED if detected else ItemPanelStatus.NOT_DETECTED
    evidence = (
        f"panel changed_ratio={changed_ratio:.4f}",
        f"panel mean_rgb_delta={mean_delta:.2f}",
        f"threshold changed_ratio>={profile.changed_ratio:.4f}",
        f"threshold mean_rgb_delta>={profile.mean_delta:.2f}",
    )
    return ItemPanelObservation(status, confidence, changed_ratio, mean_delta, evidence)
