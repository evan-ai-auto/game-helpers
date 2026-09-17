"""Manual calibration flow for the 命魂快捷图标集合开关."""
from __future__ import annotations

from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture
from ..core.view_manager import GameViewManager
from .background_context import BackgroundRunGuard, foreground_hwnd
from .character_selection import CharacterSelectionResult, sync_selected_character
from .manual_coordinate import collect_client_coordinate, screen_to_client
from .verification_session import VerificationSession


def run_soul_task_coordinate_collection(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    *,
    output_dir: str | Path = "diagnostic/soul_task",
) -> tuple[int, int]:
    """Collect the toggle point, remap it, click once, and let the operator confirm.

    The screen coordinate is sampled while the game is temporarily foregrounded.
    Before dispatching the background click, the same screen point is converted
    again against the target character window so window movement or client-origin
    changes do not silently reuse a stale client coordinate.
    """
    del output_dir  # Reserved for future before/after calibration screenshots.
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
        print(f"[命魂坐标] target_hwnd={selection.hwnd}; parent_hwnd={parent_hwnd}; foreground_hwnd={foreground_hwnd()}")
        print("[命魂坐标] 采集后会按采集坐标执行一次后台点击，供人工确认结果。")
        print("[命魂坐标] 不运行命魂状态检测，不自动重试点击。")
        sample = collect_client_coordinate(
            selection.hwnd,
            prompt="请把鼠标移到左上角快捷图标集合开关上（建议看到 tooltip）",
            foreground_hwnd_for_hover=parent_hwnd,
        )
        print(f"[命魂坐标] 采集完成：client={sample.client}; screen={sample.screen}")
        print(f"[命魂坐标] 采集时 foreground_hwnd={sample.foreground_hwnd_at_capture}")
        print(f"[命魂坐标] 建议保存为 shortcut_panel_toggle={sample.client}")

        # The window/client origin may change when the temporary foreground assist
        # ends. Re-map the unchanged screen point against the target HWND immediately
        # before clicking instead of blindly reusing the sampled client coordinate.
        remapped_client = screen_to_client(selection.hwnd, sample.screen[0], sample.screen[1])
        print(f"[命魂坐标] 点击前重新换算：screen={sample.screen} -> client={remapped_client}")
        print(f"[命魂坐标] 点击前 target_hwnd={selection.hwnd}; foreground_hwnd={foreground_hwnd()}")
        print(f"[命魂坐标] 测试点击：client={remapped_client}")
        BackgroundInput(selection.hwnd).click(remapped_client[0], remapped_client[1])
        print("[命魂坐标] 测试点击已发送，请肉眼确认快捷图标集合是否发生展开/折叠变化。")
        try:
            confirmation = input("点击是否生效？按 Enter/y=生效，n=未生效：").strip().lower()
        except EOFError:
            confirmation = ""
        if confirmation in {"n", "no", "否", "失败"}:
            raise RuntimeError("人工确认测试点击未生效。")
        print("[命魂坐标] 人工确认：测试点击视为生效。")
        return remapped_client
    finally:
        restore = guard.finish()
        print(f"[命魂坐标] restored_surface={restore['restored_surface']}")
        print(f"[命魂坐标] restored_tab={restore['restored_tab']}")
        print(f"[命魂坐标] foreground_unchanged={restore['foreground_unchanged']}")
