"""Manual calibration flow for the 命魂快捷图标集合开关."""
from __future__ import annotations

from pathlib import Path

from .background_context import BackgroundRunGuard
from .character_selection import CharacterSelectionResult, sync_selected_character
from .manual_coordinate import collect_client_coordinate
from .verification_session import VerificationSession
from ..capture import WindowsGraphicsCapture
from ..core.view_manager import GameViewManager


def run_soul_task_coordinate_collection(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    *,
    output_dir: str | Path = "diagnostic/soul_task",
) -> tuple[int, int]:
    """Bring the selected character into view and collect the toggle client point.

    This flow only calibrates coordinates. It does not click the toggle or run
    the soul-task state detector.
    """
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    session = VerificationSession(
        parent_hwnd=parent_hwnd,
        selected=selection,
        manager=manager,
        capture=WindowsGraphicsCapture(),
    )
    try:
        sync_selected_character(parent_hwnd, selection)
        geometry = session.geometry()
        client_size = (geometry.client_width, geometry.client_height)
        print(f"[命魂坐标] 当前客户区={client_size[0]}x{client_size[1]}")
        print("[命魂坐标] 仅采集快捷图标集合开关坐标，不执行展开/折叠点击。")
        sample = collect_client_coordinate(
            selection.hwnd,
            prompt="请把鼠标移到左上角快捷图标集合开关上（建议看到 tooltip）",
            foreground_hwnd_for_hover=parent_hwnd,
        )
        print(f"[命魂坐标] 采集完成：client={sample.client}; screen={sample.screen}")
        print(f"[命魂坐标] 建议保存为 shortcut_panel_toggle={sample.client}")
        return sample.client
    finally:
        restore = guard.finish()
        print(f"[命魂坐标] restored_surface={restore['restored_surface']}")
        print(f"[命魂坐标] restored_tab={restore['restored_tab']}")
        print(f"[命魂坐标] foreground_unchanged={restore['foreground_unchanged']}")
