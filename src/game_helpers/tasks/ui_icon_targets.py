"""Registry of UI icon detection targets for parameterized vision checks."""
from __future__ import annotations

from dataclasses import dataclass

from .soul_task_models import DEFAULT_SOUL_TASK_UI, UiRect

DEFAULT_ICON_TARGET_ID = "soul_task_claimed"


@dataclass(frozen=True)
class IconDetectTarget:
    """One detect-what resource: template + search ROI + matcher contract."""

    id: str
    name: str
    template_path: str
    region: UiRect
    matcher: str
    match_threshold: float


ICON_DETECT_TARGETS: tuple[IconDetectTarget, ...] = (
    IconDetectTarget(
        id=DEFAULT_ICON_TARGET_ID,
        name="命魂任务已领取图标",
        template_path=DEFAULT_SOUL_TASK_UI.template_path,
        region=DEFAULT_SOUL_TASK_UI.claimed_icon_region,
        matcher="claimed_json",
        match_threshold=DEFAULT_SOUL_TASK_UI.match_threshold,
    ),
)

ICON_DETECT_TARGET_BY_ID = {item.id: item for item in ICON_DETECT_TARGETS}


def resolve_icon_target(target_id: str = DEFAULT_ICON_TARGET_ID) -> IconDetectTarget:
    try:
        return ICON_DETECT_TARGET_BY_ID[target_id]
    except KeyError as exc:
        known = ", ".join(sorted(ICON_DETECT_TARGET_BY_ID))
        raise KeyError(f"unknown icon target: {target_id}; known={known}") from exc


def list_icon_targets() -> tuple[IconDetectTarget, ...]:
    return ICON_DETECT_TARGETS


__all__ = [
    "DEFAULT_ICON_TARGET_ID",
    "ICON_DETECT_TARGETS",
    "IconDetectTarget",
    "list_icon_targets",
    "resolve_icon_target",
]
