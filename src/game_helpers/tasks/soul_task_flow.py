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
    SoulTaskPanelObservation,
    SoulTaskStatus,
    detect_soul_task_claimed_icon,
)
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


def _click_soul_task_toggle(
    hwnd: int,
    frame_width: int,
    frame_height: int,
    panel: SoulTaskPanelObservation,
    *,
    fixed_coordinate: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Click the calibrated fixed point when available, otherwise the detected arrow center."""
    if fixed_coordinate is not None:
        local_x, local_y = fixed_coordinate
    elif panel.click_location is not None:
        local_x, local_y = panel.click_location
    else:
        raise RuntimeError("快捷图标集合未提供可靠点击位置")

    # WSGAME's background UI path accepts queued mouse messages here. Keep the
    # existing PostMessageW transport; only the coordinate source changes.
    BackgroundInput(hwnd).click(local_x, local_y)
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
    fixed_shortcut_coordinate: tuple[int, int] | None = None
    coordinate_source = "vision"

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
        fixed_shortcut_coordinate = load_fixed_ui_coordinate(
            SHORTCUT_PANEL_TARGET,
            resolution=client_size,
        )
        if fixed_shortcut_coordinate is not None:
            coordinate_source = f"fixed={fixed_shortcut_coordinate}"

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        frame = session.capture_frame()
        panel = detect_shortcut_panel_state(frame)
        if panel.collapsed is None:
            raise RuntimeError(
                "无法可靠判断命魂任务快捷图标集合展开/折叠状态; "
                f"coordinate_source={coordinate_source}; "
                + "; ".join(panel.evidence)
            )

        if panel.collapsed:
            click_location = _click_soul_task_toggle(
                selection.hwnd,
                frame.width,
                frame.height,
                panel,
                fixed_coordinate=fixed_shortcut_coordinate,
            )
            panel_opened_by_tool = True
            time.sleep(0.55)
            frame = session.capture_frame()
            panel_after = detect_shortcut_panel_state(frame)
            if panel_after.collapsed is True:
                failure_path = output_dir_path / f"character-{selection.view_index}-panel-failure.png"
                save_png(frame, str(failure_path))
                screenshot_path = str(failure_path)
                raise RuntimeError(
                    "点击快捷图标集合开关后仍检测为折叠状态; "
                    f"click={click_location}; source={coordinate_source}; "
                    f"matched={panel.matched_template}; "
                    + "; ".join(panel_after.evidence)
                )
            if panel_after.collapsed is None:
                failure_path = output_dir_path / f"character-{selection.view_index}-panel-unknown.png"
                save_png(frame, str(failure_path))
                screenshot_path = str(failure_path)
                raise RuntimeError(
                    "点击快捷图标集合开关后无法可靠判断展开状态; "
                    f"click={click_location}; source={coordinate_source}; "
                    + "; ".join(panel_after.evidence)
                )

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
        ok = observation.status in {
            SoulTaskStatus.CLAIMED,
            SoulTaskStatus.NOT_CLAIMED,
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        ok = False
    finally:
        # Do not click the shortcut-panel toggle a second time here. The CLI's
        # contract is to leave the panel in the state reached by the workflow;
        # the previous restore click made a successful collapsed->expanded run
        # end in the original collapsed state.
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
