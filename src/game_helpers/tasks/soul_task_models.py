"""命魂任务检测用的状态、配置与观测结果模型。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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

# Production default click candidate for the shortcut-panel toggle on 800×600.
# Visual matching is diagnostic only; the main flow clicks this fixed client point
# (or the calibrated value in fixed_coordinates.json when present).
DEFAULT_SHORTCUT_PANEL_CLICK = (14, 122)

# Expanded Shortcut floating-icon cluster under 指引/邮件/日历 (800×600).
# Anchored from live captures where row1 (梦/新) sits near y≈90–120 and row2
# (coin / 命魂 / 華) near y≈140–180. Keep padding so the first row is not clipped.
# Recalibrate if client layout drifts.
SHORTCUT_EXPANDED_ICON_LIST_REGION = UiRect(
    4 / 800,
    80 / 600,
    200 / 800,
    250 / 600,
)

DEFAULT_SOUL_TASK_UI = SoulTaskUiProfile(
    # Fallback pixel for probes that still read task_entry_toggle; main flow uses
    # DEFAULT_SHORTCUT_PANEL_CLICK / fixed_coordinates.json instead of vision centers.
    task_entry_toggle=UiPoint(14 / 800, 122 / 600),
    task_panel_icon=UiPoint(0.10, 0.10),
    claimed_icon_region=SHORTCUT_EXPANDED_ICON_LIST_REGION,
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
    # Visual match center only — never treat as the production click target.
    click_location: tuple[int, int] | None = None
    matched_template: str | None = None
    match_score: float = 0.0
    second_template: str | None = None
    second_score: float | None = None
