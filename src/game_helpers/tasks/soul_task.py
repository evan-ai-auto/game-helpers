"""命魂任务状态检测的最小视觉入口。

当前版本只负责：
1. 记录梦幻西游左上角任务入口 UI 的可配置点击区域；
2. 对任务面板截图做“已领取/未领取/未知”分类；
3. 不执行任何任务动作。

“已领取/未领取”的最终视觉判据必须由真实任务面板样本校准，不能凭窗口标题推断。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PIL import Image


class SoulTaskStatus(str, Enum):
    CLAIMED = "claimed"
    NOT_CLAIMED = "not_claimed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UiPoint:
    """Normalized point in the selected WSGAME client surface."""

    x: float
    y: float

    def pixel(self, width: int, height: int) -> tuple[int, int]:
        return round(self.x * width), round(self.y * height)


@dataclass(frozen=True)
class SoulTaskUiProfile:
    """UI calibration for the current 梦幻西游 client layout.

    The points are deliberately configuration, not hard-coded action logic, so
    later screenshots or client-size changes can be calibrated without changing
    the task detector itself.
    """

    task_entry_toggle: UiPoint
    task_panel_icon: UiPoint


# Calibrated from the user-provided 384x327 screenshot. The screenshot contains
# a small title/tab chrome above the 1024x768 WSGAME surface, so these are
# starting points only and must be validated against the live child surface.
DEFAULT_SOUL_TASK_UI = SoulTaskUiProfile(
    task_entry_toggle=UiPoint(0.047, 0.33),
    task_panel_icon=UiPoint(0.10, 0.10),
)


@dataclass(frozen=True)
class SoulTaskObservation:
    status: SoulTaskStatus
    panel_detected: bool
    evidence: tuple[str, ...]
    screenshot_path: str | None = None


def inspect_task_panel_image(path: str | Path) -> SoulTaskObservation:
    """Inspect a task-panel image without making a task decision from guesswork.

    Until positive and negative 命魂任务 panel samples are calibrated, the
    detector intentionally returns UNKNOWN. This prevents a visually plausible
    but incorrect screenshot from being treated as proof that a task was claimed.
    """
    image = Image.open(path)
    if image.width <= 0 or image.height <= 0:
        return SoulTaskObservation(
            status=SoulTaskStatus.UNKNOWN,
            panel_detected=False,
            evidence=("invalid screenshot dimensions",),
            screenshot_path=str(path),
        )
    return SoulTaskObservation(
        status=SoulTaskStatus.UNKNOWN,
        panel_detected=True,
        evidence=(
            "task-panel screenshot received",
            "positive/negative 命魂任务 samples are not calibrated yet",
        ),
        screenshot_path=str(path),
    )
