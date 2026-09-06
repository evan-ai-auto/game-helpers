"""道具栏状态检测与反向切换（按客户区分辨率选资产；当前优先 800×600）。

默认 ``coord_source=auto``：优先资产内人工确认的 ``click_client``，否则模板定位。
``manual`` / ``auto_then_manual`` 仅用于标定。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from .asset_resolution import resolve_resolution_asset
from .background_context import BackgroundRunGuard, foreground_hwnd
from .character_selection import CharacterSelectionResult, sync_selected_character
from .manual_coordinate import CoordSource, collect_client_coordinate, parse_coord_source
from .soul_task import SOUL_TASK_BASELINE_SIZE
from .verification_session import VerificationSession
from .visual_state import (
    detect_visual_state,
    find_template_match,
    load_visual_state,
    make_visual_state_verifier,
)


@dataclass(frozen=True)
class ItemPanelObservation:
    open: bool
    status: str
    confidence: float
    detected: bool
    origin: tuple[int, int] | None
    screenshot_path: str | None


@dataclass(frozen=True)
class ItemPanelFlowResult:
    ok: bool
    before: ItemPanelObservation | None
    after: ItemPanelObservation | None
    toggled: bool
    toggle_verified: bool
    message: str
    foreground_unchanged: bool
    restored_surface: bool
    restored_tab: bool
    click_client: tuple[int, int] | None
    icon_match_score: float | None = None
    coord_source_requested: str | None = None
    coord_source_used: str | None = None
    resolution_key: str | None = None
    error: str | None = None


def _observe(
    session: VerificationSession,
    profile,
    *,
    output_path: Path | None,
) -> ItemPanelObservation:
    frame = session.capture_frame()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_png(frame, str(output_path))
    observation = detect_visual_state(frame, profile)
    return ItemPanelObservation(
        open=bool(observation.detected),
        status=str(observation.status),
        confidence=float(observation.confidence),
        detected=bool(observation.detected),
        origin=observation.origin,
        screenshot_path=str(output_path) if output_path is not None else None,
    )


def _status_text(open_: bool) -> str:
    return "打开" if open_ else "关闭"


def _load_toggle_asset(client_size: tuple[int, int]) -> tuple[Path, dict]:
    path = resolve_resolution_asset("item_bar_toggle.json", client_size)
    return path, json.loads(path.read_text(encoding="utf-8"))


def _try_locate_item_bar_icon(
    session: VerificationSession,
    client_size: tuple[int, int],
) -> tuple[tuple[int, int], float] | None:
    asset_path, payload = _load_toggle_asset(client_size)
    image_path = (asset_path.parent / str(payload["image"])).resolve()
    threshold = float(payload.get("threshold", 0.75))
    search_step = max(1, int(payload.get("search_step", 1)))
    y0_raw = payload.get("y0_fraction")
    y0_fraction = float(y0_raw) if y0_raw is not None else None
    match = find_template_match(
        session.capture_frame(),
        image_path,
        threshold=threshold,
        search_step=search_step,
        y0_fraction=y0_fraction,
    )
    if match is None:
        return None
    return match.center, float(match.score)


def _stored_click_client(payload: dict) -> tuple[int, int] | None:
    raw = payload.get("click_client")
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError("item_bar_toggle.click_client 必须是 [x, y]")
    return int(raw[0]), int(raw[1])


def _resolve_click_client(
    *,
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    session: VerificationSession,
    client_size: tuple[int, int],
    coord_source: CoordSource,
) -> tuple[tuple[int, int], float | None, str]:
    """Return (client_xy, template_score_or_none, source_used)."""
    if coord_source == "manual":
        sample = collect_client_coordinate(
            selection.hwnd,
            prompt="请把鼠标移到底部「道具」图标上（出现「道具 (Alt+E)」提示后保持不动）。",
            foreground_hwnd_for_hover=parent_hwnd,
        )
        return sample.client, None, "manual"

    asset_path, payload = _load_toggle_asset(client_size)
    stored = _stored_click_client(payload)
    if stored is not None:
        print(f"coord_source=stored_click asset={asset_path}")
        print(f"toggle_click_client={stored}")
        return stored, None, "stored_click"

    located = _try_locate_item_bar_icon(session, client_size)
    if located is not None:
        click_client, score = located
        print("coord_source=auto_template")
        print(f"icon_match_score={score:.4f}")
        print(f"toggle_click_client={click_client}")
        return click_client, score, "auto_template"

    if coord_source == "auto":
        raise RuntimeError(
            f"自动定位失败（无 click_client 且模板未命中）：{asset_path}。"
            "可用 --coord-source manual 或 auto_then_manual。"
        )

    print("自动定位失败，回退到人工 F8 采坐标…")
    sample = collect_client_coordinate(
        selection.hwnd,
        prompt="请把鼠标移到底部「道具」图标上（出现「道具 (Alt+E)」提示后保持不动）。",
        foreground_hwnd_for_hover=parent_hwnd,
    )
    return sample.client, None, "auto_then_manual"


def run_item_panel_detect_and_toggle(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    *,
    output_dir: str | Path = "diagnostic/item_panel_flow",
    require_baseline: bool = True,
    toggle_timeout: float = 8.0,
    coord_source: CoordSource | str = "auto",
) -> ItemPanelFlowResult:
    """Detect item-panel open/closed, then toggle to the opposite state."""
    requested = parse_coord_source(str(coord_source))
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    session = VerificationSession(
        parent_hwnd=parent_hwnd,
        selected=selection,
        manager=manager,
        capture=WindowsGraphicsCapture(),
    )
    out = Path(output_dir)
    before: ItemPanelObservation | None = None
    after: ItemPanelObservation | None = None
    click_client: tuple[int, int] | None = None
    icon_match_score: float | None = None
    coord_source_used: str | None = None
    resolution_key: str | None = None
    toggled = False
    toggle_verified = False
    error: str | None = None

    try:
        sync_selected_character(parent_hwnd, selection)
        geometry = session.geometry()
        client_size = (geometry.client_width, geometry.client_height)
        resolution_key = f"{client_size[0]}x{client_size[1]}"
        if require_baseline and client_size != SOUL_TASK_BASELINE_SIZE:
            raise RuntimeError(
                f"当前角色客户区为 {client_size[0]}x{client_size[1]}，"
                f"本阶段仅支持基线 {SOUL_TASK_BASELINE_SIZE[0]}x{SOUL_TASK_BASELINE_SIZE[1]}。"
            )

        open_profile_path = resolve_resolution_asset("item_panel_open.json", client_size)
        profile = load_visual_state(open_profile_path)
        print(f"[道具栏] 使用分辨率资产 {resolution_key}")
        print(f"item_panel_open_profile={open_profile_path}")
        print("[道具栏] 后台检测当前状态…")
        before = _observe(session, profile, output_path=out / f"before-character-{selection.view_index}.png")
        target_open = not before.open
        print(f"item_panel_before={_status_text(before.open)}")
        print(f"item_panel_before_status={before.status}")
        print(f"item_panel_before_confidence={before.confidence:.4f}")
        print(f"item_panel_before_origin={before.origin}")
        print(f"screenshot_before={before.screenshot_path}")
        print(f"target_item_panel={_status_text(target_open)}")
        print(f"coord_source_requested={requested}")
        if requested == "auto":
            print("[道具栏] 坐标模式=auto（不会临时把游戏拉到前台；仅 manual/auto_then_manual 采点才会）")

        print("[道具栏] 解析点击坐标…")
        fg_before_coord = foreground_hwnd()
        click_client, icon_match_score, coord_source_used = _resolve_click_client(
            parent_hwnd=parent_hwnd,
            selection=selection,
            session=session,
            client_size=client_size,
            coord_source=requested,
        )
        print(f"coord_source_used={coord_source_used}")
        print(f"toggle_click_client={click_client}")
        print(f"foreground_unchanged_during_coord={foreground_hwnd() == fg_before_coord}")
        if requested == "auto" and foreground_hwnd() != fg_before_coord:
            raise RuntimeError(
                "纯自动坐标解析阶段前台被改变（不应发生）。"
                f"before={fg_before_coord}, after={foreground_hwnd()}"
            )

        verifier = make_visual_state_verifier(
            session.capture_frame,
            profile,
            expected_detected=target_open,
        )
        print(f"[道具栏] 后台点击切换到「{_status_text(target_open)}」…")
        fg_before_click = foreground_hwnd()
        outcome = BackgroundInput(selection.hwnd).click_and_verify(
            click_client[0],
            click_client[1],
            verifier,
            timeout=toggle_timeout,
            poll_interval=0.10,
        )
        toggled = bool(outcome.dispatched)
        toggle_verified = bool(outcome.verified)
        after = _observe(session, profile, output_path=out / f"after-character-{selection.view_index}.png")
        print(f"click_dispatched={outcome.dispatched}")
        print(f"verification_verified={outcome.verified}")
        print(f"verification_timed_out={outcome.timed_out}")
        print(f"verification_elapsed={outcome.elapsed:.3f}s")
        print(f"item_panel_after={_status_text(after.open)}")
        print(f"item_panel_after_confidence={after.confidence:.4f}")
        print(f"item_panel_after_origin={after.origin}")
        print(f"screenshot_after={after.screenshot_path}")
        print(f"foreground_unchanged_during_click={foreground_hwnd() == fg_before_click}")

        if after.open != target_open:
            raise RuntimeError(
                f"期望道具栏为「{_status_text(target_open)}」，"
                f"检测仍为「{_status_text(after.open)}」。"
            )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        restore = guard.finish()

    if error:
        message = f"道具栏流程失败：{error}"
        ok = False
    elif before is None or after is None:
        message = "道具栏流程未完成检测。"
        ok = False
    elif after.open == (not before.open):
        message = (
            f"道具栏状态检测与反向切换通过：{_status_text(before.open)} → {_status_text(after.open)}。"
        )
        ok = True
    else:
        message = "道具栏已点击，但最终状态未确认与期望相反。"
        ok = False

    return ItemPanelFlowResult(
        ok=ok and error is None and restore["restored_surface"] and restore["restored_tab"],
        before=before,
        after=after,
        toggled=toggled,
        toggle_verified=toggle_verified,
        message=message,
        foreground_unchanged=restore["foreground_unchanged"],
        restored_surface=restore["restored_surface"],
        restored_tab=restore["restored_tab"],
        click_client=click_client,
        icon_match_score=icon_match_score,
        coord_source_requested=requested,
        coord_source_used=coord_source_used,
        resolution_key=resolution_key,
        error=error,
    )
