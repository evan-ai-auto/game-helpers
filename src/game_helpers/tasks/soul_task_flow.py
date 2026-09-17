"""命魂任务最小闭环：后台同步角色并检测领取状态（800×600 基线）。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from .background_context import BackgroundRunGuard
from .character_selection import CharacterSelectionResult, sync_selected_character
from .fixed_ui_coordinate import load_fixed_ui_coordinate
from .shortcut_panel_vision import detect_shortcut_panel_state
from .soul_task import (
    SOUL_TASK_BASELINE_SIZE,
    SoulTaskObservation,
    SoulTaskStatus,
    detect_soul_task_claimed_icon,
)
from .soul_task_logging import (
    claim_status_text,
    format_bool_cn,
    format_client,
    format_score,
    log_expand_failure,
    log_panel_evidence,
    log_panel_state,
    log_soul,
)
from .soul_task_models import DEFAULT_SHORTCUT_PANEL_CLICK
from .verification_session import VerificationSession


SHORTCUT_PANEL_TARGET = "shortcut_panel_toggle"


@dataclass(frozen=True)
class SoulTaskClaimDiagnosisResult:
    ok: bool
    status: SoulTaskStatus
    message: str
    observation: SoulTaskObservation | None
    panel_opened_by_tool: bool
    foreground_unchanged: bool
    restored_surface: bool
    restored_tab: bool
    screenshot_path: str | None
    client_size: tuple[int, int] | None
    error: str | None = None
    state_changed: bool | None = None
    state_confident: bool | None = None
    click_dispatch_success: bool | None = None
    verification_result: str | None = None


def _resolve_shortcut_click(
    *,
    client_size: tuple[int, int],
) -> tuple[tuple[int, int], str]:
    """Return (click_client, source_label). Vision match is never the click target."""
    fixed = load_fixed_ui_coordinate(SHORTCUT_PANEL_TARGET, resolution=client_size)
    if fixed is not None:
        return fixed, "标定坐标"
    return DEFAULT_SHORTCUT_PANEL_CLICK, "默认候选"


def _dispatch_click(hwnd: int, click: tuple[int, int]) -> bool:
    results = BackgroundInput(hwnd).click(click[0], click[1])
    return all(int(flag) != 0 for flag in results)


def _status_message(observation: SoulTaskObservation) -> str:
    if observation.status == SoulTaskStatus.CLAIMED:
        return "命魂任务状态：已领取。"
    if observation.status == SoulTaskStatus.NOT_CLAIMED:
        return "命魂任务状态：未检测到已领取图标，需要进入女娲神使领取流程。"
    return "命魂任务状态：无法可靠确认，请人工检查截图。"


def run_soul_task_claim_diagnosis(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    *,
    output_dir: str | Path = "diagnostic/soul_task",
    require_baseline: bool = True,
) -> SoulTaskClaimDiagnosisResult:
    """Background-sync the character and diagnose 命魂领取状态."""
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    capture = WindowsGraphicsCapture()
    session = VerificationSession(
        parent_hwnd=parent_hwnd,
        selected=selection,
        manager=manager,
        capture=capture,
    )

    panel_opened_by_tool = False
    observation: SoulTaskObservation | None = None
    screenshot_path: str | None = None
    client_size: tuple[int, int] | None = None
    error: str | None = None
    ok = False
    state_changed: bool | None = None
    state_confident: bool | None = None
    click_dispatch_success: bool | None = None
    verification_result: str | None = None

    try:
        sync_selected_character(parent_hwnd, selection)
        if manager.current_surface_index() != selection.view_index:
            raise RuntimeError("选中角色的 Surface 未同步")
        if manager.current_index() != selection.view_index:
            raise RuntimeError("选中角色的 Native Tab 未同步")

        geometry = session.geometry()
        client_size = (geometry.client_width, geometry.client_height)
        if require_baseline and client_size != SOUL_TASK_BASELINE_SIZE:
            raise RuntimeError(
                f"当前角色客户区为 {client_size[0]}x{client_size[1]}，"
                f"本阶段仅支持基线 {SOUL_TASK_BASELINE_SIZE[0]}x{SOUL_TASK_BASELINE_SIZE[1]}。"
            )

        click_client, click_source = _resolve_shortcut_click(client_size=client_size)
        log_soul(f"点击候选：{format_client(click_client)}；来源={click_source}")
        log_soul("说明：视觉匹配位置仅用于诊断，不作为实际点击坐标")

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        frame = session.capture_frame()
        panel = detect_shortcut_panel_state(frame)
        state_confident = panel.collapsed is not None
        log_panel_state("展开前", panel)
        log_panel_evidence("展开前", panel)
        log_soul(f"状态可信：{format_bool_cn(state_confident)}")

        if panel.collapsed is None:
            failure_path = output_dir_path / f"character-{selection.view_index}-panel-unknown.png"
            save_png(frame, str(failure_path))
            screenshot_path = str(failure_path)
            verification_result = "状态不可信"
            log_soul("展开结果：失败")
            log_soul("失败原因：展开前无法可靠确认折叠/展开状态")
            log_soul(f"点击位置：{format_client(click_client)}")
            log_soul("点击发送：未执行")
            log_soul(
                f"展开前最佳模板：{panel.matched_template or '无'}；"
                f"{format_score(panel.match_score if panel.matched_template else None)}"
            )
            log_soul(
                f"展开前次佳模板：{panel.second_template or '无'}；"
                f"{format_score(panel.second_score if panel.second_template is not None else None)}"
            )
            log_soul("处理策略：停止，不自动重试")
            raise RuntimeError("无法可靠判断快捷图标集合展开/折叠状态")

        if panel.collapsed:
            log_soul("展开决策：当前为折叠态，执行一次后台点击")
            click_dispatch_success = _dispatch_click(selection.hwnd, click_client)
            panel_opened_by_tool = True
            log_soul(
                f"执行展开点击：{format_client(click_client)}；"
                f"消息发送={'成功' if click_dispatch_success else '失败'}"
            )
            if not click_dispatch_success:
                verification_result = "点击发送失败"
                state_changed = False
                log_expand_failure(
                    reason="后台点击消息发送失败",
                    click=click_client,
                    click_dispatch_success=False,
                    panel_after=panel,
                    strategy="停止，不自动重试",
                )
                raise RuntimeError("后台点击消息发送失败")

            time.sleep(0.55)
            frame = session.capture_frame()
            panel_after = detect_shortcut_panel_state(frame)
            log_panel_state("展开后", panel_after)
            log_panel_evidence("展开后", panel_after)

            state_confident_after = panel_after.collapsed is not None
            state_changed = (
                state_confident_after
                and panel.collapsed is True
                and panel_after.collapsed is False
            )
            log_soul(f"状态变化：{format_bool_cn(bool(state_changed))}")
            log_soul(f"状态可信：{format_bool_cn(state_confident_after)}")
            log_soul(f"点击发送：{format_bool_cn(click_dispatch_success)}")

            if panel_after.collapsed is True:
                failure_path = output_dir_path / f"character-{selection.view_index}-panel-failure.png"
                save_png(frame, str(failure_path))
                screenshot_path = str(failure_path)
                verification_result = "仍为折叠"
                log_expand_failure(
                    reason="点击后仍为折叠态",
                    click=click_client,
                    click_dispatch_success=True,
                    panel_after=panel_after,
                    strategy="停止，不自动重试",
                )
                raise RuntimeError("执行一次展开点击后仍为折叠态")

            if panel_after.collapsed is None:
                failure_path = output_dir_path / f"character-{selection.view_index}-panel-unknown.png"
                save_png(frame, str(failure_path))
                screenshot_path = str(failure_path)
                verification_result = "点击后状态不可信"
                log_expand_failure(
                    reason="点击后状态无法可靠确认",
                    click=click_client,
                    click_dispatch_success=True,
                    panel_after=panel_after,
                    strategy="停止，不自动重试",
                )
                raise RuntimeError("执行展开点击后无法可靠判断状态")

            verification_result = "展开成功"
            log_soul("展开结果：成功")
        else:
            state_changed = False
            verification_result = "已是展开态"
            log_soul("展开决策：当前已经是展开态，不执行展开点击")
            log_soul("展开结果：成功")

        output = output_dir_path / f"character-{selection.view_index}.png"
        save_png(frame, str(output))
        screenshot_path = str(output)
        observation = detect_soul_task_claimed_icon(frame)
        observation = SoulTaskObservation(
            status=observation.status,
            reason=observation.reason,
            confidence=observation.confidence,
            panel_detected=observation.panel_detected,
            match_location=observation.match_location,
            evidence=observation.evidence,
            screenshot_path=screenshot_path,
        )
        log_soul(f"领取检测：{claim_status_text(observation.status)}；{format_score(observation.confidence)}")
        ok = observation.status in {
            SoulTaskStatus.CLAIMED,
            SoulTaskStatus.NOT_CLAIMED,
        }
    except Exception as exc:
        error = str(exc)
        ok = False
    finally:
        restore = guard.finish()
        restored_surface = restore["restored_surface"]
        restored_tab = restore["restored_tab"]
        foreground_unchanged = restore["foreground_unchanged"]

    if observation is not None:
        message = _status_message(observation)
    elif error:
        message = f"命魂任务状态检测失败：{error}"
    else:
        message = "命魂任务状态检测未产生结果。"

    if not foreground_unchanged:
        ok = False
        error = (error + "；" if error else "") + "前台窗口在检测过程中发生了变化"

    log_soul(f"前台窗口：{'未变化' if foreground_unchanged else '已变化'}")
    log_soul(f"Surface 恢复：{format_bool_cn(restored_surface)}")
    log_soul(f"标签恢复：{format_bool_cn(restored_tab)}")
    if verification_result:
        log_soul(f"校验结论：{verification_result}")

    return SoulTaskClaimDiagnosisResult(
        ok=ok and error is None and restored_surface and restored_tab and foreground_unchanged,
        status=observation.status if observation else SoulTaskStatus.UNKNOWN,
        message=message,
        observation=observation,
        panel_opened_by_tool=panel_opened_by_tool,
        foreground_unchanged=foreground_unchanged,
        restored_surface=restored_surface,
        restored_tab=restored_tab,
        screenshot_path=screenshot_path,
        client_size=client_size,
        error=error,
        state_changed=state_changed,
        state_confident=state_confident,
        click_dispatch_success=click_dispatch_success,
        verification_result=verification_result,
    )
