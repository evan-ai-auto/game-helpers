"""User-selectable smoke tests for the smallest reusable diagnostic capabilities.

This module is an adapter/menu layer only. It does not move or duplicate the
underlying capability implementations, so existing flows continue to reuse the
same functions unchanged.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ..actions.background_input import BackgroundInput
from ..vision.scene_coordinate import read_player_location
from ..vision.windows_ocr import WindowsNativeOCRBackend
from ..capture import WindowsGraphicsCapture
from ..core.view_manager import GameViewManager
from .background_capture_freshness import run_background_capture_freshness
from .background_context import BackgroundRunGuard
from .basic_capabilities import get_basic_capability
from .character_selection import CharacterSelectionResult, sync_selected_character
from .verification_session import VerificationSession
from .soul_shortcut_diagnostic_flow import image_diff, _refresh_capture_surface
from .soul_task_match import as_pil_image
from .shortcut_panel_vision import SHORTCUT_PANEL_TOGGLE_REGION, detect_shortcut_panel_state
from .ui_icon_targets import DEFAULT_ICON_TARGET_ID
from .ui_icon_vision import detect_ui_icon_with_shortcut_gate
from .item_panel_flow import run_item_panel_detect_and_toggle
from .incense_capability_flow import run_demon_repellent_incense


def _capture(session):
    return as_pil_image(session.capture_frame()).convert("RGB")


def _shortcut_state_label(collapsed: bool | None) -> str:
    if collapsed is True:
        return "折叠"
    if collapsed is False:
        return "展开"
    return "未知"


def _new_run_dir(output_dir: str | Path) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _record_source_path(source_path: Path) -> str:
    """Record source paths without leaking machine-specific absolute paths."""
    path = Path(source_path)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return f"<external>/{path.name}"


def _choose_dao_ju_lan_target(before) -> bool | None:
    print("[道具栏相关] 当前状态：{}".format("打开" if before.open else "关闭"))
    print("  [1] 打开道具栏")
    print("  [2] 关闭道具栏")
    print("  [0] 返回")
    try:
        choice = int(input("请选择道具栏操作：").strip())
    except (EOFError, ValueError):
        print("[道具栏相关] 操作编号无效")
        return None
    if choice == 0:
        return None
    if choice == 1:
        return True
    if choice == 2:
        return False
    print("[道具栏相关] 操作编号无效")
    return None


def _item_panel_result_payload(flow_result) -> dict[str, object]:
    """Normalize item-panel flow result for result.json / CLI printing."""
    if is_dataclass(flow_result) and not isinstance(flow_result, type):
        payload: dict[str, object] = asdict(flow_result)
    else:
        payload = dict(getattr(flow_result, "__dict__", {}))
    payload.setdefault("capability", "dao_ju_lan")
    return payload


def _persist_basic_capability_run(
    capability,
    run_dir: Path,
    result: dict[str, object],
) -> dict[str, object]:
    _write_json(run_dir / "result.json", result)
    artifacts = sorted(path.name for path in run_dir.iterdir())
    _write_json(
        run_dir / "run.json",
        {
            "capability": capability.id,
            "name": capability.name,
            "description": capability.description,
            "implementation": capability.implementation,
            "artifacts": artifacts,
        },
    )
    print(f"[基础能力] artifact_dir={run_dir}")
    return {**result, "artifact_dir": str(run_dir)}


def run_basic_capability(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    capability_id: str,
    output_dir: str | Path,
    *,
    ui_icon_target_id: str | None = None,
    ui_icon_source_mode: str | None = None,
    ui_icon_source_path: str | Path | None = None,
) -> dict[str, object]:
    """Run exactly one capability smoke test using existing implementations."""
    capability = get_basic_capability(capability_id)
    if capability_id == "dao_ju_lan":
        run_dir = _new_run_dir(output_dir)
        flow_result = run_item_panel_detect_and_toggle(
            parent_hwnd,
            selection,
            output_dir=run_dir,
            target_selector=_choose_dao_ju_lan_target,
        )
        result = _item_panel_result_payload(flow_result)
        return _persist_basic_capability_run(capability, run_dir, result)
    if capability_id == "demon_repellent_incense":
        return run_demon_repellent_incense(parent_hwnd, selection, output_dir)
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    session = VerificationSession(parent_hwnd=parent_hwnd, selected=selection, manager=manager, capture=WindowsGraphicsCapture())
    try:
        sync_selected_character(parent_hwnd, selection)
        geometry = session.geometry()
        if (geometry.client_width, geometry.client_height) != (800, 600):
            raise RuntimeError("当前客户区不是 800x600，基础能力测试停止。")
        run_dir = _new_run_dir(output_dir)
        # ui_icon_vision only keeps the selected detection image as source.png.
        if capability_id == "ui_icon_vision":
            image = (
                _capture(session)
                if (ui_icon_source_mode or "live_capture") == "live_capture"
                else None
            )
        else:
            image = _capture(session)
            image.save(run_dir / "capture.png")
        result = _run_basic_capability_session(
            session,
            capability_id,
            run_dir,
            image,
            ui_icon_target_id=ui_icon_target_id,
            ui_icon_source_mode=ui_icon_source_mode,
            ui_icon_source_path=ui_icon_source_path,
        )
        return _persist_basic_capability_run(capability, run_dir, result)
    finally:
        guard.finish()


def _run_basic_capability_session(
    session,
    capability_id: str,
    output_dir: str | Path,
    image,
    *,
    ui_icon_target_id: str | None = None,
    ui_icon_source_mode: str | None = None,
    ui_icon_source_path: str | Path | None = None,
):
    capability = get_basic_capability(capability_id)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
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
        state = _shortcut_state_label(observation.collapsed)
        roi_box = SHORTCUT_PANEL_TOGGLE_REGION.pixel(image.width, image.height)
        image.crop(roi_box).save(output / "shortcut-toggle-roi.png")
        return {
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
            "roi": list(roi_box),
        }

    if capability_id == "ui_icon_vision":
        target_id = ui_icon_target_id or DEFAULT_ICON_TARGET_ID
        source_mode = ui_icon_source_mode or "live_capture"
        if source_mode == "file":
            if ui_icon_source_path is None:
                raise RuntimeError("ui_icon_vision file 模式必须提供 source_path")
            source_path = Path(ui_icon_source_path)
            if not source_path.is_file():
                raise RuntimeError(f"检测图源不存在: {source_path}")
            source_image = Image.open(source_path).convert("RGB")
            recorded_source = _record_source_path(source_path)
        elif source_mode == "live_capture":
            if image is None:
                raise RuntimeError("ui_icon_vision live_capture 模式缺少实时截图")
            source_image = image
            recorded_source = "live_capture"
        else:
            raise RuntimeError(f"未知 ui_icon_vision source_mode: {source_mode}")

        # Only persist the image actually used for detection.
        source_image.save(output / "source.png")

        try:
            gated = detect_ui_icon_with_shortcut_gate(source_image, target_id=target_id)
        except KeyError as exc:
            raise RuntimeError(str(exc)) from exc
        panel = gated.panel
        toggle_roi = SHORTCUT_PANEL_TOGGLE_REGION.pixel(source_image.width, source_image.height)
        source_image.crop(toggle_roi).save(output / "shortcut-toggle-roi.png")
        payload: dict[str, object] = {
            "ok": True,
            "capability": capability.id,
            "target_id": gated.target_id,
            "target_name": gated.target_name,
            "source_mode": source_mode,
            "source_path": recorded_source,
            "source_artifact": "source.png",
            "panel_state": gated.panel_state,
            "collapsed": panel.collapsed,
            "panel_template": panel.matched_template,
            "panel_score": panel.match_score,
            "panel_reason": getattr(panel.reason, "value", str(panel.reason)),
            "panel_evidence": list(panel.evidence),
            "icon_checked": gated.icon_checked,
            "icon_found": None,
            "icon_score": None,
            "icon_reason": None,
            "icon_match_location": None,
            "icon_search_roi": None,
            "icon_evidence": None,
        }
        if gated.icon is not None:
            icon = gated.icon
            left, top, right, bottom = icon.search_roi
            source_image.crop((left, top, right, bottom)).save(output / "icon-search-roi.png")
            payload.update(
                {
                    "icon_found": icon.found,
                    "icon_score": icon.score,
                    "icon_reason": icon.reason,
                    "icon_match_location": list(icon.match_location) if icon.match_location else None,
                    "icon_search_roi": list(icon.search_roi),
                    "icon_evidence": list(icon.evidence),
                }
            )
        return payload

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
        # BackgroundInput posts client-relative coords; CharacterSelectionResult
        # has no client_rect — use the selected WSGAME surface geometry.
        geometry = session.geometry()
        target = (geometry.client_width // 2, geometry.client_height // 2)
        BackgroundInput(session.selected.hwnd).mouse_move(*target)
        return {
            "ok": True,
            "capability": capability.id,
            "effect": "WM_MOUSEMOVE only",
            "client_point": list(target),
        }

    if capability_id == "find_npc_and_interact":
        return {
            "ok": True,
            "capability": capability.id,
            "status": "not_implemented",
            "message": "NPC 寻访能力尚在路上，先记下目标；定位、对话和选项交互后续补上。",
        }

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
