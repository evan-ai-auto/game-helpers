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
from ..vision.scene_coordinate import prepare_player_location, read_player_location
from ..vision.windows_ocr import WindowsNativeOCRBackend
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
    ("full", "[阻塞] Shortcut 功能能够完整闭环"),
    ("motion", "[部分完成] 能够可靠识别角色是否移动"),
    ("ocr_roi_compare", "[部分完成] 能够可靠识别场景与地图坐标"),
    ("hover", "[部分完成] 鼠标悬停能够触发并识别 Shortcut 二级状态"),
    ("postmessage_hover", "[部分完成] 后台消息能够触发并识别 Shortcut 悬停状态"),
    ("click_hotspot", "[部分完成] 后台点击能够触发并确认 Shortcut 状态变化"),
    ("background_capture_freshness", "[验收失败] 窗口被覆盖时仍能获得持续刷新的游戏画面"),
)

# 800×600 playfield used for motion: skip left HUD and the right chrome strip.
MOTION_PLAYFIELD_BOX = (80, 100, 720, 520)
MOTION_RIGHT_EDGE_BOX = (768, 0, 800, 600)
MOTION_WAIT_SECONDS = 3.0
MOTION_SAMPLE_INTERVAL = 0.25
MOTION_PLAYFIELD_RATIO = 0.002
MOTION_RIGHT_EDGE_RATIO = 0.02


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
    *,
    playfield_ratio: float | None = None,
    right_edge_ratio: float | None = None,
    playfield_threshold: float = MOTION_PLAYFIELD_RATIO,
    right_edge_threshold: float = MOTION_RIGHT_EDGE_RATIO,
) -> str:
    """Combine HUD coordinates with playfield / right-edge pixel change.

    - Either OCR side missing → 未知
    - Map cell changed → 移动
    - Same cell, playfield changed enough → 同格运动候选
    - Same cell, playfield frozen but right chrome moves → 画面未刷新
    - Same cell, both quiet → 静止候选
    """
    if first is None or second is None:
        if (
            playfield_ratio is not None
            and playfield_ratio < playfield_threshold
            and right_edge_ratio is not None
            and right_edge_ratio >= right_edge_threshold
        ):
            return "画面未刷新"
        return "未知"
    if first != second:
        return "移动"
    if playfield_ratio is not None and playfield_ratio >= playfield_threshold:
        return "同格运动候选"
    if (
        playfield_ratio is not None
        and playfield_ratio < playfield_threshold
        and right_edge_ratio is not None
        and right_edge_ratio >= right_edge_threshold
    ):
        return "画面未刷新"
    return "静止候选"


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


def _refresh_capture_surface(session: VerificationSession) -> dict[str, object]:
    """Nudge the selected WSGAME to present a fresh frame without stealing focus.

    Multi-view hosts: switch Surface away and back (known background repaint).
    Always follow with RedrawWindow on the child and parent.
    """
    import ctypes

    from .background_context import foreground_hwnd
    from .background_item_panel_open_probe_visual import refresh_surface_for_capture

    foreground = foreground_hwnd()
    switched = False
    try:
        switched = refresh_surface_for_capture(
            session.manager,
            session.selected.view_index,
            foreground,
        )
    except RuntimeError as exc:
        return {"ok": False, "switched": False, "reason": str(exc)}

    user32 = ctypes.windll.user32
    flags = 0x0001 | 0x0004 | 0x0100 | 0x0080  # invalidate/erase/updatenow/allchildren
    user32.RedrawWindow(session.selected.hwnd, None, None, flags)
    user32.RedrawWindow(session.parent_hwnd, None, None, flags)
    time.sleep(0.15)
    return {"ok": True, "switched": switched, "reason": None}


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


def _reading_payload(reading) -> dict[str, object]:
    return {
        "scene_text": reading.scene_text,
        "coordinate_text": reading.coordinate_text,
        "scene_box": list(reading.scene_box),
        "coordinate_box": list(reading.coordinate_box),
        "scene_ok": reading.scene_ok,
        "coordinate_ok": reading.coordinate_ok,
        "formatted": reading.formatted,
        "parsed_coordinate": list(reading.parsed) if reading.parsed else None,
    }


