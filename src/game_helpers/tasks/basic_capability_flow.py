"""User-selectable smoke tests for the smallest reusable diagnostic capabilities.

This module is an adapter/menu layer only. It does not move or duplicate the
underlying capability implementations, so existing flows continue to reuse the
same functions unchanged.
"""
from __future__ import annotations

from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..vision.scene_coordinate import read_player_location
from ..vision.windows_ocr import WindowsNativeOCRBackend
from ..capture import WindowsGraphicsCapture
from ..core.view_manager import GameViewManager
from .background_capture_freshness import run_background_capture_freshness
from .background_context import BackgroundRunGuard
from .basic_capabilities import BASIC_CAPABILITIES, get_basic_capability
from .character_selection import CharacterSelectionResult, sync_selected_character
from .verification_session import VerificationSession
from .soul_shortcut_diagnostic_flow import image_diff, _refresh_capture_surface
from .soul_task_match import as_pil_image
from .shortcut_panel_vision import detect_shortcut_panel_state



def _capture(session):
    return as_pil_image(session.capture_frame()).convert("RGB")


def _shortcut_state_label(collapsed: bool | None) -> str:
    if collapsed is True:
        return "折叠"
    if collapsed is False:
        return "展开"
    return "未知"


def run_basic_capability(parent_hwnd: int, selection: CharacterSelectionResult, capability_id: str, output_dir: str | Path) -> dict[str, object]:
    """Run exactly one capability smoke test using existing implementations."""
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    session = VerificationSession(parent_hwnd=parent_hwnd, selected=selection, manager=manager, capture=WindowsGraphicsCapture())
    try:
        sync_selected_character(parent_hwnd, selection)
        geometry = session.geometry()
        if (geometry.client_width, geometry.client_height) != (800, 600):
            raise RuntimeError("当前客户区不是 800x600，基础能力测试停止。")
        return _run_basic_capability_session(session, capability_id, output_dir)
    finally:
        guard.finish()


def _run_basic_capability_session(session, capability_id: str, output_dir: str | Path):
    capability = get_basic_capability(capability_id)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    image = _capture(session)

    if capability_id == "host_capture":
        host = as_pil_image(session.capture.capture(session.parent_hwnd)).convert("RGB")
        path = output / "host.png"
        host.save(path)
        return {"ok": True, "capability": capability.id, "path": str(path), "size": host.size}

    if capability_id == "game_view_capture":
        path = output / "game-view.png"
        image.save(path)
        return {"ok": True, "capability": capability.id, "path": str(path), "size": image.size}

    if capability_id == "surface_health":
        health = session.health()
        return {"ok": bool(health.ready), "capability": capability.id, "ready": health.ready, "evidence": list(health.evidence)}

    if capability_id == "scene_coordinate_ocr":
        backend = WindowsNativeOCRBackend(language="zh-Hans-CN")
        reading = read_player_location(image, backend)
        return {
            "ok": bool(reading.parsed),
            "capability": capability.id,
            "scene": reading.scene_text,
            "coordinate": reading.coordinate_text,
            "formatted": reading.formatted,
            "parsed": list(reading.parsed) if reading.parsed else None,
        }

    if capability_id == "shortcut_state_vision":
        observation = detect_shortcut_panel_state(image)
        state = _shortcut_state_label(observation.collapsed)        return {
            # UNKNOWN is a valid detection result, not a guessed state.
            "ok": True,
            "capability": capability.id,
            "state": state,
            "collapsed": observation.collapsed,
            "template": observation.matched_template,
            "score": observation.match_score,
            "confidence": observation.confidence,
            "reason": getattr(observation.reason, "value", str(observation.reason)),
            "evidence": list(observation.evidence),
            "match_location": list(observation.match_location) if observation.match_location else None,
            "second_template": observation.second_template,
            "second_score": observation.second_score,
        }

    if capability_id == "image_diff":
        before = image
        after = _capture(session)
        diff = image_diff(before, after)
        return {
            "ok": True,
            "capability": capability.id,
            "changed_pixels": diff.changed_pixels,
            "ratio": diff.ratio,
            "bbox": list(diff.bbox) if diff.bbox else None,
        }

    if capability_id == "surface_refresh":
        result = _refresh_capture_surface(session)
        return {"ok": bool(result.get("ok")), "capability": capability.id, **result}

    if capability_id == "background_mouse_move":
        BackgroundInput(session.selected.hwnd).mouse_move(
            session.selected.client_rect.left + session.selected.client_rect.width // 2,
            session.selected.client_rect.top + session.selected.client_rect.height // 2,
        )
        return {"ok": True, "capability": capability.id, "effect": "WM_MOUSEMOVE only"}

    if capability_id == "capture_freshness":
        result = run_background_capture_freshness(
            session,
            output / "freshness",
            wait_seconds=2.0,
            sample_interval=0.5,
            refresh_before_sampling=False,
        )
        return {"ok": True, "capability": capability.id, "report": result}

    raise ValueError(f"unknown basic capability: {capability_id}")
