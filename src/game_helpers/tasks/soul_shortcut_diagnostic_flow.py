"""Layered diagnostics for the 梦幻西游 shortcut-panel toggle.

This module is diagnostic-only. It deliberately does not change production
shortcut coordinates, templates, thresholds, or BackgroundInput.click().
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture
from ..core.view_manager import GameViewManager
from .background_context import BackgroundRunGuard
from .character_selection import CharacterSelectionResult, sync_selected_character
from .manual_coordinate import (
    collect_client_coordinate,
    set_foreground,
)
from .shortcut_panel_vision import detect_shortcut_panel_state
from .soul_task import SOUL_TASK_BASELINE_SIZE
from .soul_task_match import as_pil_image
from .verification_session import VerificationSession

SHORTCUT_DIAGNOSTIC_SUBTYPES = (
    ("full", "完整验证流程"),
    ("motion", "角色运动状态验证"),
    ("hover", "Hover 二级 ROI 隔离验证"),
    ("postmessage_hover", "PostMessageW Hover 验证"),
    ("click_hotspot", "后台 Click + Hotspot 验证"),
)


@dataclass(frozen=True)
class ImageDiff:
    changed_pixels: int
    ratio: float
    bbox: tuple[int, int, int, int] | None
    centroid: tuple[float, float] | None


def image_diff(before: Image.Image, after: Image.Image, *, threshold: int = 8) -> ImageDiff:
    if before.size != after.size:
        raise ValueError("diff images must have the same size")
    diff = ImageChops.difference(before.convert("RGB"), after.convert("RGB"))
    mask = diff.convert("L").point(lambda value: 255 if value >= threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return ImageDiff(0, 0.0, None, None)
    pixels = list(mask.getdata())
    changed = sum(1 for value in pixels if value)
    width, height = mask.size
    points = [(index % width, index // width) for index, value in enumerate(pixels) if value]
    centroid = (
        sum(point[0] for point in points) / changed,
        sum(point[1] for point in points) / changed,
    )
    return ImageDiff(changed, changed / float(width * height), bbox, centroid)


def classify_motion(
    first: tuple[str, int, int] | None,
    second: tuple[str, int, int] | None,
) -> str:
    if first is None or second is None:
        return "未知"
    return "静止候选" if first == second else "移动"


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _status_text(collapsed: bool | None) -> str:
    if collapsed is True:
        return "折叠"
    if collapsed is False:
        return "展开"
    return "未知"


def _select_point(
    selection: CharacterSelectionResult,
    parent_hwnd: int,
) -> tuple[tuple[int, int], tuple[int, int]]:
    sample = collect_client_coordinate(
        selection.hwnd,
        prompt="请把鼠标移到目标快捷图标上，按 F9 采集；按 ESC 取消。",
        foreground_hwnd_for_hover=parent_hwnd,
    )
    return sample.client, sample.screen


def _capture(session: VerificationSession) -> Image.Image:
    return as_pil_image(session.capture_frame()).convert("RGB")


def _fixed_level2_roi(
    anchor: tuple[int, int],
    *,
    size: int = 24,
) -> tuple[int, int, int, int]:
    left = max(0, int(anchor[0]) - size // 2)
    top = max(0, int(anchor[1]) - size // 2)
    return left, top, left + size, top + size


def _crop_roi(
    image: Image.Image,
    rect: tuple[int, int, int, int],
) -> Image.Image:
    return image.crop(rect)


def _motion_experiment(
    session: VerificationSession,
    output: Path,
    *,
    wait_seconds: float = 0.8,
) -> dict[str, object]:
    first_path = output / "motion-sample-1.png"
    second_path = output / "motion-sample-2.png"
    first = _capture(session)
    _save(first, first_path)
    time.sleep(wait_seconds)
    second = _capture(session)
    _save(second, second_path)
    result = {
        "sample_1_screenshot": str(first_path),
        "sample_2_screenshot": str(second_path),
        "sample_1": None,
        "sample_2": None,
        "state": "未知",
        "ocr_backend": "未配置",
        "reason": "仓库当前仅有角色坐标 OCR 解析契约，未提供可直接调用的 OCR 后端。",
    }
    print("[命魂诊断] 运动检测：OCR 后端未配置；状态=未知")
    print("[命魂诊断] 运动检测：本次不作为 Hover/Click 的通过条件")
    return result


def _level1(session: VerificationSession, output: Path) -> dict[str, object]:
    image = _capture(session)
    full = output / "level1-full.png"
    roi_path = output / "level1-roi.png"
    _save(image, full)
    panel = detect_shortcut_panel_state(image)
    roi = _crop_roi(image, (0, 80, 40, 128))
    _save(roi, roi_path)
    print("[命魂诊断] 一级 ROI：client=(0, 80)-(40, 128)")
    print(f"[命魂诊断] 目标匹配：template={panel.matched_template or '无'}；score={panel.match_score:.3f}")
    if panel.match_location:
        print(f"[命魂诊断] 匹配位置：client=({panel.match_location[0]}, {panel.match_location[1]})")
    return {
        "full_screenshot": str(full),
        "roi_screenshot": str(roi_path),
        "roi": [0, 80, 40, 128],
        "template": panel.matched_template,
        "score": panel.match_score,
        "match_location": list(panel.match_location) if panel.match_location else None,
        "visual_center": list(panel.click_location) if panel.click_location else None,
        "collapsed": panel.collapsed,
    }


def _hover_experiment(
    session: VerificationSession,
    selection: CharacterSelectionResult,
    parent_hwnd: int,
    output: Path,
) -> dict[str, object]:
    client, screen = _select_point(selection, parent_hwnd)
    roi_rect = _fixed_level2_roi(client)

    before = _capture(session)
    _save(before.crop(roi_rect), output / "level2-before-hover.png")

    set_foreground(parent_hwnd)
    import ctypes

    ctypes.windll.user32.SetCursorPos(*screen)
    time.sleep(0.5)
    hover_frame = _capture(session)
    _save(hover_frame.crop(roi_rect), output / "level2-real-hover.png")

    away = (max(0, screen[0] - 160), max(0, screen[1] - 160))
    ctypes.windll.user32.SetCursorPos(*away)
    time.sleep(0.4)
    leave_frame = _capture(session)
    _save(leave_frame.crop(roi_rect), output / "level2-real-leave.png")

    before_roi = before.crop(roi_rect)
    hover = hover_frame.crop(roi_rect)
    leave = leave_frame.crop(roi_rect)
    ab = image_diff(before_roi, hover)
    bc = image_diff(hover, leave)
    ac = image_diff(before_roi, leave)
    print(f"[命魂诊断] 二级 ROI：client=({roi_rect[0]}, {roi_rect[1]})-({roi_rect[2]}, {roi_rect[3]})")
    print(f"[命魂诊断] 真实鼠标 Hover：变化比例={ab.ratio:.3f}")
    print(f"[命魂诊断] 真实鼠标离开：变化比例={bc.ratio:.3f}")
    print(f"[命魂诊断] Hover 前后稳定性：变化比例={ac.ratio:.3f}")
    return {
        "target_client": list(client),
        "target_screen": list(screen),
        "roi": list(roi_rect),
        "real_mouse": {
            "before_vs_hover": ab.__dict__,
            "hover_vs_leave": bc.__dict__,
            "before_vs_leave": ac.__dict__,
        },
    }


def _postmessage_hover_experiment(
    session: VerificationSession,
    selection: CharacterSelectionResult,
    parent_hwnd: int,
    output: Path,
) -> dict[str, object]:
    client, screen = _select_point(selection, parent_hwnd)
    roi_rect = _fixed_level2_roi(client)
    import ctypes

    ctypes.windll.user32.SetCursorPos(
        max(0, screen[0] - 160),
        max(0, screen[1] - 160),
    )
    time.sleep(0.3)
    before = _capture(session)
    _save(before.crop(roi_rect), output / "level2-postmessage-before.png")

    BackgroundInput(selection.hwnd).mouse_move(*client)
    print("[命魂诊断] 输入方式：PostMessageW")
    print(f"[命魂诊断] WM_MOUSEMOVE：client=({client[0]}, {client[1]})；发送成功")
    time.sleep(0.5)
    hover = _capture(session)
    _save(hover.crop(roi_rect), output / "level2-postmessage-hover.png")
    diff = image_diff(before.crop(roi_rect), hover.crop(roi_rect))
    print(f"[命魂诊断] PostMessageW Hover 响应：变化比例={diff.ratio:.3f}")
    return {
        "target_client": list(client),
        "target_screen": list(screen),
        "roi": list(roi_rect),
        "mousemove_dispatch": True,
        "hover_diff": diff.__dict__,
    }


def _click_hotspot_experiment(
    session: VerificationSession,
    selection: CharacterSelectionResult,
    parent_hwnd: int,
    output: Path,
) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    print("[命魂诊断] Click/Hotspot：请逐点按 F9 采集有效点击位置；按 ESC 结束。")
    while True:
        try:
            client, screen = _select_point(selection, parent_hwnd)
        except RuntimeError as exc:
            if "ESC" in str(exc):
                break
            raise
        before = _capture(session)
        panel_before = detect_shortcut_panel_state(before)
        dispatch = BackgroundInput(selection.hwnd).click(*client)
        after = _capture(session)
        panel_after = detect_shortcut_panel_state(after)
        changed = (
            panel_before.collapsed is not None
            and panel_after.collapsed is not None
            and panel_before.collapsed != panel_after.collapsed
        )
        samples.append({
            "client": list(client),
            "screen": list(screen),
            "dispatch": list(dispatch),
            "before_collapsed": panel_before.collapsed,
            "after_collapsed": panel_after.collapsed,
            "state_changed": changed,
        })
        print(f"[命魂诊断] 后台 Click：client=({client[0]}, {client[1]})；消息发送成功")
        print(f"[命魂诊断] Click 后状态：{_status_text(panel_after.collapsed)}")
        answer = input("人工确认该点有效？y=计入，n=不计入，q=结束：").strip().lower()
        samples[-1]["manual_confirmed"] = answer in {"y", "yes", "是", "有效"}
        if answer in {"q", "quit", "exit", "esc"}:
            break
    report = {
        "samples": samples,
        "production_coordinate_changed": False,
        "production_coordinate": [14, 122],
    }
    (output / "click-hotspot-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def run_soul_shortcut_diagnostic(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    *,
    subtype: str,
    output_dir: str | Path = "diagnostic/workflow_runs/soul_shortcut_diagnostic",
) -> dict[str, object]:
    """Run one diagnostic subtype; subtype='full' runs all stages."""
    valid = {item[0] for item in SHORTCUT_DIAGNOSTIC_SUBTYPES}
    if subtype not in valid:
        raise ValueError(f"未知命魂诊断子实验：{subtype}")
    output = Path(output_dir) / subtype
    output.mkdir(parents=True, exist_ok=True)
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    session = VerificationSession(
        parent_hwnd=parent_hwnd,
        selected=selection,
        manager=manager,
        capture=WindowsGraphicsCapture(),
    )
    report: dict[str, object] = {
        "subtype": subtype,
        "character": selection.character_name,
        "client_size": list(SOUL_TASK_BASELINE_SIZE),
        "production_coordinate_changed": False,
    }
    try:
        sync_selected_character(parent_hwnd, selection)
        geometry = session.geometry()
        if (geometry.client_width, geometry.client_height) != SOUL_TASK_BASELINE_SIZE:
            raise RuntimeError("当前客户区不是 800x600，诊断任务停止。")
        if subtype in {"motion", "full"}:
            report["motion"] = _motion_experiment(session, output)
            if subtype == "motion":
                return _finish(report, output)
        if subtype == "hover":
            report["level1"] = _level1(session, output)
            report["hover"] = _hover_experiment(session, selection, parent_hwnd, output)
        elif subtype == "postmessage_hover":
            report["level1"] = _level1(session, output)
            report["postmessage_hover"] = _postmessage_hover_experiment(
                session, selection, parent_hwnd, output
            )
        elif subtype == "click_hotspot":
            report["level1"] = _level1(session, output)
            report["click_hotspot"] = _click_hotspot_experiment(
                session, selection, parent_hwnd, output
            )
        elif subtype == "full":
            report["level1"] = _level1(session, output)
            report["hover"] = _hover_experiment(
                session, selection, parent_hwnd, output
            )
            report["postmessage_hover"] = _postmessage_hover_experiment(
                session, selection, parent_hwnd, output
            )
            report["click_hotspot"] = _click_hotspot_experiment(
                session, selection, parent_hwnd, output
            )
        return _finish(report, output)
    finally:
        restore = guard.finish()
        print(f"[命魂诊断] Surface 恢复：{'成功' if restore['restored_surface'] else '失败'}")
        print(f"[命魂诊断] 标签恢复：{'成功' if restore['restored_tab'] else '失败'}")
        print(f"[命魂诊断] 前台窗口：{'未变化' if restore['foreground_unchanged'] else '已变化'}")


def _finish(report: dict[str, object], output: Path) -> dict[str, object]:
    report_path = output / "validation-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[命魂诊断] 报告：{report_path}")
    print("[命魂诊断] 生产默认坐标：未修改")
    return report


def list_subtypes() -> tuple[tuple[str, str], ...]:
    return SHORTCUT_DIAGNOSTIC_SUBTYPES


__all__ = [
    "SHORTCUT_DIAGNOSTIC_SUBTYPES",
    "classify_motion",
    "image_diff",
    "list_subtypes",
    "run_soul_shortcut_diagnostic",
]
