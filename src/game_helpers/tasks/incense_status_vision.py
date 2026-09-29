"""摄妖香使用状态：右侧条折叠/展开、闹钟悬停与 tooltip OCR。"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from ..actions.background_input import BackgroundInput
from ..capture.models import Frame
from ..core.models import Rect
from .soul_task_match import as_pil_image, load_template, masked_match, resolve_template_path
from .soul_task_detect import ARROW_Y_FRACTION_RANGE_TOP, detect_soul_task_panel_collapsed
from .soul_task_models import DEFAULT_SOUL_TASK_UI, UiRect
from .verification_session import VerificationSession

# Provisional 800x600 ROIs — calibrate with real right-strip captures.
RIGHT_TOGGLE_REGION = UiRect(760 / 800, 90 / 600, 800 / 800, 220 / 600)
# 任务追踪标题栏闹钟约在 (641,109)；旧 ROI [700,60,800,280] 偏右且过深，会落到任务正文假阳性。
CLOCK_SEARCH_REGION = UiRect(620 / 800, 90 / 600, 800 / 800, 145 / 600)
CLOCK_TEMPLATE_PATH = "data/assets/ui/resolutions/800x600/incense_clock_icon.png"
UNUSED_TOOLTIP_TEXT = "暂无时间提醒信息"
REMAINING_PATTERN = re.compile(r"(?:剩余)?\s*(\d+)\s*分")
# OCR landed on 任务追踪 body instead of incense tooltip.
TASK_TRACKER_OCR_MARKERS = ("任务追踪", "宠环", "签到答题", "任务积分")
# Evidence crop around the PostMessage hover target (clock center).
HOVER_TARGET_HALF = 24
# Tip OCR: narrow band above/left of the clock, not the whole task panel.
TOOLTIP_OCR_WIDTH = 180
TOOLTIP_OCR_HEIGHT = 56
TOOLTIP_OCR_LEFT = 20


@dataclass(frozen=True)
class IncenseUsageObservation:
    usage: str  # unused | active | unknown | asset_missing | panel_collapsed | panel_unknown
    remaining_minutes: int | None
    panel_collapsed: bool | None
    panel_template: str | None
    panel_score: float
    panel_confidence: float
    panel_reason: str
    panel_match_location: tuple[int, int] | None
    panel_search_roi: tuple[int, int, int, int]
    clock_found: bool
    clock_score: float
    clock_location: tuple[int, int] | None
    clock_reason: str
    clock_search_roi: tuple[int, int, int, int]
    clock_threshold: float
    hover_point: tuple[int, int] | None
    tooltip_text: str
    evidence: tuple[str, ...]


def parse_incense_tooltip(text: str) -> tuple[str, int | None]:
    """Map tooltip OCR text to usage + optional remaining minutes."""
    normalized = "".join(text.split())
    if not normalized:
        return "unknown", None
    if any(marker in normalized for marker in TASK_TRACKER_OCR_MARKERS):
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


def tooltip_looks_like_task_tracker(text: str) -> bool:
    """True when OCR captured 任务追踪 chrome instead of an incense hover tip."""
    normalized = "".join(text.split())
    return any(marker in normalized for marker in TASK_TRACKER_OCR_MARKERS)


def detect_right_strip_collapsed(image: Image.Image | Frame):
    """Detect the incense right-strip with 1,1,12,2-specific arrow semantics."""
    from dataclasses import replace

    profile = replace(
        DEFAULT_SOUL_TASK_UI,
        collapsed_toggle_region=RIGHT_TOGGLE_REGION,
    )
    return detect_soul_task_panel_collapsed(
        image,
        profile=profile,
        right_arrow_collapsed=False,
        # Top-band geometry on this strip yields |score|≈0.35–0.40; keep below soul default.
        arrow_direction_min_abs_score=0.35,
        arrow_y_fraction_range=ARROW_Y_FRACTION_RANGE_TOP,
    )


def _match_clock(
    image: Image.Image,
) -> tuple[bool, float, tuple[int, int] | None, str, tuple[int, int, int, int], float, tuple[str, ...]]:
    """Match the clock using the same evidence contract as UI icon vision."""
    template_path = resolve_template_path(CLOCK_TEMPLATE_PATH)
    threshold = 0.78
    left, top, right, bottom = CLOCK_SEARCH_REGION.pixel(image.width, image.height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    roi_box = (left, top, right, bottom)
    if not template_path.is_file():
        raise FileNotFoundError(str(template_path))
    if right <= left or bottom <= top:
        return (False, 0.0, None, "invalid_detection_region", roi_box, threshold, ("invalid detection region",))
    roi = np.asarray(image, dtype=np.float32)[top:bottom, left:right]
    template_rgb, alpha = load_template(template_path)
    score, location = masked_match(roi, template_rgb, alpha)
    found = location is not None and score >= threshold
    best_location = (left + location[0], top + location[1]) if location else None
    reason = "icon_found" if found else "icon_not_found"
    evidence = (
        "target=demon_repellent_incense.clock",
        f"template={template_path}",
        f"score={score:.3f}",
        f"threshold={threshold:.3f}",
        f"roi={list(roi_box)}",
    )
    if not found or best_location is None:
        return (False, max(0.0, float(score)), None, reason, roi_box, threshold, evidence)
    absolute = best_location
    center = (
        absolute[0] + template_rgb.shape[1] // 2,
        absolute[1] + template_rgb.shape[0] // 2,
    )
    return (True, max(0.0, float(score)), center, reason, roi_box, threshold, evidence)


def _clamp_box(
    left: int, top: int, right: int, bottom: int, *, width: int, height: int
) -> tuple[int, int, int, int]:
    left = max(0, min(left, width - 1))
    top = max(0, min(top, height - 1))
    right = max(left + 1, min(right, width))
    bottom = max(top + 1, min(bottom, height))
    return left, top, right, bottom


def hover_target_box(
    hover: tuple[int, int], *, width: int, height: int, half: int = HOVER_TARGET_HALF
) -> tuple[int, int, int, int]:
    """Client-pixel box around the PostMessage hover target (clock center)."""
    hx, hy = hover
    return _clamp_box(hx - half, hy - half, hx + half, hy + half, width=width, height=height)


def tooltip_ocr_box(
    hover: tuple[int, int], *, width: int, height: int
) -> tuple[int, int, int, int]:
    """Narrow band above/left of the clock for incense tip OCR."""
    hx, hy = hover
    left = hx - TOOLTIP_OCR_LEFT - TOOLTIP_OCR_WIDTH // 2
    right = left + TOOLTIP_OCR_WIDTH
    bottom = hy - 4
    top = bottom - TOOLTIP_OCR_HEIGHT
    if top < 0:
        top = 0
        bottom = min(height, TOOLTIP_OCR_HEIGHT)
    return _clamp_box(left, top, right, bottom, width=width, height=height)


def _save_hover_on_search_roi(
    image: Image.Image,
    *,
    search_box: tuple[int, int, int, int],
    hover: tuple[int, int],
    path: Path,
) -> None:
    """Annotate clock-search ROI with the hover crosshair for manual review."""
    from PIL import ImageDraw

    crop = image.crop(search_box).convert("RGB")
    draw = ImageDraw.Draw(crop)
    lx, ty, _, _ = search_box
    hx, hy = hover[0] - lx, hover[1] - ty
    draw.ellipse((hx - 6, hy - 6, hx + 6, hy + 6), outline=(255, 0, 0), width=2)
    draw.line((hx - 10, hy, hx + 10, hy), fill=(255, 0, 0), width=1)
    draw.line((hx, hy - 10, hx, hy + 10), fill=(255, 0, 0), width=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(path)


def _ocr_tooltip(image: Image.Image, hover: tuple[int, int]) -> str:
    from ..vision.windows_ocr import WindowsNativeOCRBackend

    left, top, right, bottom = tooltip_ocr_box(hover, width=image.width, height=image.height)
    region = Rect(left, top, right, bottom)
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
    progress: Callable[[str], None] | None = None,
) -> IncenseUsageObservation:
    """Capture and verify the full pre-hover visual chain, then hover and OCR."""
    def log(message: str) -> None:
        if progress is not None:
            progress(message)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    log("[1/5] START 捕获当前画面")
    image = as_pil_image(session.capture_frame()).convert("RGB")
    image.save(output / "capture.png")
    log("[1/5] PASS 已保存 capture.png；进入右侧条状态识别")

    toggle_box = RIGHT_TOGGLE_REGION.pixel(image.width, image.height)
    image.crop(toggle_box).save(output / "right-toggle-roi.png")
    log("[2/5] START 识别右侧条折叠/展开状态（12,2：右=展开，左=折叠）")
    panel = detect_right_strip_collapsed(image)
    panel_state = "expanded" if panel.collapsed is False else "collapsed" if panel.collapsed is True else "unknown"
    log(
        f"[2/5] 识别结果：右侧条={('展开' if panel.collapsed is False else '折叠' if panel.collapsed is True else '未知')}；"
        f"方向语义=右箭头表示展开/左箭头表示折叠；"
        f"匹配模板={panel.matched_template}；匹配分数={panel.match_score:.3f}；"
        f"置信度={panel.confidence:.3f}；原因={getattr(panel.reason, 'value', str(panel.reason))}"
    )
    evidence = [
        f"panel_collapsed={panel.collapsed}",
        f"panel_template={panel.matched_template}",
        f"panel_score={panel.match_score:.3f}",
        f"panel_confidence={panel.confidence:.3f}",
        f"panel_reason={getattr(panel.reason, 'value', str(panel.reason))}",
        f"panel_match_location={panel.match_location}",
        *list(panel.evidence),
    ]

    empty_roi = toggle_box
    if panel.collapsed is None:
        log("[2/5] BLOCKED 无法确认右侧条状态；流程停止，未进入闹钟检测")
        return IncenseUsageObservation(
            usage="panel_unknown",
            remaining_minutes=None,
            panel_collapsed=None,
            panel_template=panel.matched_template,
            panel_score=panel.match_score,
            panel_confidence=panel.confidence,
            panel_reason=getattr(panel.reason, "value", str(panel.reason)),
            panel_match_location=panel.match_location,
            panel_search_roi=toggle_box,
            clock_found=False,
            clock_score=0.0,
            clock_location=None,
            clock_reason="panel_unknown",
            clock_search_roi=empty_roi,
            clock_threshold=0.0,
            hover_point=None,
            tooltip_text="",
            evidence=tuple(evidence + ["pre_hover_verification=FAIL", "右侧条折叠/展开状态未知"]),
        )
    if panel.collapsed is True:
        log("[2/5] BLOCKED 当前为折叠态；流程停止，不执行闹钟检测/鼠标移动")
        return IncenseUsageObservation(
            usage="panel_collapsed",
            remaining_minutes=None,
            panel_collapsed=True,
            panel_template=panel.matched_template,
            panel_score=panel.match_score,
            panel_confidence=panel.confidence,
            panel_reason=getattr(panel.reason, "value", str(panel.reason)),
            panel_match_location=panel.match_location,
            panel_search_roi=toggle_box,
            clock_found=False,
            clock_score=0.0,
            clock_location=None,
            clock_reason="panel_blocked",
            clock_search_roi=empty_roi,
            clock_threshold=0.0,
            hover_point=None,
            tooltip_text="",
            evidence=tuple(evidence + ["pre_hover_verification=BLOCKED", "右侧条为折叠态，未进入闹钟检测"]),
        )

    log("[3/5] START 在已展开右侧条中检测闹钟图标")
    try:
        (
            found,
            score,
            hover,
            clock_reason,
            clock_box,
            clock_threshold,
            clock_evidence,
        ) = _match_clock(image)
    except FileNotFoundError as exc:
        return IncenseUsageObservation(
            usage="asset_missing",
            remaining_minutes=None,
            panel_collapsed=False,
            panel_template=panel.matched_template,
            panel_score=panel.match_score,
            panel_confidence=panel.confidence,
            panel_reason=getattr(panel.reason, "value", str(panel.reason)),
            panel_match_location=panel.match_location,
            panel_search_roi=toggle_box,
            clock_found=False,
            clock_score=0.0,
            clock_location=None,
            clock_reason="template_missing",
            clock_search_roi=CLOCK_SEARCH_REGION.pixel(image.width, image.height),
            clock_threshold=0.78,
            hover_point=None,
            tooltip_text="",
            evidence=tuple(
                evidence
                + [
                    "pre_hover_verification=FAIL",
                    f"闹钟模板缺失: {exc}",
                    f"请提供 {CLOCK_TEMPLATE_PATH}",
                ]
            ),
        )

    image.crop(clock_box).save(output / "clock-search-roi.png")
    log(
        f"[3/5] 识别结果：闹钟图标={'已识别' if found else '未识别'}；"
        f"匹配分数={score:.3f}；阈值={clock_threshold:.3f}；原因={clock_reason}"
    )
    evidence.extend(clock_evidence)
    evidence.append(f"clock_reason={clock_reason}")
    evidence.append(f"pre_hover_verification={'PASS' if found and hover else 'FAIL'}")

    if not found or hover is None:
        log("[3/5] BLOCKED 未确认闹钟图标；流程停止，不执行鼠标移动")
        return IncenseUsageObservation(
            usage="unknown",
            remaining_minutes=None,
            panel_collapsed=False,
            panel_template=panel.matched_template,
            panel_score=panel.match_score,
            panel_confidence=panel.confidence,
            panel_reason=getattr(panel.reason, "value", str(panel.reason)),
            panel_match_location=panel.match_location,
            panel_search_roi=toggle_box,
            clock_found=False,
            clock_score=score,
            clock_location=None,
            clock_reason=clock_reason,
            clock_search_roi=clock_box,
            clock_threshold=clock_threshold,
            hover_point=None,
            tooltip_text="",
            evidence=tuple(evidence + ["未匹配到闹钟图标"]),
        )

    log(f"[4/5] START 闹钟验证通过；准备鼠标移动到 hover_point={hover}")
    hover_box = hover_target_box(hover, width=image.width, height=image.height)
    image.crop(hover_box).save(output / "hover-target-roi.png")
    image.crop(hover_box).save(output / "clock-roi.png")
    _save_hover_on_search_roi(
        image,
        search_box=clock_box,
        hover=hover,
        path=output / "hover-on-search-roi.png",
    )
    evidence.append(f"hover_point={hover}")
    evidence.append(f"hover_target_roi={list(hover_box)}")
    log(f"[4/5] 已保存悬停证据：hover-target-roi.png / hover-on-search-roi.png；目标={hover}")

    # Only after panel + clock verification passes do we issue mouse movement.
    BackgroundInput(session.selected.hwnd).mouse_move(*hover)
    log(f"[4/5] PASS 已执行鼠标移动，等待 tooltip 稳定 {hover_settle_seconds:.2f}s")
    time.sleep(hover_settle_seconds)
    log("[5/5] START 捕获 tooltip 并执行 OCR（窄带，非悬停范围）")
    hovered = as_pil_image(session.capture_frame()).convert("RGB")
    tip_box = tooltip_ocr_box(hover, width=hovered.width, height=hovered.height)
    hovered.crop(tip_box).save(output / "tooltip-roi.png")
    evidence.append(f"tooltip_ocr_roi={list(tip_box)}")

    try:
        tooltip_text = _ocr_tooltip(hovered, hover)
    except RuntimeError as exc:
        log(f"[5/5] BLOCKED OCR 不可用：{exc}")
        return IncenseUsageObservation(
            usage="unknown",
            remaining_minutes=None,
            panel_collapsed=False,
            panel_template=panel.matched_template,
            panel_score=panel.match_score,
            panel_confidence=panel.confidence,
            panel_reason=getattr(panel.reason, "value", str(panel.reason)),
            panel_match_location=panel.match_location,
            panel_search_roi=toggle_box,
            clock_found=True,
            clock_score=score,
            clock_location=hover,
            clock_reason=clock_reason,
            clock_search_roi=clock_box,
            clock_threshold=clock_threshold,
            hover_point=hover,
            tooltip_text="",
            evidence=tuple(evidence + [f"OCR 不可用: {exc}"]),
        )

    usage, minutes = parse_incense_tooltip(tooltip_text)
    log(
        f"[5/5] 识别结果：tooltip OCR={tooltip_text!r}；"
        f"摄妖香状态={usage}；剩余分钟={minutes if minutes is not None else '未知'}"
    )
    evidence.append(f"tooltip={tooltip_text!r}")
    if tooltip_looks_like_task_tracker(tooltip_text):
        evidence.append("tooltip_rejected=task_tracker_ui")
        log("[5/5] BLOCKED OCR 命中任务追踪面板文本，判定为悬停未出 tip 或 OCR 仍偏到面板")
    return IncenseUsageObservation(
        usage=usage,
        remaining_minutes=minutes,
        panel_collapsed=False,
        panel_template=panel.matched_template,
        panel_score=panel.match_score,
        panel_confidence=panel.confidence,
        panel_reason=getattr(panel.reason, "value", str(panel.reason)),
        panel_match_location=panel.match_location,
        panel_search_roi=toggle_box,
        clock_found=True,
        clock_score=score,
        clock_location=hover,
        clock_reason=clock_reason,
        clock_search_roi=clock_box,
        clock_threshold=clock_threshold,
        hover_point=hover,
        tooltip_text=tooltip_text,
        evidence=tuple(evidence),
    )


__all__ = [
    "CLOCK_SEARCH_REGION",
    "CLOCK_TEMPLATE_PATH",
    "IncenseUsageObservation",
    "RIGHT_TOGGLE_REGION",
    "detect_incense_usage",
    "detect_right_strip_collapsed",
    "hover_target_box",
    "parse_incense_tooltip",
    "tooltip_looks_like_task_tracker",
    "tooltip_ocr_box",
]
