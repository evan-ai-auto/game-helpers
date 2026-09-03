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

    def pixel(self, width: int, height: int) -> tuple[int, int]:
        return round(self.x * width), round(self.y * height)


@dataclass(frozen=True)
class UiRect:
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
    collapsed_toggle_region: UiRect
    collapsed_toggle_template_path: str = "data/assets/ui/soul_task_panel_collapsed_toggle.json"
    template_path: str = "data/assets/ui/soul_task_claimed_icon.json"
    toggle_match_threshold: float = 0.82
    match_threshold: float = 0.78


DEFAULT_SOUL_TASK_UI = SoulTaskUiProfile(
    # Coordinates are normalized against the parent WGC frame (1036x831 in
    # the user's current environment). The toggle is the small arrow button
    # at roughly (25, 153) in the supplied screenshot.
    task_entry_toggle=UiPoint(25 / 1036, 153 / 831),
    task_panel_icon=UiPoint(0.10, 0.10),
    claimed_icon_region=UiRect(0.0, 0.0, 0.34, 0.42),
    collapsed_toggle_region=UiRect(10 / 1036, 139 / 831, 42 / 1036, 166 / 831),
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


@dataclass(frozen=True)
class SoulTaskPanelObservation:
    collapsed: bool | None
    confidence: float
    match_location: tuple[int, int] | None
    reason: SoulTaskDetectionReason
    evidence: tuple[str, ...] = ()


def _resolve_template_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    cwd_candidate = Path.cwd() / candidate
    if cwd_candidate.is_file():
        return cwd_candidate
    repo_candidate = Path(__file__).resolve().parents[3] / candidate
    if repo_candidate.is_file():
        return repo_candidate
    return cwd_candidate


def _load_template(path: str | Path) -> np.ndarray:
    resolved = _resolve_template_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    raw_json = json.loads(resolved.read_text(encoding="utf-8"))
    payload = raw_json
    if isinstance(payload, dict) and isinstance(payload.get("content"), str):
        try:
            payload = json.loads(payload["content"])
        except json.JSONDecodeError:
            pass
    if not isinstance(payload, dict) or "template_base64" not in payload:
        raise ValueError("template_base64 missing")
    raw = base64.b64decode(payload["template_base64"], validate=True)
    return np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=np.float32)


def _ncc(roi: np.ndarray, template: np.ndarray) -> tuple[float, tuple[int, int] | None]:
    h, w = template.shape[:2]
    rh, rw = roi.shape[:2]
    if rh < h or rw < w:
        return 0.0, None
    t_gray = 0.299 * template[..., 0] + 0.587 * template[..., 1] + 0.114 * template[..., 2]
    t_gray = t_gray - t_gray.mean()
    t_norm = float(np.sqrt((t_gray * t_gray).sum()))
    if t_norm <= 1e-6:
        return 0.0, None
    roi_gray = 0.299 * roi[..., 0] + 0.587 * roi[..., 1] + 0.114 * roi[..., 2]
    best, best_xy = -1.0, None
    for y in range(rh - h + 1):
        for x in range(rw - w + 1):
            patch = roi_gray[y:y + h, x:x + w]
            p = patch - patch.mean()
            denom = float(np.sqrt((p * p).sum()) * t_norm)
            if denom <= 1e-6:
                continue
            score = float((p * t_gray).sum() / denom)
            if score > best:
                best, best_xy = score, (x, y)
    return best, best_xy


def detect_soul_task_panel_collapsed(
    image: Image.Image,
    *,
    profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI,
) -> SoulTaskPanelObservation:
    """Detect the user's marked collapsed-state toggle."""
    left, top, right, bottom = profile.collapsed_toggle_region.pixel(image.width, image.height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    if right <= left or bottom <= top:
        return SoulTaskPanelObservation(None, 0.0, None, SoulTaskDetectionReason.ROI_INVALID)
    try:
        template = _load_template(profile.collapsed_toggle_template_path)
    except FileNotFoundError:
        return SoulTaskPanelObservation(None, 0.0, None, SoulTaskDetectionReason.TOGGLE_TEMPLATE_MISSING)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, binascii.Error):
        return SoulTaskPanelObservation(None, 0.0, None, SoulTaskDetectionReason.TOGGLE_TEMPLATE_INVALID)
    roi = np.asarray(image.convert("RGB"), dtype=np.float32)[top:bottom, left:right]
    score, location = _ncc(roi, template)
    collapsed = score >= profile.toggle_match_threshold
    return SoulTaskPanelObservation(
        collapsed=collapsed,
        confidence=max(0.0, score),
        match_location=(left + location[0], top + location[1]) if location else None,
        reason=SoulTaskDetectionReason.PANEL_EXPANDED if not collapsed else SoulTaskDetectionReason.PANEL_ALREADY_OPEN,
        evidence=(f"collapsed toggle best score={score:.3f}", f"template={_resolve_template_path(profile.collapsed_toggle_template_path)}"),
    )


def detect_soul_task_claimed_icon(
    image: Image.Image,
    *,
    profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI,
    template_path: str | Path | None = None,
) -> SoulTaskObservation:
    if image.width <= 0 or image.height <= 0:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.IMAGE_INVALID, 0.0, False)
    left, top, right, bottom = profile.claimed_icon_region.pixel(image.width, image.height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    if right <= left or bottom <= top:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.ROI_INVALID, 0.0, False)
    resolved_template = _resolve_template_path(template_path or profile.template_path)
    try:
        template = _load_template(resolved_template)
    except FileNotFoundError:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.TEMPLATE_MISSING, 0.0, False,
                                    evidence=(f"claimed icon template not found: {resolved_template}",))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, binascii.Error):
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.TEMPLATE_INVALID, 0.0, False,
                                    evidence=(f"claimed icon template could not be decoded: {resolved_template}",))
    roi = np.asarray(image.convert("RGB"), dtype=np.float32)[top:bottom, left:right]
    score, location = _ncc(roi, template)
    if score >= profile.match_threshold:
        absolute = (left + location[0], top + location[1]) if location else None
        return SoulTaskObservation(SoulTaskStatus.CLAIMED, SoulTaskDetectionReason.ICON_FOUND, score, True, absolute,
                                    (f"claimed icon match score={score:.3f}", f"template={resolved_template}"))
    return SoulTaskObservation(SoulTaskStatus.NOT_CLAIMED, SoulTaskDetectionReason.ICON_NOT_FOUND, max(0.0, score), True,
                                None, (f"claimed icon not found; best score={score:.3f}", f"template={resolved_template}"))


def inspect_task_panel_image(path: str | Path, *, profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI) -> SoulTaskObservation:
    try:
        image = Image.open(path)
    except (OSError, ValueError):
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.IMAGE_INVALID, 0.0, False,
                                    evidence=("unable to load screenshot",), screenshot_path=str(path))
    result = detect_soul_task_claimed_icon(image, profile=profile)
    return SoulTaskObservation(result.status, result.reason, result.confidence, result.panel_detected,
                               result.match_location, result.evidence, str(path))


def claim_verification_result(after: SoulTaskObservation) -> SoulTaskObservation:
    if after.status == SoulTaskStatus.CLAIMED:
        return after
    return SoulTaskObservation(SoulTaskStatus.CLAIM_FAILED, SoulTaskDetectionReason.CLAIM_VERIFICATION_FAILED,
                                after.confidence, after.panel_detected, after.match_location,
                                ("命魂任务领取流程已执行，但复检仍未发现已领取图标", *after.evidence), after.screenshot_path)
