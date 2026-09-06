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
from .soul_task import (
    DEFAULT_SOUL_TASK_UI,
    SOUL_TASK_BASELINE_SIZE,
    SoulTaskObservation,
    SoulTaskStatus,
    detect_soul_task_claimed_icon,
    detect_soul_task_panel_collapsed,
)
from .verification_session import VerificationSession


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


def _click_soul_task_toggle(hwnd: int, frame_width: int, frame_height: int) -> tuple[int, int]:
    """Click the panel toggle in selected WSGAME client coordinates."""
    local_x, local_y = DEFAULT_SOUL_TASK_UI.task_entry_toggle.pixel(frame_width, frame_height)
    BackgroundInput(hwnd).click_sync(local_x, local_y)
    return local_x, local_y


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
    """Background-sync the character and diagnose 命魂领取状态.

    Does not raise the game window. Does not auto-claim the task from an NPC.
    Reuses stable capabilities: sync_selected_character, VerificationSession,
    BackgroundInput, soul_task detectors, BackgroundRunGuard.
    """
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

        frame = session.capture_frame()
        panel = detect_soul_task_panel_collapsed(frame)
        if panel.collapsed is None:
            raise RuntimeError("无法可靠判断命魂任务界面展开/折叠状态")

        if panel.collapsed:
            _click_soul_task_toggle(selection.hwnd, frame.width, frame.height)
            panel_opened_by_tool = True
            time.sleep(0.55)
            frame = session.capture_frame()
            panel_after = detect_soul_task_panel_collapsed(frame)
            if panel_after.collapsed is True:
                raise RuntimeError("点击展开开关后仍检测为折叠状态")
            if panel_after.collapsed is None:
                raise RuntimeError("点击展开开关后无法可靠判断面板状态")

        output = Path(output_dir) / f"character-{selection.view_index}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
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
        ok = observation.status in {SoulTaskStatus.CLAIMED, SoulTaskStatus.NOT_CLAIMED}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        ok = False
    finally:
        if panel_opened_by_tool:
            try:
                frame_restore = session.capture_frame()
                _click_soul_task_toggle(selection.hwnd, frame_restore.width, frame_restore.height)
                time.sleep(0.35)
            except Exception:
                pass
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
        error = (error + "; " if error else "") + "前台窗口在检测过程中发生了变化"

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
    )
