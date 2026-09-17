"""Manual calibration flows for the 命魂快捷图标集合开关."""
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
    print(f"[命魂坐标] {label}: screen_left={geometry.screen_left}; screen_top={geometry.screen_top}; client={geometry.client_width}x{geometry.client_height}")

def _session(parent_hwnd: int, selection: CharacterSelectionResult):
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    return manager, BackgroundRunGuard.begin(manager), VerificationSession(parent_hwnd=parent_hwnd, selected=selection, manager=manager, capture=WindowsGraphicsCapture())

def run_soul_task_coordinate_collection(parent_hwnd: int, selection: CharacterSelectionResult, *, output_dir: str | Path = "diagnostic/soul_task") -> tuple[int, int]:
    del output_dir
    manager, guard, session = _session(parent_hwnd, selection)
    try:
        sync_selected_character(parent_hwnd, selection)
        geometry = session.geometry()
        print(f"[命魂坐标] 当前客户区={geometry.client_width}x{geometry.client_height}")
        _print_geometry("target客户区原点", geometry)
        print(f"[命魂坐标] target_hwnd={selection.hwnd}; parent_hwnd={parent_hwnd}; foreground_hwnd={foreground_hwnd()}")
        print("[命魂坐标] 采集后会按采集坐标执行一次后台点击，供人工确认结果。")
        print("[命魂坐标] 不运行命魂状态检测，不自动重试点击。")
        sample = collect_client_coordinate(selection.hwnd, prompt="请把鼠标移到左上角快捷图标集合开关上（建议看到 tooltip）", foreground_hwnd_for_hover=parent_hwnd)
        print(f"[命魂坐标] 采集完成：client={sample.client}; screen={sample.screen}")
        before = session.geometry(); _print_geometry("点击前target客户区原点", before)
        remapped = screen_to_client(selection.hwnd, sample.screen[0], sample.screen[1])
        result = BackgroundInput(selection.hwnd).click(*remapped)
        print(f"[命魂坐标] 点击消息发送结果：WM_MOUSEMOVE={result[0]}; WM_LBUTTONDOWN={result[1]}; WM_LBUTTONUP={result[2]}")
        if input("点击是否生效？按 Enter/y=生效，n=未生效：").strip().lower() in {"n", "no", "否", "失败"}:
            raise RuntimeError("人工确认测试点击未生效。")
        return remapped
    finally:
        restore = guard.finish(); print(f"[命魂坐标] restored_surface={restore['restored_surface']}"); print(f"[命魂坐标] restored_tab={restore['restored_tab']}"); print(f"[命魂坐标] foreground_unchanged={restore['foreground_unchanged']}")

def run_soul_task_coordinate_continuous_verification(parent_hwnd: int, selection: CharacterSelectionResult, *, output_dir: str | Path = "diagnostic/soul_task") -> tuple[int, int]:
    del output_dir
    manager, guard, session = _session(parent_hwnd, selection)
    samples = []
    try:
        sync_selected_character(parent_hwnd, selection)
        print("[命魂连续验证] 每次 F9 采点并后台点击；y=有效，n=无效，q=结束。")
        while True:
            try: sample = collect_client_coordinate(selection.hwnd, prompt="请把鼠标移到目标开关上，保持不动后按 F9；按 ESC 结束", foreground_hwnd_for_hover=parent_hwnd)
            except (KeyboardInterrupt, EOFError): break
            remapped = screen_to_client(selection.hwnd, sample.screen[0], sample.screen[1]); result = BackgroundInput(selection.hwnd).click(*remapped)
            print(f"[命魂连续验证] sample_screen={sample.screen}; sample_client={sample.client}; remapped_client={remapped}; dispatch={result}")
            answer = input("本次点击是否确实改变了展开/折叠状态？y=有效，n=无效，q=结束：").strip().lower()
            if answer in {"q", "quit", "exit", "esc"}: break
            if answer in {"y", "yes", "是", "有效"}: samples.append(remapped); print(f"[命魂连续验证] VALID sample_index={len(samples)} client={remapped}")
        print(f"[命魂连续验证] valid_sample_count={len(samples)}"); print(f"[命魂连续验证] valid_samples={samples}")
        return samples[-1] if samples else (0, 0)
    finally:
        restore = guard.finish(); print(f"[命魂连续验证] restored_surface={restore['restored_surface']}"); print(f"[命魂连续验证] restored_tab={restore['restored_tab']}"); print(f"[命魂连续验证] foreground_unchanged={restore['foreground_unchanged']}")
