"""命魂任务领取状态检测。

已领取的唯一正向证据：用户标记的“命魂任务已领取”图标。
找不到该图标 => NOT_CLAIMED；截图/区域无法可靠检测 => UNKNOWN。
领取流程后的复检仍无图标 => CLAIM_FAILED。
本模块当前不自动执行领取动作。
"""
from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
from PIL import Image


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
    CLAIM_VERIFICATION_FAILED = "claim_verification_failed"


@dataclass(frozen=True)
class UiPoint:
    x: float
    y: float

    def pixel(self, width: int, height: int) -> tuple[int, int]:
        return round(self.x * width), round(self.y * height)


@dataclass(frozen=True)
class UiRect:
    """Normalized rectangle in the captured game surface."""
    left: float
    top: float
    right: float
    bottom: float

    def pixel(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (round(self.left * width), round(self.top * height),
                round(self.right * width), round(self.bottom * height))


@dataclass(frozen=True)
class SoulTaskUiProfile:
    task_entry_toggle: UiPoint
    task_panel_icon: UiPoint
    claimed_icon_region: UiRect
    template_path: str = "data/assets/ui/soul_task_claimed_icon.json"
    match_threshold: float = 0.78


# The user's red-box detection area is intentionally a configuration value.
# It can be recalibrated without changing detection code when the client layout changes.
DEFAULT_SOUL_TASK_UI = SoulTaskUiProfile(
    task_entry_toggle=UiPoint(0.047, 0.33),
    task_panel_icon=UiPoint(0.10, 0.10),
    claimed_icon_region=UiRect(0.0, 0.0, 0.23, 0.42),
)


@dataclass(frozen=True)
class SoulTaskObservation:
    status: SoulTaskStatus
    reason: SoulTaskDetectionReason
    confidence: float
    panel_detected: bool
    match_location: tuple[int, int] | None = None
    evidence: tuple[str, ...] = ()
    screenshot_path: str | None = None


def _load_template(path: str | Path) -> np.ndarray:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = base64.b64decode(payload["template_base64"])
    return np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=np.float32)


def _ncc(roi: np.ndarray, template: np.ndarray) -> tuple[float, tuple[int, int] | None]:
    """Return the best normalized cross-correlation score and local position."""
    h, w = template.shape[:2]
    rh, rw = roi.shape[:2]
    if rh < h or rw < w:
        return 0.0, None
    t = template - template.mean(axis=(0, 1), keepdims=True)
    t_norm = float(np.sqrt((t * t).sum()))
    if t_norm <= 1e-6:
        return 0.0, None
    best, best_xy = -1.0, None
    for y in range(rh - h + 1):
        for x in range(rw - w + 1):
            patch = roi[y:y + h, x:x + w]
            p = patch - patch.mean(axis=(0, 1), keepdims=True)
            denom = float(np.sqrt((p * p).sum()) * t_norm)
            if denom <= 1e-6:
                continue
            score = float((p * t).sum() / denom)
            if score > best:
                best, best_xy = score, (x, y)
    return best, best_xy


def detect_soul_task_claimed_icon(
    image: Image.Image,
    *,
    profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI,
    template_path: str | Path | None = None,
) -> SoulTaskObservation:
    """Detect the claimed icon inside the user-defined detection region."""
    if image.width <= 0 or image.height <= 0:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.IMAGE_INVALID, 0.0, False)
    left, top, right, bottom = profile.claimed_icon_region.pixel(image.width, image.height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    if right <= left or bottom <= top:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.ROI_INVALID, 0.0, False)
    try:
        template = _load_template(template_path or profile.template_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, base64.binascii.Error):
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.IMAGE_INVALID, 0.0, False,
                                   evidence=("claimed icon template could not be loaded",))
    roi = np.asarray(image.convert("RGB"), dtype=np.float32)[top:bottom, left:right]
    score, location = _ncc(roi, template)
    if score >= profile.match_threshold:
        absolute = (left + location[0], top + location[1]) if location else None
        return SoulTaskObservation(SoulTaskStatus.CLAIMED, SoulTaskDetectionReason.ICON_FOUND, score, True,
                                   absolute, (f"claimed icon match score={score:.3f}",))
    return SoulTaskObservation(SoulTaskStatus.NOT_CLAIMED, SoulTaskDetectionReason.ICON_NOT_FOUND,
                               max(0.0, score), True, None,
                               (f"claimed icon not found; best score={score:.3f}",))


def inspect_task_panel_image(path: str | Path, *, profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI) -> SoulTaskObservation:
    """Inspect a saved game screenshot."""
    try:
        image = Image.open(path)
    except (OSError, ValueError):
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.IMAGE_INVALID, 0.0, False,
                                   evidence=("unable to load screenshot",), screenshot_path=str(path))
    result = detect_soul_task_claimed_icon(image, profile=profile)
    return SoulTaskObservation(result.status, result.reason, result.confidence, result.panel_detected,
                               result.match_location, result.evidence, str(path))


def claim_verification_result(after: SoulTaskObservation) -> SoulTaskObservation:
    """Convert a failed post-claim verification into an explicit failure state."""
    if after.status == SoulTaskStatus.CLAIMED:
        return after
    return SoulTaskObservation(
        SoulTaskStatus.CLAIM_FAILED,
        SoulTaskDetectionReason.CLAIM_VERIFICATION_FAILED,
        after.confidence,
        after.panel_detected,
        after.match_location,
        ("命魂任务领取流程已执行，但复检仍未发现已领取图标", *after.evidence),
        after.screenshot_path,
    )
