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
# Template is 26×25; dial hotspot inside match box (not raw bbox center).
# 171235 hotspot: red@(12,12) already on dial center.
CLOCK_HOVER_IN_TEMPLATE = (12, 12)
# Capture-frame hover → input client (Win32/image: origin top-left, Y down).
# 075115 Y lock (+8). Human: X +2 right from (-21,8) → (-19,8).
CLOCK_CAPTURE_TO_INPUT_NUDGE = (-19, 8)
UNUSED_TOOLTIP_TEXT = "暂无时间提醒信息"
REMAINING_PATTERN = re.compile(r"(?:剩余|余)\s*(\d+)\s*分")
# OCR landed on 任务追踪 body instead of incense tooltip.
TASK_TRACKER_OCR_MARKERS = ("任务追踪", "宠环", "签到答题", "任务积分")
# Evidence crop around the PostMessage hover target (clock center).
HOVER_TARGET_HALF = 24
# Tip OCR: keep band near the clock; left edge must stay on/near the right strip
# (20260929T123820: ROI left=545 bled into 长安城 stalls → false tip pixel deltas).
# 173118: tip ROI must be horizontal — width 160×2.
# 084546: primary tip ROI height 64→84 and top shifts up 20 (hy-8→hy-28).
# 085641: human — shift primary tip ROI down 5px (hy-28→hy-23).
# 100839: keep top; height +10 (84→94).
TOOLTIP_OCR_WIDTH = 320
TOOLTIP_OCR_HEIGHT = 94
TOOLTIP_OCR_BELOW_HEIGHT = 64
TOOLTIP_OCR_LEFT = 8
TOOLTIP_OCR_MIN_LEFT = 480
TOOLTIP_OCR_TOP_ABOVE_HOVER = 23
# Discovery sweep retired: locked transport+dwell only (no post/send/setcursor matrix).
# Always keep these few trial image dirs (pass or fail) for review.
HOVER_DIAGNOSTIC_SETTLE_SECONDS = (0.90,)
DEFAULT_HOVER_SETTLE_SECONDS = 0.90
# Exit far enough left of the right strip so enter-hover is unambiguous.
HOVER_EXIT_OFFSET = 140
# 1,1,12,3: message-only never tips; locked winner is SetCursorPos+PostMessage.
HOVER_DIAGNOSTIC_STRATEGIES = ("setcursor_postmessage",)
DEFAULT_HOVER_STRATEGY = "setcursor_postmessage"
INCENSE_TIP_MARKERS = ("暂无时间提醒", "剩余", "摄妖香", "时间提醒")
# Same point ×4: lock Y from 075115 +0_+2; X fine-tune after manual recheck.
HOVER_DIAGNOSTIC_OFFSETS = (
    (0, 0),
    (0, 0),
    (0, 0),
    (0, 0),
)


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
    # Tip title alone (154224 white tip); remaining may be OCR'd from left band.
    if "时间提醒" in normalized and "暂无" not in normalized:
        return "unknown", None
    return "unknown", None


def tooltip_looks_like_task_tracker(text: str) -> bool:
    """True when OCR captured 任务追踪 chrome instead of an incense hover tip."""
    normalized = "".join(text.split())
    return any(marker in normalized for marker in TASK_TRACKER_OCR_MARKERS)


