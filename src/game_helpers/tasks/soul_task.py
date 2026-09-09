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
    TOGGLE_TEMPLATE_MISSING = "shortcut_toggle_template_missing"
    TOGGLE_TEMPLATE_INVALID = "shortcut_toggle_template_invalid"
    PANEL_ALREADY_OPEN = "panel_already_open"
    PANEL_COLLAPSED = "panel_collapsed"
    PANEL_EXPANDED = "panel_expanded"
    PANEL_STATE_UNKNOWN = "panel_state_unknown"
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
        return (
            round(self.left * width),
            round(self.top * height),
            round(self.right * width),
            round(self.bottom * height),
        )


@dataclass(frozen=True)
class SoulTaskUiProfile:
    task_entry_toggle: UiPoint
    task_panel_icon: UiPoint
    claimed_icon_region: UiRect
    collapsed_toggle_region: UiRect
    toggle_right_light_template_path: str = "data/assets/ui/shortcut_toggle_right_light.png"
    toggle_right_gray_template_path: str = "data/assets/ui/shortcut_toggle_right_gray.png"
    toggle_left_light_template_path: str = "data/assets/ui/shortcut_toggle_left_light.png"
    template_path: str = "data/assets/ui/soul_task_claimed_icon.json"
    toggle_match_threshold: float = 0.82
    toggle_margin: float = 0.01
    match_threshold: float = 0.78


SOUL_TASK_BASELINE_SIZE = (800, 600)

DEFAULT_SOUL_TASK_UI = SoulTaskUiProfile(
    # Compatibility fallback only; normal operation locates the real arrow.
    task_entry_toggle=UiPoint(25 / 800, 100 / 600),
    task_panel_icon=UiPoint(0.10, 0.10),
    claimed_icon_region=UiRect(0.0, 0.0, 0.34, 0.42),
    collapsed_toggle_region=UiRect(8 / 800, 82 / 600, 52 / 800, 128 / 600),
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
    click_location: tuple[int, int] | None = None
    matched_template: str | None = None


def _as_pil_image(image: Image.Image | Frame) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, Frame):
        expected = image.width * image.height * 4
        if len(image.data) != expected:
            raise ValueError("invalid Frame BGRA payload")
        return Image.frombytes(
            "RGBA", (image.width, image.height), image.data, "raw", "BGRA"
        ).convert("RGB")
    raise TypeError(f"unsupported image type: {type(image).__name__}")


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


