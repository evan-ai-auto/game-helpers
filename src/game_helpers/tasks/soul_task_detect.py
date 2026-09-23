"""命魂任务面板折叠态与已领取图标检测。"""
from __future__ import annotations

import binascii
import json
from collections import deque
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


def _largest_bright_component(mask: np.ndarray) -> list[tuple[int, int]]:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            queue: deque[tuple[int, int]] = deque([(y, x)])
            seen[y, x] = True
            cells: list[tuple[int, int]] = []
            while queue:
                cy, cx = queue.popleft()
                cells.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            if len(cells) > len(best):
                best = cells
    return best


# Arrow geometry must be strong enough before it can override template class.
ARROW_DIRECTION_MIN_ABS_SCORE = 0.55
# Gray/white toggle arrows stay; saturated icon colors (blue/yellow) are excluded.
ARROW_MAX_CHROMA = 35.0


def _arrow_pointing_from_roi(roi: np.ndarray) -> tuple[str | None, float]:
    """Infer arrow pointing direction from bright low-chroma pixels under 指引.

    Returns ``(\"right\"|\"left\"|None, score)``. Right-pointing => collapsed;
    left-pointing => expanded. Uses tip-vs-base geometry on the largest bright
    gray blob so colorful shortcut icons do not dominate.
    """
    if roi.ndim != 3 or roi.shape[0] < 8 or roi.shape[1] < 8:
        return None, 0.0
    height, width = roi.shape[:2]
    y0 = int(height * 0.42)
    x1 = max(12, int(width * 0.70))
    band_rgb = roi[y0:height, 0:x1]
    luminance = band_rgb.mean(axis=2)
    chroma = band_rgb.max(axis=2) - band_rgb.min(axis=2)
    low_chroma = chroma <= ARROW_MAX_CHROMA

    def _cells_for_threshold(min_luma: float, percentile: float) -> list[tuple[int, int]]:
        threshold = max(min_luma, float(np.percentile(luminance, percentile)))
        mask = (luminance >= threshold) & low_chroma
        return _largest_bright_component(mask)

    cells = _cells_for_threshold(200.0, 90.0)
    if len(cells) < 12:
        cells = _cells_for_threshold(170.0, 82.0)
    if len(cells) < 12:
        return None, 0.0

    ys = np.array([y for y, _ in cells])
    xs = np.array([x for _, x in cells])
    rows = sorted(set(ys.tolist()))
    widths: list[float] = []
    mids: list[float] = []
    for row in rows:
        row_xs = xs[ys == row]
        widths.append(float(row_xs.max() - row_xs.min() + 1))
        mids.append(float(0.5 * (row_xs.min() + row_xs.max())))
    if len(widths) < 4:
        return None, 0.0

    order = np.argsort(np.asarray(widths))
    tip_count = max(2, len(order) // 4)
    tip_mid = float(np.mean([mids[index] for index in order[:tip_count]]))
    base_mid = float(np.mean([mids[index] for index in order[-tip_count:]]))
    span = max(float(xs.max() - xs.min() + 1) * 0.5, 1.0)
    # Game toggle assets: right-pointing has tip/stem left of the wide base.
    score = (base_mid - tip_mid) / span
    if abs(score) < 0.10:
        return None, score
    return ("right" if score > 0 else "left"), score


def detect_soul_task_panel_collapsed(
    image: Image.Image | Frame,
    *,
    profile: SoulTaskUiProfile = DEFAULT_SOUL_TASK_UI,
) -> SoulTaskPanelObservation:
    """Detect collapsed/expanded state from the real arrow assets.

    User-provided evidence defines the semantics:
      * right-pointing arrow (light or grey) = collapsed
      * left-pointing arrow (light) = expanded

    Direction of a strong low-chroma arrow blob is preferred when clear;
    template NCC remains for match location / scores and as fallback when
    geometry is weak. Evidence records template disagreement when present.

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
    best_score, best_name, _best_collapsed, location, size = matches[0]
    second_score, second_name = matches[1][0], matches[1][1]

    collapsed_matches = [item for item in matches if item[2]]
    expanded_matches = [item for item in matches if not item[2]]
    best_collapsed = max(collapsed_matches, key=lambda item: item[0])
    best_expanded = max(expanded_matches, key=lambda item: item[0])
    collapsed_score = best_collapsed[0]
    expanded_score = best_expanded[0]

    pointing, point_score = _arrow_pointing_from_roi(roi)
    decide: str | None = None
    arrow_rejected: str | None = None
    chosen: tuple[float, str, bool, tuple[int, int] | None, tuple[int, int]] | None = None
    is_collapsed: bool | None = None

    # After low-chroma filtering, strong geometry is trusted: polluted colorful
    # icons often still inflate the wrong template class on expanded strips.
    if pointing is not None and abs(point_score) >= ARROW_DIRECTION_MIN_ABS_SCORE:
        if pointing == "right":
            chosen = best_collapsed
            is_collapsed = True
            decide = "arrow-direction"
        else:
            chosen = best_expanded
            is_collapsed = False
            decide = "arrow-direction"
        template_agrees = (
            (pointing == "right" and collapsed_score >= expanded_score)
            or (pointing == "left" and expanded_score >= collapsed_score)
        )
        if not template_agrees:
            arrow_rejected = "disagree"
    elif pointing is not None:
        arrow_rejected = "weak"

    if chosen is None:
        class_margin = collapsed_score - expanded_score
        if (
            collapsed_score >= profile.toggle_match_threshold
            and class_margin >= profile.toggle_margin
        ):
            chosen = best_collapsed
            is_collapsed = True
            decide = "template-class"
        elif (
            expanded_score >= profile.toggle_match_threshold
            and -class_margin >= profile.toggle_margin
        ):
            chosen = best_expanded
            is_collapsed = False
            decide = "template-class"
        else:
            absolute = (left + location[0], top + location[1]) if location else None
            visual_center = (
                (absolute[0] + size[0] // 2, absolute[1] + size[1] // 2)
                if absolute
                else None
            )
            evidence = (
                f"toggle best={best_name} score={best_score:.3f}",
                f"toggle second={second_name} score={second_score:.3f}",
                f"collapsed={collapsed_score:.3f} expanded={expanded_score:.3f}",
                f"arrow-direction={pointing or 'unknown'} score={point_score:.3f}",
                *(
                    (f"arrow-rejected={arrow_rejected}",)
                    if arrow_rejected
                    else ()
                ),
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

    assert chosen is not None and is_collapsed is not None and decide is not None
    chosen_score, chosen_name, _, chosen_location, chosen_size = chosen
    absolute = (
        (left + chosen_location[0], top + chosen_location[1]) if chosen_location else None
    )
    visual_center = (
        (absolute[0] + chosen_size[0] // 2, absolute[1] + chosen_size[1] // 2)
        if absolute
        else None
    )
    confidence = max(0.0, min(1.0, 0.5 + 0.5 * chosen_score))
    reason = (
        SoulTaskDetectionReason.PANEL_COLLAPSED
        if is_collapsed
        else SoulTaskDetectionReason.PANEL_EXPANDED
    )
    evidence = (
        f"toggle matched={chosen_name} score={chosen_score:.3f}",
        f"decide={decide}",
        f"arrow-direction={pointing or 'unknown'} score={point_score:.3f}",
        *(
            (f"arrow-rejected={arrow_rejected}",)
            if arrow_rejected
            else ()
        ),
        "right arrow means collapsed; left arrow means expanded",
    )
    return SoulTaskPanelObservation(
        collapsed=is_collapsed,
        confidence=confidence,
        match_location=absolute,
        reason=reason,
        evidence=evidence,
        click_location=visual_center,
        matched_template=chosen_name,
        match_score=float(chosen_score),
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