def tooltip_looks_like_incense(text: str) -> bool:
    """True when OCR looks like an incense tip (not task-tracker chrome)."""
    usage, _minutes = parse_incense_tooltip(text)
    if usage in ("unused", "active"):
        return True
    normalized = "".join(text.split())
    if tooltip_looks_like_task_tracker(normalized):
        return False
    return any(marker in normalized for marker in INCENSE_TIP_MARKERS)


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
    """Match the clock using the same evidence contract as UI icon vision.

    Returns hover at the clock-face hot zone inside the match box (not raw bbox
    center — that sat between the clock and the gear in 20260929T132004).
    """
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
    hot_x, hot_y = CLOCK_HOVER_IN_TEMPLATE
    evidence = (
        "target=demon_repellent_incense.clock",
        f"template={template_path}",
        f"score={score:.3f}",
        f"threshold={threshold:.3f}",
        f"roi={list(roi_box)}",
        f"hover_in_template={list(CLOCK_HOVER_IN_TEMPLATE)}",
    )
    if not found or best_location is None:
        return (False, max(0.0, float(score)), None, reason, roi_box, threshold, evidence)
    absolute = best_location
    template_w = int(template_rgb.shape[1])
    template_h = int(template_rgb.shape[0])
    hover = (
        absolute[0] + min(max(0, hot_x), max(0, template_w - 1)),
        absolute[1] + min(max(0, hot_y), max(0, template_h - 1)),
    )
    evidence = evidence + (
        f"match_top_left={list(absolute)}",
        f"match_box={[absolute[0], absolute[1], absolute[0] + template_w, absolute[1] + template_h]}",
        f"hover_point={list(hover)}",
        "note=hover uses clock-face hotspot in template, not bbox center",
    )
    return (True, max(0.0, float(score)), hover, reason, roi_box, threshold, evidence)


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
    """Wide tip OCR band near the dial (horizontal stretch).

    173118: tip ROI must be wider on X (160→320) — not a tall strip.
    084546: height +20 and visual top -20 vs prior hy-8 / h=64 window.
    085641: visual top +5 (hy-28→hy-23).
    100839: height +10 (84→94), top unchanged.
    Left edge stays on/near the right strip to limit playfield bleed.
    """
    hx, hy = hover
    left = hx - TOOLTIP_OCR_WIDTH // 2 - TOOLTIP_OCR_LEFT
    left = max(TOOLTIP_OCR_MIN_LEFT, min(left, width - TOOLTIP_OCR_WIDTH))
    right = left + TOOLTIP_OCR_WIDTH
    top = max(0, hy - TOOLTIP_OCR_TOP_ABOVE_HOVER)
    bottom = top + TOOLTIP_OCR_HEIGHT
    return _clamp_box(left, top, right, bottom, width=width, height=height)


def tooltip_ocr_box_below(
    hover: tuple[int, int], *, width: int, height: int
) -> tuple[int, int, int, int]:
    """Secondary tip band just under the dial (same wide × short window)."""
    hx, hy = hover
    left = hx - TOOLTIP_OCR_WIDTH // 2
    left = max(TOOLTIP_OCR_MIN_LEFT, min(left, width - TOOLTIP_OCR_WIDTH))
    right = left + TOOLTIP_OCR_WIDTH
    top = hy + 2
    bottom = top + TOOLTIP_OCR_BELOW_HEIGHT
    return _clamp_box(left, top, right, bottom, width=width, height=height)


def tooltip_ocr_box_left(
    hover: tuple[int, int], *, width: int, height: int
) -> tuple[int, int, int, int]:
    """Left tip band for「余N分钟」/「剩余N分」(154224 dark tip left of clock)."""
    hx, hy = hover
    right = max(8, hx - 4)
    left = max(0, right - 120)
    top = max(0, hy - 28)
    bottom = min(height, hy + 28)
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

    try:
        backend = WindowsNativeOCRBackend(language="zh-Hans-CN")
    except RuntimeError:
        backend = WindowsNativeOCRBackend()

    candidates: list[str] = []
    for box in (
        tooltip_ocr_box(hover, width=image.width, height=image.height),
        tooltip_ocr_box_below(hover, width=image.width, height=image.height),
        tooltip_ocr_box_left(hover, width=image.width, height=image.height),
    ):
        lines = backend.read(image, region=Rect(*box))
        text = " ".join(item.text for item in lines).strip()
        if text:
            candidates.append(text)
    if not candidates:
        return ""
    # Merge bands so「时间提醒」+「余N分钟」can parse as active together (154224).
    merged = " ".join(candidates)
    usage, _minutes = parse_incense_tooltip(merged)
    if usage in ("unused", "active") or tooltip_looks_like_incense(merged):
        if not tooltip_looks_like_task_tracker(merged) or usage in ("unused", "active"):
            return merged
    for text in candidates:
        usage, _minutes = parse_incense_tooltip(text)
        if usage in ("unused", "active"):
            return text
    for text in candidates:
        if tooltip_looks_like_incense(text):
            return text
    for text in candidates:
        if not tooltip_looks_like_task_tracker(text):
            return text
    return candidates[0]


