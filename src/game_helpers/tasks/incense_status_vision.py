"""摄妖香使用状态：右侧条折叠/展开、闹钟悬停与 tooltip OCR。"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ..actions.background_input import BackgroundInput
from ..capture.models import Frame
from ..core.models import Rect
from .soul_task_match import as_pil_image, load_template, masked_match, resolve_template_path
from .soul_task_detect import detect_soul_task_panel_collapsed
from .soul_task_models import DEFAULT_SOUL_TASK_UI, UiRect
from .verification_session import VerificationSession

# Provisional 800x600 ROIs — calibrate with real right-strip captures.
RIGHT_TOGGLE_REGION = UiRect(760 / 800, 90 / 600, 800 / 800, 220 / 600)
CLOCK_SEARCH_REGION = UiRect(700 / 800, 60 / 600, 800 / 800, 280 / 600)
CLOCK_TEMPLATE_PATH = "data/assets/ui/resolutions/800x600/incense_clock_icon.png"
UNUSED_TOOLTIP_TEXT = "暂无时间提醒信息"
REMAINING_PATTERN = re.compile(r"(?:剩余)?\s*(\d+)\s*分")


@dataclass(frozen=True)
class IncenseUsageObservation:
    usage: str  # unused | active | unknown | asset_missing | panel_collapsed | panel_unknown
    remaining_minutes: int | None
    panel_collapsed: bool | None
    clock_found: bool
    clock_score: float
    clock_location: tuple[int, int] | None
    hover_point: tuple[int, int] | None
    tooltip_text: str
    evidence: tuple[str, ...]


def parse_incense_tooltip(text: str) -> tuple[str, int | None]:
    """Map tooltip OCR text to usage + optional remaining minutes."""
    normalized = "".join(text.split())
    if not normalized:
        return "unknown", None
    if UNUSED_TOOLTIP_TEXT.replace(" ", "") in normalized or "暂无时间提醒" in normalized:
        return "unused", None
    match = REMAINING_PATTERN.search(normalized)
    if match:
        return "active", int(match.group(1))
    if "剩余" in normalized and "分" in normalized:
        digits = re.findall(r"\d+", normalized)
        if digits:
            return "active", int(digits[0])
    return "unknown", None


def detect_right_strip_collapsed(image: Image.Image | Frame):
    """Reuse shortcut arrow detect with the right-strip ROI."""
    from dataclasses import replace

    profile = replace(
        DEFAULT_SOUL_TASK_UI,
        collapsed_toggle_region=RIGHT_TOGGLE_REGION,
    )
    return detect_soul_task_panel_collapsed(image, profile=profile)


def _match_clock(image: Image.Image) -> tuple[bool, float, tuple[int, int] | None, tuple[int, int, int, int]]:
    template_path = resolve_template_path(CLOCK_TEMPLATE_PATH)
    left, top, right, bottom = CLOCK_SEARCH_REGION.pixel(image.width, image.height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    roi_box = (left, top, right, bottom)
    if not template_path.is_file():
        raise FileNotFoundError(str(template_path))
    if right <= left or bottom <= top:
        return False, 0.0, None, roi_box
    roi = np.asarray(image, dtype=np.float32)[top:bottom, left:right]
    template_rgb, alpha = load_template(template_path)
    score, location = masked_match(roi, template_rgb, alpha)
    threshold = 0.78
    if location is None or score < threshold:
        return False, float(score), None, roi_box
    absolute = (left + location[0], top + location[1])
    center = (
        absolute[0] + template_rgb.shape[1] // 2,
        absolute[1] + template_rgb.shape[0] // 2,
    )
    return True, float(score), center, roi_box


def _ocr_tooltip(image: Image.Image, hover: tuple[int, int]) -> str:
    from ..vision.windows_ocr import WindowsNativeOCRBackend

    # Tooltip usually appears near the hovered icon; take a band around it.
    pad_x, pad_y = 120, 80
    region = Rect(
        max(0, hover[0] - pad_x),
        max(0, hover[1] - pad_y),
        min(image.width, hover[0] + pad_x),
        min(image.height, hover[1] + pad_y + 40),
    )
    try:
        backend = WindowsNativeOCRBackend(language="zh-Hans-CN")
    except RuntimeError:
        backend = WindowsNativeOCRBackend()
    lines = backend.read(image, region=region)
    return " ".join(item.text for item in lines)


def detect_incense_usage(
    session: VerificationSession,
    output_dir: str | Path,
    *,
    hover_settle_seconds: float = 0.45,
) -> IncenseUsageObservation:
    """Capture, resolve right-strip state, hover clock, OCR tooltip."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    image = as_pil_image(session.capture_frame()).convert("RGB")
    image.save(output / "capture.png")

    toggle_box = RIGHT_TOGGLE_REGION.pixel(image.width, image.height)
    image.crop(toggle_box).save(output / "right-toggle-roi.png")
    panel = detect_right_strip_collapsed(image)
    evidence = [
        f"panel_collapsed={panel.collapsed}",
        f"panel_template={panel.matched_template}",
        f"panel_score={panel.match_score:.3f}",
        *list(panel.evidence),
    ]

    if panel.collapsed is None:
        return IncenseUsageObservation(
            "panel_unknown",
            None,
            None,
            False,
            0.0,
            None,
            None,
            "",
            tuple(evidence + ["右侧条折叠/展开状态未知"]),
        )
    if panel.collapsed is True:
        return IncenseUsageObservation(
            "panel_collapsed",
            None,
            True,
            False,
            0.0,
            None,
            None,
            "",
            tuple(evidence + ["右侧条为折叠态，未悬停闹钟"]),
        )

    try:
        found, score, hover, clock_box = _match_clock(image)
    except FileNotFoundError as exc:
        return IncenseUsageObservation(
            "asset_missing",
            None,
            False,
            False,
            0.0,
            None,
            None,
            "",
            tuple(evidence + [f"闹钟模板缺失: {exc}", f"请提供 {CLOCK_TEMPLATE_PATH}"]),
        )

    image.crop(clock_box).save(output / "clock-search-roi.png")
    evidence.append(f"clock_score={score:.3f}")
    if not found or hover is None:
        return IncenseUsageObservation(
            "unknown",
            None,
            False,
            False,
            score,
            None,
            None,
            "",
            tuple(evidence + ["未匹配到闹钟图标"]),
        )

    # Approximate clock crop around match for evidence.
    cw = max(16, (clock_box[2] - clock_box[0]) // 4)
    ch = max(16, (clock_box[3] - clock_box[1]) // 4)
    clock_crop = (
        max(0, hover[0] - cw // 2),
        max(0, hover[1] - ch // 2),
        min(image.width, hover[0] + cw // 2),
        min(image.height, hover[1] + ch // 2),
    )
    image.crop(clock_crop).save(output / "clock-roi.png")

    BackgroundInput(session.selected.hwnd).mouse_move(*hover)
    time.sleep(hover_settle_seconds)
    hovered = as_pil_image(session.capture_frame()).convert("RGB")
    pad_x, pad_y = 120, 80
    tip_box = (
        max(0, hover[0] - pad_x),
        max(0, hover[1] - pad_y),
        min(hovered.width, hover[0] + pad_x),
        min(hovered.height, hover[1] + pad_y + 40),
    )
    hovered.crop(tip_box).save(output / "tooltip-roi.png")

    try:
        tooltip_text = _ocr_tooltip(hovered, hover)
    except RuntimeError as exc:
        return IncenseUsageObservation(
            "unknown",
            None,
            False,
            True,
            score,
            hover,
            hover,
            "",
            tuple(evidence + [f"OCR 不可用: {exc}"]),
        )

    usage, minutes = parse_incense_tooltip(tooltip_text)
    evidence.append(f"tooltip={tooltip_text!r}")
    return IncenseUsageObservation(
        usage=usage,
        remaining_minutes=minutes,
        panel_collapsed=False,
        clock_found=True,
        clock_score=score,
        clock_location=hover,
        hover_point=hover,
        tooltip_text=tooltip_text,
        evidence=tuple(evidence),
    )


__all__ = [
    "CLOCK_TEMPLATE_PATH",
    "IncenseUsageObservation",
    "RIGHT_TOGGLE_REGION",
    "detect_incense_usage",
    "detect_right_strip_collapsed",
    "parse_incense_tooltip",
]
