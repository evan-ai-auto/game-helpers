"""摄妖香相关：子菜单编排与完整流程。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..capture import WindowsGraphicsCapture
from ..core.view_manager import GameViewManager
from .background_context import BackgroundRunGuard
from .character_selection import CharacterSelectionResult, sync_selected_character
from .incense_inventory_scan import IncenseInventoryObservation, scan_incense_in_inventory
from .incense_status_vision import IncenseUsageObservation, detect_incense_usage
from .verification_session import VerificationSession

INCENSE_SUBTASKS = (
    ("full", "完整流程", "先识别使用态；未使用则开道具栏并检索摄妖香栏位"),
    ("usage", "使用状态识别", "右侧条折叠/展开 → 悬停闹钟图标 → OCR tooltip"),
    ("inventory", "道具栏摄妖香检索", "依赖「未使用」结论；打开道具栏后模板扫格"),
)


def choose_incense_subtask() -> str | None:
    print("[摄妖香相关] 子任务：")
    for index, (_key, name, description) in enumerate(INCENSE_SUBTASKS, start=1):
        print(f"  [{index}] [未验收] {name} - {description}")
    print("  [0] 返回")
    try:
        choice = int(input("请选择摄妖香子任务：").strip())
    except (EOFError, ValueError):
        print("[摄妖香相关] 操作编号无效")
        return None
    if choice == 0:
        return None
    if 1 <= choice <= len(INCENSE_SUBTASKS):
        return INCENSE_SUBTASKS[choice - 1][0]
    print("[摄妖香相关] 操作编号无效")
    return None


def _new_run_dir(output_dir: str | Path) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _usage_payload(obs: IncenseUsageObservation) -> dict[str, object]:
    return {
        "usage": obs.usage,
        "remaining_minutes": obs.remaining_minutes,
        "panel_collapsed": obs.panel_collapsed,
        "clock_found": obs.clock_found,
        "clock_score": obs.clock_score,
        "clock_location": list(obs.clock_location) if obs.clock_location else None,
        "hover_point": list(obs.hover_point) if obs.hover_point else None,
        "tooltip_text": obs.tooltip_text,
        "evidence": list(obs.evidence),
    }


def _inventory_payload(obs: IncenseInventoryObservation) -> dict[str, object]:
    return {
        "status": obs.status,
        "present": obs.present,
        "row": obs.row,
        "col": obs.col,
        "click_client": list(obs.click_client) if obs.click_client else None,
        "match_score": obs.match_score,
        "slot_crop_path": obs.slot_crop_path,
        "evidence": list(obs.evidence),
    }


def _print_usage(obs: IncenseUsageObservation) -> None:
    print(f"[摄妖香] usage={obs.usage}")
    if obs.remaining_minutes is not None:
        print(f"[摄妖香] remaining_minutes={obs.remaining_minutes}")
    if obs.usage == "asset_missing":
        print("[摄妖香] 阻塞：缺少闹钟图标模板，请提供后重试。")
    for line in obs.evidence:
        print(f"[摄妖香] {line}")


def _print_inventory(obs: IncenseInventoryObservation) -> None:
    print(f"[摄妖香] inventory_status={obs.status}")
    if obs.present is True:
        print(f"[摄妖香] 找到摄妖香：第 {obs.row} 排第 {obs.col} 列 | 热区={obs.click_client}")
    elif obs.present is False:
        print("[摄妖香] 道具栏中未找到摄妖香")
    if obs.status == "asset_missing":
        print("[摄妖香] 阻塞：缺少摄妖香道具图标模板，请提供后重试。")
    for line in obs.evidence:
        print(f"[摄妖香] {line}")


def run_incense_usage(
    session: VerificationSession,
    output: Path,
) -> tuple[dict[str, object], IncenseUsageObservation]:
    obs = detect_incense_usage(session, output / "usage")
    _print_usage(obs)
    payload = _usage_payload(obs)
    _write_json(output / "usage" / "result.json", payload)
    return payload, obs


def run_incense_inventory(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    session: VerificationSession,
    output: Path,
    *,
    require_unused: bool,
    usage_obs: IncenseUsageObservation | None = None,
) -> tuple[dict[str, object], IncenseInventoryObservation]:
    if require_unused:
        if usage_obs is None:
            usage_payload, usage_obs = run_incense_usage(session, output)
            _ = usage_payload
        if usage_obs.usage != "unused":
            skipped = IncenseInventoryObservation(
                status="skipped",
                present=None,
                row=None,
                col=None,
                click_client=None,
                match_score=0.0,
                slot_crop_path=None,
                evidence=(
                    f"跳过检索：当前使用态为 {usage_obs.usage}（仅 unused 时扫格）",
                ),
            )
            _print_inventory(skipped)
            payload = _inventory_payload(skipped)
            inv_dir = output / "inventory"
            inv_dir.mkdir(parents=True, exist_ok=True)
            _write_json(inv_dir / "result.json", payload)
            return payload, skipped

    obs = scan_incense_in_inventory(
        parent_hwnd,
        selection,
        session,
        output / "inventory",
        open_panel=True,
    )
    _print_inventory(obs)
    payload = _inventory_payload(obs)
    _write_json(output / "inventory" / "result.json", payload)
    return payload, obs


def run_incense_full(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    session: VerificationSession,
    output: Path,
) -> dict[str, object]:
    usage_payload, usage_obs = run_incense_usage(session, output)
    inventory_payload: dict[str, object] | None = None
    if usage_obs.usage == "unused":
        inventory_payload, _ = run_incense_inventory(
            parent_hwnd,
            selection,
            session,
            output,
            require_unused=False,
            usage_obs=usage_obs,
        )
    elif usage_obs.usage == "active":
        print(f"[摄妖香] 已使用，剩余 {usage_obs.remaining_minutes} 分钟；跳过道具栏检索。")
    else:
        print(f"[摄妖香] 使用态={usage_obs.usage}；跳过道具栏检索。")
    return {
        "usage": usage_payload,
        "inventory": inventory_payload,
    }


def run_demon_repellent_incense(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    output_dir: str | Path,
    *,
    subtask: str | None = None,
) -> dict[str, object]:
    """Interactive submenu entry for 摄妖香相关."""
    chosen = subtask if subtask is not None else choose_incense_subtask()
    if chosen is None:
        return {
            "ok": False,
            "capability": "demon_repellent_incense",
            "error": "cancelled",
            "message": "用户返回摄妖香相关菜单。",
        }

    manager = GameViewManager(parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    session = VerificationSession(
        parent_hwnd=parent_hwnd,
        selected=selection,
        manager=manager,
        capture=WindowsGraphicsCapture(),
    )
    output = _new_run_dir(output_dir)
    try:
        sync_selected_character(parent_hwnd, selection)
        if chosen == "usage":
            usage_payload, usage_obs = run_incense_usage(session, output)
            ok = usage_obs.usage in {"unused", "active"}
            result = {
                "ok": ok,
                "capability": "demon_repellent_incense",
                "subtask": chosen,
                "usage": usage_payload,
                "artifact_dir": str(output),
                "message": f"使用状态识别完成：{usage_obs.usage}",
            }
        elif chosen == "inventory":
            inventory_payload, inventory_obs = run_incense_inventory(
                parent_hwnd,
                selection,
                session,
                output,
                require_unused=True,
            )
            ok = inventory_obs.status in {"found", "not_found"}
            result = {
                "ok": ok,
                "capability": "demon_repellent_incense",
                "subtask": chosen,
                "inventory": inventory_payload,
                "artifact_dir": str(output),
                "message": f"道具栏检索完成：{inventory_obs.status}",
            }
        else:
            combined = run_incense_full(parent_hwnd, selection, session, output)
            usage = combined.get("usage") or {}
            inventory = combined.get("inventory")
            usage_state = usage.get("usage")
            if usage_state == "active":
                ok = True
            elif usage_state == "unused" and inventory is not None:
                ok = inventory.get("status") in {"found", "not_found"}
            else:
                ok = False
            result = {
                "ok": ok,
                "capability": "demon_repellent_incense",
                "subtask": "full",
                **combined,
                "artifact_dir": str(output),
                "message": "摄妖香完整流程完成。",
            }
        _write_json(output / "result.json", result)
        return result
    finally:
        guard.finish()


__all__ = [
    "INCENSE_SUBTASKS",
    "choose_incense_subtask",
    "run_demon_repellent_incense",
]