def _vision_hover_to_input(
    hover: tuple[int, int],
    *,
    width: int,
    height: int,
) -> tuple[int, int]:
    """Map capture-frame hover mark to the client point used for mouse input."""
    x = int(hover[0]) + int(CLOCK_CAPTURE_TO_INPUT_NUDGE[0])
    y = int(hover[1]) + int(CLOCK_CAPTURE_TO_INPUT_NUDGE[1])
    return (
        max(0, min(width - 1, x)),
        max(0, min(height - 1, y)),
    )


def _hover_transport(
    input_driver: BackgroundInput,
    *,
    strategy: str,
    x: int,
    y: int,
    session: VerificationSession | None = None,
) -> None:
    if strategy == "postmessage":
        input_driver.mouse_move(x, y)
        return
    if strategy == "sendmessage":
        input_driver.mouse_move_sync(x, y)
        return
    if strategy == "setcursor":
        if session is None:
            raise ValueError("setcursor hover requires VerificationSession")
        _set_cursor_to_client(session, x, y)
        return
    if strategy == "setcursor_postmessage":
        # Real cursor first, then WM_MOUSEMOVE so games that ignore either alone still tip.
        _hover_transport(
            input_driver, strategy="setcursor", x=x, y=y, session=session
        )
        input_driver.mouse_move(x, y)
        return
    raise ValueError(f"unknown hover transport: {strategy}")


def _set_cursor_to_client(session: VerificationSession, x: int, y: int) -> tuple[int, int]:
    """Move the OS cursor to WSGAME client (x,y); re-assert if focus nudges it."""
    from .manual_coordinate import client_to_screen, cursor_screen_pos, screen_to_client

    import ctypes

    target_screen = client_to_screen(session.selected.hwnd, int(x), int(y))
    if not ctypes.windll.user32.SetCursorPos(int(target_screen[0]), int(target_screen[1])):
        raise ctypes.WinError()
    time.sleep(0.02)
    actual_client = screen_to_client(session.selected.hwnd, *cursor_screen_pos())
    if abs(actual_client[0] - int(x)) > 2 or abs(actual_client[1] - int(y)) > 2:
        if not ctypes.windll.user32.SetCursorPos(int(target_screen[0]), int(target_screen[1])):
            raise ctypes.WinError()
        time.sleep(0.02)
        actual_client = screen_to_client(session.selected.hwnd, *cursor_screen_pos())
    return actual_client


