"""Parameterized UI icon detection with optional Shortcut expand gate."""
from __future__ import annotations

import binascii
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ..capture.models import Frame
from .shortcut_panel_vision import detect_shortcut_panel_state
from .soul_task_match import (
    as_pil_image,
    load_claimed_icon_template,
    load_template,
    masked_match,
    ncc,
    resolve_template_path,
)
from .soul_task_models import SoulTaskPanelObservation
from .ui_icon_targets import (
    DEFAULT_ICON_TARGET_ID,
    IconDetectTarget,
    list_icon_targets,
    resolve_icon_target,
)


@dataclass(frozen=True)
class IconMatchObservation:
    found: bool
    score: float
    reason: str
    match_location: tuple[int, int] | None
    search_roi: tuple[int, int, int, int]
    evidence: tuple[str, ...]
    target_id: str
    target_name: str


@dataclass(frozen=True)
class UiIconGateObservation:
    panel: SoulTaskPanelObservation
    panel_state: str
    icon_checked: bool
    icon: IconMatchObservation | None
    target_id: str
    target_name: str


def _panel_state_label(collapsed: bool | None) -> str:
    if collapsed is True:
        return "折叠"
    if collapsed is False:
        return "展开"
    return "未知"


def detect_icon_in_image(
    image: Image.Image | Frame,
    target: IconDetectTarget | str = DEFAULT_ICON_TARGET_ID,
) -> IconMatchObservation:
    """Match one registered target inside its search ROI (no Shortcut gate)."""
    resolved = resolve_icon_target(target) if isinstance(target, str) else target
    try:
        image = as_pil_image(image)
    except (TypeError, ValueError):
        empty = (0, 0, 0, 0)
        return IconMatchObservation(
            False, 0.0, "invalid_image", None, empty, ("invalid image",), resolved.id, resolved.name
        )
    if image.width <= 0 or image.height <= 0:
        empty = (0, 0, 0, 0)
        return IconMatchObservation(
            False, 0.0, "invalid_image", None, empty, ("empty image",), resolved.id, resolved.name
        )

    left, top, right, bottom = resolved.region.pixel(image.width, image.height)
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    roi_box = (left, top, right, bottom)
    if right <= left or bottom <= top:
        return IconMatchObservation(
            False,
            0.0,
            "invalid_detection_region",
            None,
            roi_box,
            ("invalid detection region",),
            resolved.id,
            resolved.name,
        )

    template_path = resolve_template_path(resolved.template_path)
    roi = np.asarray(image, dtype=np.float32)[top:bottom, left:right]

    try:
        if resolved.matcher == "claimed_json":
            template = load_claimed_icon_template(template_path)
            score, location = ncc(roi, template)
        elif resolved.matcher == "masked_png":
            template_rgb, alpha = load_template(template_path)
            score, location = masked_match(roi, template_rgb, alpha)
        else:
            return IconMatchObservation(
                False,
                0.0,
                "unsupported_matcher",
                None,
                roi_box,
                (f"unsupported matcher: {resolved.matcher}",),
                resolved.id,
                resolved.name,
            )
    except FileNotFoundError:
        return IconMatchObservation(
            False,
            0.0,
            "template_missing",
            None,
            roi_box,
            (f"template not found: {template_path}",),
            resolved.id,
            resolved.name,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError, binascii.Error):
        return IconMatchObservation(
            False,
            0.0,
            "template_invalid",
            None,
            roi_box,
            (f"template invalid: {template_path}",),
            resolved.id,
            resolved.name,
        )

    found = score >= resolved.match_threshold
    best_location = (left + location[0], top + location[1]) if location else None
    reason = "icon_found" if found else "icon_not_found"
    evidence = (
        f"target={resolved.id}",
        f"template={template_path}",
        f"score={score:.3f}",
        f"threshold={resolved.match_threshold:.3f}",
        f"roi={list(roi_box)}",
    )
    return IconMatchObservation(
        found=found,
        score=max(0.0, float(score)),
        reason=reason,
        match_location=best_location,
        search_roi=roi_box,
        evidence=evidence,
        target_id=resolved.id,
        target_name=resolved.name,
    )


def detect_ui_icon_with_shortcut_gate(
    image: Image.Image | Frame,
    *,
    target_id: str = DEFAULT_ICON_TARGET_ID,
) -> UiIconGateObservation:
    """Run Shortcut state first; only expanded panels proceed to icon match."""
    target = resolve_icon_target(target_id)
    panel = detect_shortcut_panel_state(image)
    state = _panel_state_label(panel.collapsed)
    if panel.collapsed is not False:
        return UiIconGateObservation(
            panel=panel,
            panel_state=state,
            icon_checked=False,
            icon=None,
            target_id=target.id,
            target_name=target.name,
        )
    icon = detect_icon_in_image(image, target)
    return UiIconGateObservation(
        panel=panel,
        panel_state=state,
        icon_checked=True,
        icon=icon,
        target_id=target.id,
        target_name=target.name,
    )


def list_icon_source_candidates(*, limit: int = 20) -> list[Path]:
    """Recent PNG candidates under diagnostic runs and UI assets."""
    roots = (Path("diagnostic/workflow_runs"), Path("data/assets/ui"))
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        found.extend(path for path in root.rglob("*.png") if path.is_file())
    found.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return found[: max(0, limit)]


def choose_icon_target_interactive() -> str:
    targets = list_icon_targets()
    print("[图标检测] 请选择要检测的目标资源（参数1）")
    for index, target in enumerate(targets, start=1):
        default = "（默认）" if target.id == DEFAULT_ICON_TARGET_ID else ""
        print(f"  [{index}] {target.name} | id={target.id}{default}")
    raw = input("请选择目标编号（回车=默认命魂任务已领取图标）：").strip()
    if not raw:
        return DEFAULT_ICON_TARGET_ID
    try:
        choice = int(raw)
    except ValueError as exc:
        raise RuntimeError("目标编号无效") from exc
    if not 1 <= choice <= len(targets):
        raise RuntimeError(f"目标编号必须在 1 到 {len(targets)} 之间")
    return targets[choice - 1].id


def choose_icon_source_interactive() -> tuple[str, Path | None]:
    """Return (mode, path). mode is file|live_capture; path is set for file mode."""
    candidates = list_icon_source_candidates()
    print("[图标检测] 请选择检测图源（参数2，必选）")
    print("  [L] 使用当前实时截图")
    for index, path in enumerate(candidates, start=1):
        print(f"  [{index}] {path.as_posix()}")
    print("  或直接输入图片路径")
    raw = input("请选择图源编号 / L / 路径：").strip()
    if not raw:
        raise RuntimeError("必须选择检测图源")
    if raw.lower() in {"l", "live", "实时", "当前"}:
        return "live_capture", None
    try:
        choice = int(raw)
    except ValueError:
        path = Path(raw)
        if not path.is_file():
            raise RuntimeError(f"图源文件不存在: {path}") from None
        return "file", path
    if not 1 <= choice <= len(candidates):
        raise RuntimeError(f"图源编号必须在 1 到 {len(candidates)} 之间（或输入 L/路径）")
    return "file", candidates[choice - 1]


__all__ = [
    "IconMatchObservation",
    "UiIconGateObservation",
    "choose_icon_source_interactive",
    "choose_icon_target_interactive",
    "detect_icon_in_image",
    "detect_ui_icon_with_shortcut_gate",
    "list_icon_source_candidates",
]
