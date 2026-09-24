"""命魂任务领取状态检测。

实现已拆分到 soul_task_models / soul_task_match / soul_task_detect；
本模块保持原有公共导入路径不变。
"""
from __future__ import annotations

from .soul_task_detect import (
    claim_verification_result,
    detect_soul_task_claimed_icon,
    detect_soul_task_panel_collapsed,
    inspect_task_panel_image,
)
from .soul_task_models import (
    DEFAULT_SHORTCUT_PANEL_CLICK,
    DEFAULT_SOUL_TASK_UI,
    SHORTCUT_EXPANDED_ICON_LIST_REGION,
    SOUL_TASK_BASELINE_SIZE,
    SoulTaskDetectionReason,
    SoulTaskObservation,
    SoulTaskPanelObservation,
    SoulTaskStatus,
    SoulTaskUiProfile,
    UiPoint,
    UiRect,
)

__all__ = [
    "DEFAULT_SHORTCUT_PANEL_CLICK",
    "DEFAULT_SOUL_TASK_UI",
    "SHORTCUT_EXPANDED_ICON_LIST_REGION",
    "SOUL_TASK_BASELINE_SIZE",
    "SoulTaskDetectionReason",
    "SoulTaskObservation",
    "SoulTaskPanelObservation",
    "SoulTaskStatus",
    "SoulTaskUiProfile",
    "UiPoint",
    "UiRect",
    "claim_verification_result",
    "detect_soul_task_claimed_icon",
    "detect_soul_task_panel_collapsed",
    "inspect_task_panel_image",
]