def _save_hover_hotspot_evidence(
    image: Image.Image,
    *,
    hover: tuple[int, int],
    match_evidence: tuple[str, ...],
    path: Path,
    input_point: tuple[int, int] | None = None,
) -> None:
    """Annotate match box + vision mark (+ optional input aim) for review.

    Red = vision hover (template dial hotspot). Cyan = input aim after nudge.
    """
    from PIL import ImageDraw

    annotated = image.convert("RGB").copy()
    draw = ImageDraw.Draw(annotated)
    match_box = None
    for item in match_evidence:
        if item.startswith("match_box="):
            raw = item.split("=", 1)[1].strip()
            try:
                match_box = tuple(int(v) for v in raw.strip("[]").split(","))
            except ValueError:
                match_box = None
    if match_box and len(match_box) == 4:
        draw.rectangle(list(match_box), outline=(0, 255, 0), width=2)
        # Dial geometric center of match box (review reference).
        cx = (match_box[0] + match_box[2]) // 2
        cy = (match_box[1] + match_box[3]) // 2
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), outline=(255, 255, 0), width=1)
    hx, hy = hover
    draw.ellipse((hx - 5, hy - 5, hx + 5, hy + 5), outline=(255, 0, 0), width=2)
    draw.line((hx - 8, hy, hx + 8, hy), fill=(255, 0, 0), width=1)
    draw.line((hx, hy - 8, hx, hy + 8), fill=(255, 0, 0), width=1)
    if input_point is not None and input_point != hover:
        ix, iy = input_point
        draw.ellipse((ix - 5, iy - 5, ix + 5, iy + 5), outline=(0, 255, 255), width=2)
        draw.line((ix - 8, iy, ix + 8, iy), fill=(0, 255, 255), width=1)
        draw.line((ix, iy - 8, ix, iy + 8), fill=(0, 255, 255), width=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    annotated.save(path)


def _strategy_needs_foreground(strategy: str) -> bool:
    return strategy in {"setcursor", "setcursor_postmessage"}


def _with_temporary_game_foreground(session: VerificationSession, action: Callable[[], None]) -> None:
    """Raise game briefly for SetCursorPos hover, then restore prior foreground/cursor."""
    from .background_context import foreground_hwnd
    from .manual_coordinate import cursor_screen_pos, set_foreground

    import ctypes

    previous_fg = foreground_hwnd()
    previous_cursor = cursor_screen_pos()
    try:
        set_foreground(session.parent_hwnd)
        action()
    finally:
        try:
            ctypes.windll.user32.SetCursorPos(int(previous_cursor[0]), int(previous_cursor[1]))
        except Exception:
            pass
        if previous_fg and foreground_hwnd() != previous_fg:
            try:
                set_foreground(previous_fg)
            except Exception:
                pass


def run_incense_hover_diagnostic(
    session: VerificationSession,
    output_dir: str | Path,
    *,
    settle_seconds: tuple[float, ...] = HOVER_DIAGNOSTIC_SETTLE_SECONDS,
    strategies: tuple[str, ...] = HOVER_DIAGNOSTIC_STRATEGIES,
    hover_offsets: tuple[tuple[int, int], ...] = HOVER_DIAGNOSTIC_OFFSETS,
) -> dict[str, object]:
    """Verify locked hover path; keep every trial image dir for review.

    Discovery (message-only / setcursor / multi-dwell grid) is retired.
    Default matrix is setcursor_postmessage @ 0.90s with small dial offsets.
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    image = as_pil_image(session.capture_frame()).convert("RGB")
    image.save(output / "capture.png")

    panel = detect_right_strip_collapsed(image)
    if panel.collapsed is not False:
        return {
            "ok": False,
            "reason": "panel_not_expanded",
            "panel_collapsed": panel.collapsed,
            "panel_evidence": list(panel.evidence),
        }

    found, score, hover, reason, clock_box, threshold, clock_evidence = _match_clock(image)
    if not found or hover is None:
        return {
            "ok": False,
            "reason": reason,
            "clock_found": False,
            "clock_score": score,
            "clock_search_roi": list(clock_box),
            "clock_threshold": threshold,
            "clock_evidence": list(clock_evidence),
        }

    base_input = _vision_hover_to_input(hover, width=image.width, height=image.height)
    _save_hover_hotspot_evidence(
        image,
        hover=hover,
        match_evidence=clock_evidence,
        path=output / "hover-hotspot.png",
        input_point=base_input,
    )

    driver = BackgroundInput(session.selected.hwnd)
    outside = (max(0, base_input[0] - HOVER_EXIT_OFFSET), base_input[1])
    results: list[dict[str, object]] = []

    for strategy in strategies:
        strategy_dir = output / strategy
        strategy_dir.mkdir(parents=True, exist_ok=True)
        # Message-only: center only. Cursor strategies: all configured offsets.
        for dwell in settle_seconds:
            if strategy in {"postmessage", "sendmessage"}:
                offsets: tuple[tuple[int, int], ...] = ((0, 0),)
            else:
                offsets = hover_offsets
            for ox, oy in offsets:
                vision_target = (
                    max(0, min(image.width - 1, hover[0] + ox)),
                    max(0, min(image.height - 1, hover[1] + oy)),
                )
                input_target = (
                    max(0, min(image.width - 1, base_input[0] + ox)),
                    max(0, min(image.height - 1, base_input[1] + oy)),
                )
                label = f"dwell-{dwell:.2f}s"
                if (ox, oy) != (0, 0):
                    label = f"{label}_off-{ox:+d}_{oy:+d}"
                trial = strategy_dir / label
                trial.mkdir(parents=True, exist_ok=True)

                def _run_trial(
                    input_xy: tuple[int, int] = input_target,
                    tip_xy: tuple[int, int] = input_target,
                ) -> tuple[Image.Image, Image.Image, float, str, str | None, list[int] | None]:
                    _hover_transport(
                        driver,
                        strategy=strategy,
                        x=outside[0],
                        y=outside[1],
                        session=session,
                    )
                    time.sleep(0.15)
                    before_frame = as_pil_image(session.capture_frame()).convert("RGB")
                    before_frame.save(trial / "before.png")
                    _hover_transport(
                        driver,
                        strategy=strategy,
                        x=input_xy[0],
                        y=input_xy[1],
                        session=session,
                    )
                    cursor_after: list[int] | None = None
                    if _strategy_needs_foreground(strategy):
                        from .manual_coordinate import cursor_screen_pos, screen_to_client

                        try:
                            cursor_after = list(
                                screen_to_client(
                                    session.selected.hwnd, *cursor_screen_pos()
                                )
                            )
                        except Exception:
                            cursor_after = None
                    time.sleep(float(dwell))
                    after_frame = as_pil_image(session.capture_frame()).convert("RGB")
                    after_frame.save(trial / "after.png")
                    tip = tooltip_ocr_box(
                        tip_xy, width=after_frame.width, height=after_frame.height
                    )
                    before_tip = np.asarray(before_frame.crop(tip), dtype=np.int16)
                    after_tip = np.asarray(after_frame.crop(tip), dtype=np.int16)
                    tip_delta = float(np.abs(after_tip - before_tip).mean())
                    after_frame.crop(tip).save(trial / "tooltip-roi.png")
                    below = tooltip_ocr_box_below(
                        tip_xy, width=after_frame.width, height=after_frame.height
                    )
                    after_frame.crop(below).save(trial / "tooltip-roi-below.png")
                    try:
                        text = _ocr_tooltip(after_frame, tip_xy)
                        err = None
                    except RuntimeError as exc:
                        text = ""
                        err = str(exc)
                    return after_frame, before_frame, tip_delta, text, err, cursor_after

                if _strategy_needs_foreground(strategy):
                    held: list[
                        tuple[
                            Image.Image,
                            Image.Image,
                            float,
                            str,
                            str | None,
                            list[int] | None,
                        ]
                    ] = []

                    def _fg_trial() -> None:
                        held.append(_run_trial())

                    _with_temporary_game_foreground(session, _fg_trial)
                    _after, _before, delta, tooltip_text, ocr_error, cursor_client_after = held[0]
                else:
                    (
                        _after,
                        _before,
                        delta,
                        tooltip_text,
                        ocr_error,
                        cursor_client_after,
                    ) = _run_trial()

                tip_box = list(
                    tooltip_ocr_box(
                        input_target, width=_after.width, height=_after.height
                    )
                )
                tip_ocr_ok = tooltip_looks_like_incense(tooltip_text)
                results.append({
                    "strategy": strategy,
                    "dwell_seconds": float(dwell),
                    "hover_offset": [ox, oy],
                    "hover_point": list(vision_target),
                    "input_point": list(input_target),
                    "exit_point": list(outside),
                    "cursor_client_after_move": cursor_client_after,
                    "tooltip_roi": tip_box,
                    "tooltip_pixel_delta_mean": round(delta, 3),
                    "tooltip_text": tooltip_text,
                    "ocr_error": ocr_error,
                    "tooltip_changed": delta >= 1.0,
                    "tip_ocr_ok": tip_ocr_ok,
                    "pixel_delta_without_tip": bool(delta >= 1.0 and not tip_ocr_ok),
                    "artifacts_kept": True,
                })

    tip_hits = [item for item in results if item["tip_ocr_ok"]]
    pixel_only = [item for item in results if item["pixel_delta_without_tip"]]
    winners = sorted({str(item["strategy"]) for item in tip_hits})
    return {
        "ok": bool(tip_hits),
        "panel_collapsed": panel.collapsed,
        "clock_found": True,
        "clock_score": score,
        "clock_location": list(hover),
        "input_point": list(base_input),
        "capture_to_input_nudge": list(CLOCK_CAPTURE_TO_INPUT_NUDGE),
        "clock_search_roi": list(clock_box),
        "clock_threshold": threshold,
        "trials": results,
        "winning_strategies": winners,
        "pixel_delta_only_strategies": sorted(
            {str(item["strategy"]) for item in pixel_only}
        ),
        "evidence": [
            "diagnostic=hover-locked-verification",
            f"strategies={list(strategies)}",
            f"settle_seconds={list(settle_seconds)}",
            f"hover_offsets={[list(item) for item in hover_offsets]}",
            f"capture_to_input_nudge={list(CLOCK_CAPTURE_TO_INPUT_NUDGE)}",
            f"vision_hover={list(hover)}",
            f"input_point={list(base_input)}",
            f"tip_ocr_ok_trials={len(tip_hits)}",
            f"pixel_delta_without_tip_trials={len(pixel_only)}",
            f"winning_strategies={winners}",
            "artifacts=keep all locked-matrix trial dirs",
            "note=human X +2 right from (-21,8) → nudge=(-19,8); still (0,0)×4",
        ],
    }


def detect_incense_usage(
    session: VerificationSession,
    output_dir: str | Path,
    *,
    hover_settle_seconds: float = DEFAULT_HOVER_SETTLE_SECONDS,
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
    input_point = _vision_hover_to_input(hover, width=image.width, height=image.height)
    evidence.append(f"hover_point={hover}")
    evidence.append(f"input_point={input_point}")
    evidence.append(f"capture_to_input_nudge={list(CLOCK_CAPTURE_TO_INPUT_NUDGE)}")
    evidence.append(f"hover_target_roi={list(hover_box)}")
    _save_hover_hotspot_evidence(
        image,
        hover=hover,
        match_evidence=clock_evidence,
        path=output / "hover-hotspot.png",
        input_point=input_point,
    )
    log(
        f"[4/5] 已保存悬停证据：hover-target-roi / hover-on-search-roi / hover-hotspot；"
        f"vision={hover} input={input_point}"
    )

    # Message-only hover never spawned tip (20260929T122753); use real cursor.
    driver = BackgroundInput(session.selected.hwnd)
    evidence.append(f"hover_strategy={DEFAULT_HOVER_STRATEGY}")

    def _hover_then_capture() -> Image.Image:
        _hover_transport(
            driver,
            strategy=DEFAULT_HOVER_STRATEGY,
            x=input_point[0],
            y=input_point[1],
            session=session,
        )
        log(
            f"[4/5] PASS 已执行悬停({DEFAULT_HOVER_STRATEGY}) input={input_point}，"
            f"等待 tooltip 稳定 {hover_settle_seconds:.2f}s"
        )
        time.sleep(hover_settle_seconds)
        return as_pil_image(session.capture_frame()).convert("RGB")

    log("[5/5] START 捕获悬停后全屏画面，并裁剪 tip OCR 窄带")
    if _strategy_needs_foreground(DEFAULT_HOVER_STRATEGY):
        captured: list[Image.Image] = []

        def _setcursor_hover() -> None:
            captured.append(_hover_then_capture())

        _with_temporary_game_foreground(session, _setcursor_hover)
        hovered = captured[0]
    else:
        hovered = _hover_then_capture()
    hovered.save(output / "hovered-capture.png")
    _save_hover_on_search_roi(
        hovered,
        search_box=(0, 0, hovered.width, hovered.height),
        hover=input_point,
        path=output / "hovered-capture-marked.png",
    )
    evidence.append("hovered_capture=hovered-capture.png")
    evidence.append("hovered_capture_marked=hovered-capture-marked.png")
    tip_box = tooltip_ocr_box(input_point, width=hovered.width, height=hovered.height)
    hovered.crop(tip_box).save(output / "tooltip-roi.png")
    evidence.append(f"tooltip_ocr_roi={list(tip_box)}")
    log("[5/5] 已保存 hovered-capture.png / hovered-capture-marked.png；进入 tip OCR")

    try:
        tooltip_text = _ocr_tooltip(hovered, input_point)
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
    "CLOCK_CAPTURE_TO_INPUT_NUDGE",
    "CLOCK_HOVER_IN_TEMPLATE",
    "CLOCK_SEARCH_REGION",
    "CLOCK_TEMPLATE_PATH",
    "DEFAULT_HOVER_STRATEGY",
    "DEFAULT_HOVER_SETTLE_SECONDS",
    "HOVER_DIAGNOSTIC_STRATEGIES",
    "IncenseUsageObservation",
    "RIGHT_TOGGLE_REGION",
    "detect_incense_usage",
    "detect_right_strip_collapsed",
    "run_incense_hover_diagnostic",
    "hover_target_box",
    "parse_incense_tooltip",
    "tooltip_looks_like_incense",
    "tooltip_looks_like_task_tracker",
    "tooltip_ocr_box",
    "tooltip_ocr_box_below",
    "tooltip_ocr_box_left",
]