def _load_template(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load a PNG template as RGB + normalized alpha mask."""
    resolved = _resolve_template_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    with Image.open(resolved) as image:
        rgba = image.convert("RGBA")
    return (
        np.asarray(rgba, dtype=np.float32)[..., :3],
        np.asarray(rgba, dtype=np.float32)[..., 3] / 255.0,
    )


def _load_claimed_icon_template(path: str | Path) -> np.ndarray:
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


def _masked_match(
    roi: np.ndarray,
    template_rgb: np.ndarray,
    alpha: np.ndarray,
) -> tuple[float, tuple[int, int] | None]:
    """Color similarity that ignores transparent template pixels."""
    h, w = template_rgb.shape[:2]
    rh, rw = roi.shape[:2]
    if rh < h or rw < w:
        return 0.0, None
    weights = np.asarray(alpha, dtype=np.float32)
    if weights.shape != (h, w) or float(weights.sum()) <= 1e-6:
        return 0.0, None
    weight_sum = float(weights.sum())
    best_score, best_xy = 0.0, None
    for y in range(rh - h + 1):
        for x in range(rw - w + 1):
            patch = roi[y:y + h, x:x + w]
            error = float(
                (np.abs(patch - template_rgb).mean(axis=2) * weights).sum()
                / weight_sum
            )
            score = max(0.0, 1.0 - error / 255.0)
            if score > best_score:
                best_score, best_xy = score, (x, y)
    return best_score, best_xy


def _toggle_templates(profile: SoulTaskUiProfile) -> tuple[tuple[str, str, bool], ...]:
    return (
        ("right_light", profile.toggle_right_light_template_path, True),
        ("right_gray", profile.toggle_right_gray_template_path, True),
        ("left_light", profile.toggle_left_light_template_path, False),
    )


def detect_soul_task_panel_collapsed(
    image: Image.Image | Frame,
    *,
    profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI,
) -> SoulTaskPanelObservation:
    """Detect collapsed/expanded state from the real arrow assets.

    User-provided evidence defines the semantics:
      * right-pointing arrow (light or grey) = collapsed
      * left-pointing arrow (light) = expanded

    The returned click location is the matched arrow center, so execution does
    not depend on the old fixed coordinate.
    """
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
    roi = np.asarray(image, dtype=np.float32)[top:bottom, left:right]
    if roi.size == 0:
        return SoulTaskPanelObservation(None, 0.0, None, SoulTaskDetectionReason.ROI_INVALID)

    matches: list[tuple[float, str, bool, tuple[int, int] | None, tuple[int, int]]] = []
    for name, path, is_collapsed in _toggle_templates(profile):
        try:
            template_rgb, alpha = _load_template(path)
        except FileNotFoundError:
            return SoulTaskPanelObservation(
                None, 0.0, None, SoulTaskDetectionReason.TOGGLE_TEMPLATE_MISSING,
                evidence=(f"toggle template not found: {_resolve_template_path(path)}",)
            )
        except (OSError, ValueError):
            return SoulTaskPanelObservation(
                None, 0.0, None, SoulTaskDetectionReason.TOGGLE_TEMPLATE_INVALID,
                evidence=(f"toggle template invalid: {_resolve_template_path(path)}",)
            )
        score, location = _masked_match(roi, template_rgb, alpha)
        matches.append(
            (score, name, is_collapsed, location, (template_rgb.shape[1], template_rgb.shape[0]))
        )

    matches.sort(key=lambda item: item[0], reverse=True)
    best_score, best_name, is_collapsed, location, size = matches[0]
    second_score = matches[1][0]
    margin = best_score - second_score

    if best_score < profile.toggle_match_threshold or margin < profile.toggle_margin:
        evidence = (
            f"toggle best={best_name} score={best_score:.3f}",
            f"toggle second={matches[1][1]} score={second_score:.3f}",
            f"toggle margin={margin:.3f}",
        )
        return SoulTaskPanelObservation(
            None,
            max(0.0, best_score),
            (left + location[0], top + location[1]) if location else None,
            SoulTaskDetectionReason.PANEL_STATE_UNKNOWN,
            evidence=evidence,
            matched_template=best_name,
        )

    absolute = (left + location[0], top + location[1]) if location else None
    click_location = (
        (absolute[0] + size[0] // 2, absolute[1] + size[1] // 2)
        if absolute
        else None
    )
    confidence = max(0.0, min(1.0, 0.5 + 0.5 * best_score))
    reason = SoulTaskDetectionReason.PANEL_COLLAPSED if is_collapsed else SoulTaskDetectionReason.PANEL_EXPANDED
    evidence = (
        f"toggle matched={best_name} score={best_score:.3f}",
        f"toggle margin={margin:.3f}",
        "right arrow means collapsed; left arrow means expanded",
    )
    return SoulTaskPanelObservation(
        collapsed=is_collapsed,
        confidence=confidence,
        match_location=absolute,
        reason=reason,
        evidence=evidence,
        click_location=click_location,
        matched_template=best_name,
    )


def detect_soul_task_claimed_icon(
    image: Image.Image | Frame,
    *,
    profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI,
    template_path: str | Path | None = None,
) -> SoulTaskObservation:
    try:
        image = _as_pil_image(image)
    except (TypeError, ValueError):
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.IMAGE_INVALID, 0.0, False)
    if image.width <= 0 or image.height <= 0:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.IMAGE_INVALID, 0.0, False)
    left, top, right, bottom = profile.claimed_icon_region.pixel(image.width, image.height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    if right <= left or bottom <= top:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.ROI_INVALID, 0.0, False)
    resolved_template = _resolve_template_path(template_path or profile.template_path)
    try:
        template = _load_claimed_icon_template(resolved_template)
    except FileNotFoundError:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.TEMPLATE_MISSING, 0.0, False,
                                    evidence=(f"claimed icon template not found: {resolved_template}",))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, binascii.Error):
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.TEMPLATE_INVALID, 0.0, False,
                                    evidence=(f"claimed icon template could not be decoded: {resolved_template}",))
    roi = np.asarray(image, dtype=np.float32)[top:bottom, left:right]
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
