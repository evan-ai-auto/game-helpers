"""User-selectable smoke tests for the smallest reusable diagnostic capabilities.

This module is an adapter/menu layer only. It does not move or duplicate the
underlying capability implementations, so existing flows continue to reuse the
same functions unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..vision.scene_coordinate import read_player_location
from ..vision.windows_ocr import WindowsNativeOCRBackend
from .background_capture_freshness import run_background_capture_freshness
from .background_item_panel_open_probe_visual import refresh_surface_for_capture
from .soul_shortcut_diagnostic_flow import image_diff, _refresh_capture_surface
from .soul_task_match import as_pil_image
from .shortcut_panel_vision import detect_shortcut_panel_state


@dataclass(frozen=True)
class BasicCapability:
    id: str
    name: str
    description: str


BASIC_CAPABILITIES = (
    BasicCapability("host_capture", "获取宿主窗口画面", "单次 WGC Host 捕获并保存截图。"),
    BasicCapability("game_view_capture", "获取选中游戏画面", "Host WGC 捕获后按选中 WSGAME 几何裁剪。"),
    BasicCapability("surface_health", "检查游戏画面 Surface", "检查当前选中 WSGAME Surface 是否具备捕获条件。"),
    BasicCapability("scene_coordinate_ocr", "读取场景与地图坐标", "对当前游戏画面执行场景名与 X/Y OCR。"),
    BasicCapability("shortcut_state_vision", "识别 Shortcut 当前状态", "使用现有 Shortcut ROI 识别折叠/展开状态。"),
    BasicCapability("image_diff", "执行图像差分", "对连续两次选中游戏画面执行基础像素差分。"),
    BasicCapability("surface_refresh", "执行 Surface 刷新", "单独调用现有 Surface 切换/RedrawWindow 刷新能力。"),
    BasicCapability("background_mouse_move", "发送后台鼠标移动", "仅发送 WM_MOUSEMOVE，不执行点击，不改变生产坐标。"),
    BasicCapability("capture_freshness", "验证捕获新鲜度", "独立运行 Host/WSGAME/Playfield/RightEdge 分层新鲜度检查。"),
)


def _capture(session):
    return as_pil_image(session.capture_frame()).convert("RGB")


def run_basic_capability(session, capability_id: str, output_dir: str | Path) -> dict[str, object]:
    """Run exactly one capability smoke test using existing implementations."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    image = _capture(session)

    if capability_id == "host_capture":
        host = as_pil_image(session.capture.capture(session.parent_hwnd)).convert("RGB")
        path = output / "host.png"
        host.save(path)
        return {"ok": True, "capability": capability_id, "path": str(path), "size": host.size}

    if capability_id == "game_view_capture":
        path = output / "game-view.png"
        image.save(path)
        return {"ok": True, "capability": capability_id, "path": str(path), "size": image.size}

    if capability_id == "surface_health":
        health = session.health()
        return {"ok": bool(health.ready), "capability": capability_id, "ready": health.ready, "evidence": list(health.evidence)}

    if capability_id == "scene_coordinate_ocr":
        backend = WindowsNativeOCRBackend(language="zh-Hans-CN")
        reading = read_player_location(image, backend)
        return {
            "ok": bool(reading.parsed),
            "capability": capability_id,
            "scene": reading.scene_text,
            "coordinate": reading.coordinate_text,
            "formatted": reading.formatted,
            "parsed": list(reading.parsed) if reading.parsed else None,
        }

    if capability_id == "shortcut_state_vision":
        observation = detect_shortcut_panel_state(image)
        return {
            "ok": observation.collapsed is not None,
            "capability": capability_id,
            "collapsed": observation.collapsed,
            "score": observation.score,
            "template": observation.template_name,
        }

    if capability_id == "image_diff":
        before = image
        after = _capture(session)
        diff = image_diff(before, after)
        return {
            "ok": True,
            "capability": capability_id,
            "changed_pixels": diff.changed_pixels,
            "ratio": diff.ratio,
            "bbox": list(diff.bbox) if diff.bbox else None,
        }

    if capability_id == "surface_refresh":
        result = _refresh_capture_surface(session)
        return {"ok": bool(result.get("ok")), "capability": capability_id, **result}

    if capability_id == "background_mouse_move":
        BackgroundInput(session.selected.hwnd).mouse_move(
            session.selected.client_rect.left + session.selected.client_rect.width // 2,
            session.selected.client_rect.top + session.selected.client_rect.height // 2,
        )
        return {"ok": True, "capability": capability_id, "effect": "WM_MOUSEMOVE only"}

    if capability_id == "capture_freshness":
        result = run_background_capture_freshness(
            session,
            output / "freshness",
            wait_seconds=2.0,
            sample_interval=0.5,
            refresh_before_sampling=False,
        )
        return {"ok": True, "capability": capability_id, "report": result}

    raise ValueError(f"unknown basic capability: {capability_id}")