def _print_location_reading(label: str, reading) -> None:
    print(f"[命魂诊断] {label}场景原文：{reading.scene_text or '空'}")
    print(f"[命魂诊断] {label}坐标原文：{reading.coordinate_text or '空'}")
    if reading.formatted:
        print(f"[命魂诊断] {label}组装结果：{reading.formatted}")
        return
    if not reading.scene_ok:
        print(f"[命魂诊断] {label}失败阶段：场景名")
    if not reading.coordinate_ok:
        print(f"[命魂诊断] {label}失败阶段：坐标")


def _motion_experiment(
    session: VerificationSession,
    output: Path,
    *,
    wait_seconds: float = MOTION_WAIT_SECONDS,
    sample_interval: float = MOTION_SAMPLE_INTERVAL,
) -> dict[str, object]:
    playfield_box = MOTION_PLAYFIELD_BOX
    right_box = MOTION_RIGHT_EDGE_BOX
    print(
        "[命魂诊断] 运动检测："
        f"总时长={wait_seconds:.1f}s；采样间隔={sample_interval:.2f}s；"
        f"主画面 client=({playfield_box[0]}, {playfield_box[1]})-({playfield_box[2]}, {playfield_box[3]})；"
        f"右侧条 client=({right_box[0]}, {right_box[1]})-({right_box[2]}, {right_box[3]})"
    )
    print("[命魂诊断] 运动检测：请在采样期间保持目标状态（站立或持续移动）")

    refreshes: list[dict[str, object]] = []
    warm = _refresh_capture_surface(session)
    refreshes.append({"when": "before_sampling", **warm})
    print(
        "[命魂诊断] 运动检测：开采前刷新 Surface："
        f"{'成功' if warm['ok'] else '失败'}"
        f"；切换他窗={'是' if warm.get('switched') else '否'}"
        + (f"；原因={warm['reason']}" if warm.get("reason") else "")
    )

    samples: list[dict[str, object]] = []
    images: list[Image.Image] = []
    frame_count = max(2, int(wait_seconds / sample_interval) + 1)
    mid_refresh_at = max(2, frame_count // 2)
    mid_refreshed = False
    started = time.monotonic()
    for index in range(frame_count):
        if index > 0:
            target = started + index * sample_interval
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        if (
            index == mid_refresh_at
            and not mid_refreshed
            and samples
            and max(float(sample["playfield_ratio"]) for sample in samples) < MOTION_PLAYFIELD_RATIO
        ):
            mid = _refresh_capture_surface(session)
            refreshes.append({"when": f"before_frame_{index + 1}", **mid})
            mid_refreshed = True
            print(
                "[命魂诊断] 运动检测：中途刷新 Surface（主画面仍未变）："
                f"{'成功' if mid['ok'] else '失败'}"
                f"；切换他窗={'是' if mid.get('switched') else '否'}"
                + (f"；原因={mid['reason']}" if mid.get("reason") else "")
            )
        image = _capture(session)
        elapsed = time.monotonic() - started
        path = output / f"motion-sample-{index + 1:02d}.png"
        _save(image, path)
        if index == 0:
            play_ratio = 0.0
            right_ratio = 0.0
            play_pixels = 0
            right_pixels = 0
        else:
            play = image_diff(_crop_roi(images[0], playfield_box), _crop_roi(image, playfield_box))
            right = image_diff(_crop_roi(images[0], right_box), _crop_roi(image, right_box))
            play_ratio = play.ratio
            right_ratio = right.ratio
            play_pixels = play.changed_pixels
            right_pixels = right.changed_pixels
        sample = {
            "index": index + 1,
            "elapsed_seconds": round(elapsed, 3),
            "screenshot": str(path),
            "playfield_changed_pixels": play_pixels,
            "playfield_ratio": play_ratio,
            "right_edge_changed_pixels": right_pixels,
            "right_edge_ratio": right_ratio,
        }
        samples.append(sample)
        images.append(image)
        print(
            f"[命魂诊断] 运动检测：第 {index + 1}/{frame_count} 帧 "
            f"t={elapsed:.2f}s 主画面={play_ratio:.3f} 右侧={right_ratio:.3f}"
        )

    first_play = next(
        (
            sample
            for sample in samples[1:]
            if float(sample["playfield_ratio"]) >= MOTION_PLAYFIELD_RATIO
        ),
        None,
    )
    first_right = next(
        (
            sample
            for sample in samples[1:]
            if float(sample["right_edge_ratio"]) >= MOTION_RIGHT_EDGE_RATIO
        ),
        None,
    )
    max_play = max(float(sample["playfield_ratio"]) for sample in samples)
    max_right = max(float(sample["right_edge_ratio"]) for sample in samples)
    if first_play is not None:
        print(
            "[命魂诊断] 运动检测：主画面首次变化："
            f"第 {first_play['index']} 帧 / {first_play['elapsed_seconds']}s 后；"
            f"比例={float(first_play['playfield_ratio']):.3f}"
        )
    else:
        print("[命魂诊断] 运动检测：主画面全程未达变化阈值")
    if first_right is not None:
        print(
            "[命魂诊断] 运动检测：右侧条首次变化："
            f"第 {first_right['index']} 帧 / {first_right['elapsed_seconds']}s 后；"
            f"比例={float(first_right['right_edge_ratio']):.3f}"
        )

    # Keep legacy filenames pointing at first / last for older reports.
    _save(images[0], output / "motion-sample-1.png")
    _save(images[-1], output / "motion-sample-2.png")

    try:
        backend = WindowsNativeOCRBackend(language="zh-Hans-CN")
    except RuntimeError as exc:
        state = classify_motion(
            None,
            None,
            playfield_ratio=max_play,
            right_edge_ratio=max_right,
        )
        result = {
            "sample_1_screenshot": str(output / "motion-sample-1.png"),
            "sample_2_screenshot": str(output / "motion-sample-2.png"),
            "sample_1": None,
            "sample_2": None,
            "wait_seconds": wait_seconds,
            "sample_interval": sample_interval,
            "frame_count": len(samples),
            "playfield_box": list(playfield_box),
            "right_edge_box": list(right_box),
            "playfield_ratio": max_play,
            "right_edge_ratio": max_right,
            "first_playfield_change": first_play,
            "first_right_edge_change": first_right,
            "surface_refreshes": refreshes,
            "samples": samples,
            "state": state,
            "ocr_backend": "不可用",
            "reason": str(exc),
        }
        print(f"[命魂诊断] 运动检测：OCR 后端不可用；原因={exc}；状态={state}")
        return result

    sample_1 = read_player_location(images[0], backend)
    sample_2 = read_player_location(images[-1], backend)
    state = classify_motion(
        sample_1.parsed,
        sample_2.parsed,
        playfield_ratio=max_play,
        right_edge_ratio=max_right,
    )
    result = {
        "sample_1_screenshot": str(output / "motion-sample-1.png"),
        "sample_2_screenshot": str(output / "motion-sample-2.png"),
        "ocr_backend": "Windows.Media.Ocr",
        "ocr_language": backend.language,
        "sample_1": _reading_payload(sample_1),
        "sample_2": _reading_payload(sample_2),
        "wait_seconds": wait_seconds,
        "sample_interval": sample_interval,
        "frame_count": len(samples),
        "playfield_box": list(playfield_box),
        "right_edge_box": list(right_box),
        "playfield_changed_pixels": int(
            max(int(sample["playfield_changed_pixels"]) for sample in samples)
        ),
        "playfield_ratio": max_play,
        "right_edge_changed_pixels": int(
            max(int(sample["right_edge_changed_pixels"]) for sample in samples)
        ),
        "right_edge_ratio": max_right,
        "first_playfield_change": first_play,
        "first_right_edge_change": first_right,
        "surface_refreshes": refreshes,
        "samples": samples,
        "state": state,
    }
    _print_location_reading("运动检测 P1 ", sample_1)
    _print_location_reading("运动检测 P2 ", sample_2)
    print(
        f"[命魂诊断] 运动检测：帧数={len(samples)}；"
        f"主画面最大比例={max_play:.3f}；右侧最大比例={max_right:.3f}"
    )
    print(f"[命魂诊断] 运动检测：状态={state}")
    return result


def _ocr_roi_compare_experiment(
    session: VerificationSession,
    output: Path,
) -> dict[str, object]:
    """Read scene name and X/Y from one full screenshot, then assemble 地图名[x,y]."""
    image = _capture(session)
    source_path = output / "ocr-roi-source.png"
    _save(image, source_path)
    try:
        backend = WindowsNativeOCRBackend(language="zh-Hans-CN")
    except RuntimeError as exc:
        print(f"[命魂诊断] OCR 分段识别：后端不可用；原因={exc}")
        return {
            "screenshot": str(source_path),
            "backend": "不可用",
            "production_coordinate_changed": False,
            "production_config_changed": False,
            "reason": str(exc),
        }

    scene, coordinate = prepare_player_location(image)
    _save(scene.raw, output / "ocr-scene-raw.png")
    _save(scene.prepared.convert("RGB"), output / "ocr-scene-prepared.png")
    _save(coordinate.raw, output / "ocr-coordinate-raw.png")
    _save(coordinate.prepared.convert("RGB"), output / "ocr-coordinate-prepared.png")
    print(
        "[命魂诊断] 预处理：整图转 RGB；"
        f"场景名 client=({scene.box[0]}, {scene.box[1]})-({scene.box[2]}, {scene.box[3]})；"
        f"坐标 client=({coordinate.box[0]}, {coordinate.box[1]})-({coordinate.box[2]}, {coordinate.box[3]})"
    )
    print("[命魂诊断] 预处理：提取浅色字形、去掉黑边和底纹、四周留白、放大 4 倍后再识别")

    reading = read_player_location(image, backend)
    _print_location_reading("", reading)
    print("[命魂诊断] OCR 分段识别：完成；未修改生产配置")
    return {
        "screenshot": str(source_path),
        "client_size": [image.width, image.height],
        "backend": "Windows.Media.Ocr",
        "language": backend.language,
        "scene_raw": str(output / "ocr-scene-raw.png"),
        "scene_prepared": str(output / "ocr-scene-prepared.png"),
        "coordinate_raw": str(output / "ocr-coordinate-raw.png"),
        "coordinate_prepared": str(output / "ocr-coordinate-prepared.png"),
        "reading": _reading_payload(reading),
        "production_coordinate_changed": False,
        "production_config_changed": False,
    }


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
        if subtype == "ocr_roi_compare":
            report["ocr_roi_compare"] = _ocr_roi_compare_experiment(session, output)
            return _finish(report, output)
        if subtype == "background_capture_freshness":
            from .background_capture_freshness import run_background_capture_freshness
            report["background_capture_freshness"] = {
                "covered": run_background_capture_freshness(
                    session,
                    output / "covered",
                    wait_seconds=5.0,
                    sample_interval=0.25,
                    refresh_before_sampling=False,
                ),
                "refresh": run_background_capture_freshness(
                    session,
                    output / "refresh",
                    wait_seconds=5.0,
                    sample_interval=0.25,
                    refresh_before_sampling=True,
                ),
            }
            return _finish(report, output)
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
    "MOTION_PLAYFIELD_BOX",
    "MOTION_PLAYFIELD_RATIO",
    "MOTION_RIGHT_EDGE_BOX",
    "MOTION_RIGHT_EDGE_RATIO",
    "MOTION_SAMPLE_INTERVAL",
    "MOTION_WAIT_SECONDS",
    "SHORTCUT_DIAGNOSTIC_SUBTYPES",
    "classify_motion",
    "image_diff",
    "list_subtypes",
    "run_soul_shortcut_diagnostic",
]
