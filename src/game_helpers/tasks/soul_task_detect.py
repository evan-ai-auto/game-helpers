"""命魂任务面板折叠态与已领取图标检测。"""
from __future__ import annotations

import binascii
import json
from pathlib import Path

import numpy as np
from PIL import Image

from ..capture.models import Frame
from .soul_task_match import (
    as_pil_image,
    load_claimed_icon_template,
    load_template,
    masked_match,
    ncc,
    resolve_template_path,
    toggle_templates,
)
from .soul_task_models import (
    DEFAULT_SOUL_TASK_UI,
    SoulTaskDetectionReason,
    SoulTaskObservation,
    SoulTaskPanelObservation,
    SoulTaskStatus,
    SoulTaskUiProfile,
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

    ``match_location`` / ``click_location`` describe the *visual* match only.
    Production clicks must use the calibrated fixed coordinate, not these fields.
    """
    try:
        image = as_pil_image(image)
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
    for name, path, is_collapsed in toggle_templates(profile):
        try:
            template_rgb, alpha = load_template(path)
        except FileNotFoundError:
            return SoulTaskPanelObservation(
                None, 0.0, None, SoulTaskDetectionReason.TOGGLE_TEMPLATE_MISSING,
                evidence=(f"toggle template not found: {resolve_template_path(path)}",)
            )
        except (OSError, ValueError):
            return SoulTaskPanelObservation(
                None, 0.0, None, SoulTaskDetectionReason.TOGGLE_TEMPLATE_INVALID,
                evidence=(f"toggle template invalid: {resolve_template_path(path)}",)
            )
        score, location = masked_match(roi, template_rgb, alpha)
        matches.append(
            (score, name, is_collapsed, location, (template_rgb.shape[1], template_rgb.shape[0]))
        )

    matches.sort(key=lambda item: item[0], reverse=True)
    best_score, best_name, is_collapsed, location, size = matches[0]
    second_score, second_name = matches[1][0], matches[1][1]
    margin = best_score - second_score

    absolute = (left + location[0], top + location[1]) if location else None
    visual_center = (
        (absolute[0] + size[0] // 2, absolute[1] + size[1] // 2)
        if absolute
        else None
    )

    if best_score < profile.toggle_match_threshold or margin < profile.toggle_margin:
        evidence = (
            f"toggle best={best_name} score={best_score:.3f}",
            f"toggle second={second_name} score={second_score:.3f}",
            f"toggle margin={margin:.3f}",
        )
        return SoulTaskPanelObservation(
            None,
            max(0.0, best_score),
            absolute,
            SoulTaskDetectionReason.PANEL_STATE_UNKNOWN,
            evidence=evidence,
            click_location=visual_center,
            matched_template=best_name,
            match_score=float(best_score),
            second_template=second_name,
            second_score=float(second_score),
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
        click_location=visual_center,
        matched_template=best_name,
        match_score=float(best_score),
        second_template=second_name,
        second_score=float(second_score),
    )


def detect_soul_task_claimed_icon(
    image: Image.Image | Frame,
    *,
    profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI,
    template_path: str | Path | None = None,
) -> SoulTaskObservation:
    try:
        image = as_pil_image(image)
    except (TypeError, ValueError):
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.IMAGE_INVALID, 0.0, False)
    if image.width <= 0 or image.height <= 0:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.IMAGE_INVALID, 0.0, False)
    left, top, right, bottom = profile.claimed_icon_region.pixel(image.width, image.height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    if right <= left or bottom <= top:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.ROI_INVALID, 0.0, False)
    resolved_template = resolve_template_path(template_path or profile.template_path)
    try:
        template = load_claimed_icon_template(resolved_template)
    except FileNotFoundError:
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.TEMPLATE_MISSING, 0.0, False,
                                    evidence=(f"claimed icon template not found: {resolved_template}",))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, binascii.Error):
        return SoulTaskObservation(SoulTaskStatus.UNKNOWN, SoulTaskDetectionReason.TEMPLATE_INVALID, 0.0, False,
                                    evidence=(f"claimed icon template could not be decoded: {resolved_template}",))
    roi = np.asarray(image, dtype=np.float32)[top:bottom, left:right]
    score, location = ncc(roi, template)
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
