"""Continuous manual calibration flow for the 命魂快捷图标集合开关."""
from __future__ import annotations

from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture
from ..core.view_manager import GameViewManager
from .background_context import BackgroundRunGuard, foreground_hwnd
from .character_selection import CharacterSelectionResult, sync_selected_character
from .manual_coordinate import collect_client_coordinate, screen_to_client
from .verification_session import VerificationSession


def _print_geometry(label: str, geometry: object) -> None:
    print(
        f"[命魂坐标] {label}: "
        f"screen_left={geometry.screen_left}; screen_top={geometry.screen_top}; "
        f"client={geometry.client_width}x{geometry.client_height}"
    )


def run_soul_task_coordinate_collection(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    *,
    output_dir: str | Path = "diagnostic/soul_task",
) -> tuple[int, int]:
    """Collect repeatedly; only operator-confirmed clicks are retained as valid samples."""
    del output_dir
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    session = VerificationSession(
        parent_hwnd=parent_hwnd,
        selected=selection,
        manager=manager,
        capture=WindowsGraphicsCapture(),
    )
    valid_samples: list[tuple[int, int]] = []
    try:
        sync_selected_character(parent_hwnd, selection)
        geometry = session.geometry()
        print(f"[命魂坐标] 当前客户区={geometry.client_width}x{geometry.client_height}")
        _print_geometry("target客户区原点", geometry)
        print(f"[命魂坐标] target_hwnd={selection.hwnd}; parent_hwnd={parent_hwnd}; foreground_hwnd={foreground_hwnd()}")
        print("[命魂坐标] 连续验证模式：每次 F9 采点并后台点击，只有人工确认 y 的坐标计入有效样本。")
        print("[命魂坐标] 按 ESC 结束采集；不会自动重试或覆盖默认坐标。")

        while True:
            try:
                sample = collect_client_coordinate(
                    selection.hwnd,
                    prompt="请把鼠标移到目标开关上，保持不动后按 F9；按 ESC 结束",
                    foreground_hwnd_for_hover=parent_hwnd,
                )
            except (KeyboardInterrupt, EOFError):
                print("[命魂坐标] 采集结束。")
                break

            before_click_geometry = session.geometry()
            remapped_client = screen_to_client(selection.hwnd, sample.screen[0], sample.screen[1])
            dispatch_results = BackgroundInput(selection.hwnd).click(*remapped_client)
            print(f"[命魂坐标] sample_screen={sample.screen}; sample_client={sample.client}; remapped_client={remapped_client}")
            print(f"[命魂坐标] target_origin=({before_click_geometry.screen_left},{before_click_geometry.screen_top}); foreground_hwnd={foreground_hwnd()}")
            print(f"[命魂坐标] dispatch=WM_MOUSEMOVE:{dispatch_results[0]},WM_LBUTTONDOWN:{dispatch_results[1]},WM_LBUTTONUP:{dispatch_results[2]}")
            try:
                confirmation = input("本次点击是否确实改变了展开/折叠状态？y=有效，n=无效，q=结束：").strip().lower()
            except EOFError:
                confirmation = "q"
            if confirmation in {"q", "quit", "exit", "esc"}:
                break
            if confirmation in {"y", "yes", "是", "有效"}:
                valid_samples.append(remapped_client)
                print(f"[命魂坐标] VALID sample_index={len(valid_samples)} client={remapped_client}")
            else:
                print("[命魂坐标] INVALID 本次坐标未计入有效样本。")

        print(f"[命魂坐标] valid_sample_count={len(valid_samples)}")
        print(f"[命魂坐标] valid_samples={valid_samples}")
        if valid_samples:
            xs = [point[0] for point in valid_samples]
            ys = [point[1] for point in valid_samples]
            print(f"[命魂坐标] valid_bounds=x:{min(xs)}..{max(xs)},y:{min(ys)}..{max(ys)}")
            return valid_samples[-1]
        return (0, 0)
    finally:
        restore = guard.finish()
        print(f"[命魂坐标] restored_surface={restore['restored_surface']}")
        print(f"[命魂坐标] restored_tab={restore['restored_tab']}")
        print(f"[命魂坐标] foreground_unchanged={restore['foreground_unchanged']}")
