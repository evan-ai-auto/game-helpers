"""Shared-session item-panel toggle verification probe.

Unlike the legacy standalone probe, this entry point receives an already
selected character context. It captures the selected WSGAME surface directly,
so host-window padding and differently sized sibling surfaces do not become
part of the visual search canvas.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.surface import inspect_surface
from ..core.view_manager import GameViewManager
from .character_selection import CharacterSelectionResult
from .verification_session import VerificationSession
from .visual_state import detect_visual_state, load_visual_state, make_visual_state_verifier

VK_F8 = 0x77
VK_ESCAPE = 0x1B


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def _foreground_hwnd() -> int:
    return int(ctypes.windll.user32.GetForegroundWindow())


def _cursor_pos() -> tuple[int, int]:
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def _screen_to_client(hwnd: int, x: int, y: int) -> tuple[int, int]:
    point = POINT(int(x), int(y))
    if not ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(point)):
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def _set_foreground(hwnd: int, timeout: float = 2.0) -> None:
    user32 = ctypes.windll.user32
    current = _foreground_hwnd()
    if current == hwnd:
        return
    current_thread = int(user32.GetWindowThreadProcessId(current, None)) if current else 0
    target_thread = int(user32.GetWindowThreadProcessId(hwnd, None))
    attached = False
    try:
        if current_thread and target_thread and current_thread != target_thread:
            if not user32.AttachThreadInput(current_thread, target_thread, True):
                raise ctypes.WinError()
            attached = True
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        deadline = time.monotonic() + timeout
        while _foreground_hwnd() != hwnd and time.monotonic() < deadline:
            time.sleep(0.02)
        if _foreground_hwnd() != hwnd:
            raise RuntimeError(f"failed to make foreground hwnd={hwnd}: current={_foreground_hwnd()}")
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, target_thread, False)


def _restore_foreground(hwnd: int) -> bool:
    _set_foreground(int(hwnd))
    return _foreground_hwnd() == int(hwnd)


def _wait_for_f8() -> bool:
    user32 = ctypes.windll.user32
    while True:
        if user32.GetAsyncKeyState(VK_ESCAPE) & 0x0001:
            return False
        if user32.GetAsyncKeyState(VK_F8) & 0x0001:
            while user32.GetAsyncKeyState(VK_F8) & 0x8000:
                time.sleep(0.02)
            return True
        time.sleep(0.03)


def run(parent_hwnd: int, selected: CharacterSelectionResult) -> int:
    """Verify a background item-panel toggle using one shared session."""
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    session = VerificationSession(
        parent_hwnd=parent_hwnd,
        selected=selected,
        manager=manager,
        capture=WindowsGraphicsCapture(),
    )
    original_surface = manager.current_surface_index()
    original_tab = manager.current_index()
    original_foreground = _foreground_hwnd()
    original_cursor = _cursor_pos()
    result_code = 1

    print(f"selected character='{selected.character_name}' view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"original_surface={original_surface}")
    print(f"original_tab={original_tab}")
    print(f"original_foreground={original_foreground}")

    try:
        session.sync_character()
        frame_before = session.capture_frame()
        geometry = session.geometry()
        health = inspect_surface(frame_before, geometry)
        print("\nselected_surface_geometry:")
        print(f"surface_client_size={geometry.client_width}x{geometry.client_height}")
        print(f"surface_screen_origin=({geometry.screen_left},{geometry.screen_top})")
        print(f"surface_dpi={geometry.dpi}")
        print(f"surface_aspect_ratio={geometry.aspect_ratio:.6f}")
        print(f"capture_size={frame_before.width}x{frame_before.height}")
        print(f"surface_health={health.status}")
        for item in health.evidence:
            print(f"surface_health_evidence={item}")
        if not health.ready:
            print("结果：选中角色的 WSGAME 捕获几何不兼容，停止视觉点击验证。")
            return 1

        output_dir = Path("diagnostic/background_item_panel_toggle")
        output_dir.mkdir(parents=True, exist_ok=True)
        save_png(frame_before, str(output_dir / f"before-character-{selected.view_index}.png"))

        _set_foreground(parent_hwnd)
        print(f"foreground_for_hover={_foreground_hwnd()}")
        print("请手动把真实鼠标移动到‘道具’图标。")
        print("确认‘道具 (Alt+E)’ tooltip 出现后保持鼠标不动，按 F8。")
        print("按 ESC 取消。")
        if not _wait_for_f8():
            print("收到 ESC，取消实验。")
            return 0

        screen_x, screen_y = _cursor_pos()
        client_x, client_y = _screen_to_client(selected.hwnd, screen_x, screen_y)
        print("\nMANUAL_HOVER_MARK")
        print(f"cursor_screen=({screen_x},{screen_y})")
        print(f"selected_client=({client_x},{client_y})")

        if not _restore_foreground(original_foreground):
            raise RuntimeError("cannot restore original foreground before background click")

        profile = load_visual_state(Path("data/assets/ui/visual_states/item_panel_open.json"))
        initial = detect_visual_state(frame_before, profile)
        print(f"item_panel_before_status={initial.status}")
        print(f"item_panel_before_confidence={initial.confidence:.6f}")
        print(f"item_panel_before_detected={initial.detected}")
        print(f"item_panel_before_origin={initial.origin}")

        target_open = not initial.detected
        print(f"target_item_panel_open={target_open}")
        verifier = make_visual_state_verifier(
            lambda: session.capture_frame(),
            profile,
            expected_detected=target_open,
        )

        outcome = BackgroundInput(selected.hwnd).click_and_verify(
            client_x,
            client_y,
            verifier,
            timeout=5.0,
            poll_interval=0.10,
        )
        frame_after = session.capture_frame()
        save_png(frame_after, str(output_dir / f"after-character-{selected.view_index}.png"))
        after = detect_visual_state(frame_after, profile)

        print(f"click_dispatched={outcome.dispatched}")
        print(f"verification_verified={outcome.verified}")
        print(f"verification_timed_out={outcome.timed_out}")
        print(f"verification_elapsed={outcome.elapsed:.3f}s")
        print(f"item_panel_after_status={after.status}")
        print(f"item_panel_after_confidence={after.confidence:.6f}")
        print(f"item_panel_after_detected={after.detected}")
        print(f"item_panel_after_origin={after.origin}")
        print(f"foreground_after_click={_foreground_hwnd()}")
        print(f"foreground_unchanged={_foreground_hwnd() == original_foreground}")

        if outcome.verified:
            print("verification_result=verified")
            print("结果：道具栏完成反向切换，并通过选中 WSGAME 的视觉状态确认。")
            result_code = 0
        elif outcome.timed_out:
            print("verification_result=pending_visual")
            print("结果：后台点击已发送，但未在超时前确认道具栏反向状态。")
        else:
            print("verification_result=incomplete")
    except Exception as exc:
        print(f"probe_error={exc}")
        result_code = 1
    finally:
        try:
            manager.switch_surface_to(original_surface)
            manager.switch_to(original_tab)
        except Exception as exc:
            print(f"context_restore_error={exc}")
            result_code = 1
        try:
            foreground_restored = _restore_foreground(original_foreground)
        except Exception as exc:
            print(f"foreground_restore_error={exc}")
            foreground_restored = False
            result_code = 1
        try:
            ctypes.windll.user32.SetCursorPos(*original_cursor)
            cursor_restored = _cursor_pos() == original_cursor
        except Exception as exc:
            print(f"cursor_restore_error={exc}")
            cursor_restored = False
            result_code = 1
        print("\n恢复测试上下文：")
        print(f"restored_surface={manager.current_surface_index() == original_surface}")
        print(f"restored_tab={manager.current_index() == original_tab}")
        print(f"foreground_restore_ok={foreground_restored}")
        print(f"foreground_final={_foreground_hwnd()}")
        print(f"foreground_unchanged={_foreground_hwnd() == original_foreground}")
        print(f"cursor_restored={cursor_restored}")
        print("道具栏状态：保留测试后的状态，不自动恢复。")

    return result_code
