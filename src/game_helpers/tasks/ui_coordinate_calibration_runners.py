"""Fixed UI coordinate calibration click runners and visual checks."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..actions.background_input import BackgroundInput
from ..capture import save_png
from .shortcut_panel_vision import detect_shortcut_panel_state
from .ui_coordinate_calibration_io import session_item_profile_path
from .verification_session import VerificationSession
from .visual_state import (
    VisualStateObservation,
    VisualStateProfile,
    detect_visual_state,
    load_visual_state,
    make_visual_state_verifier,
)


def observe_visual(
    session: VerificationSession,
    profile: VisualStateProfile,
    output_path: Path,
) -> VisualStateObservation:
    frame = session.capture_frame()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_png(frame, str(output_path))
    return detect_visual_state(frame, profile)


def shortcut_verifier(
    session: VerificationSession,
    *,
    expected_collapsed: bool,
) -> Callable[[], object | None]:
    consecutive = 0

    def verify() -> object | None:
        nonlocal consecutive
        observation = detect_shortcut_panel_state(session.capture_frame())
        if observation.collapsed is expected_collapsed:
            consecutive += 1
            if consecutive >= 2:
                return observation
        else:
            consecutive = 0
        return None

    return verify


def click_item_panel(
    session: VerificationSession,
    profile: VisualStateProfile,
    click_client: tuple[int, int],
    *,
    expected_open: bool,
    timeout: float,
):
    verifier = make_visual_state_verifier(
        session.capture_frame,
        profile,
        expected_detected=expected_open,
    )
    return BackgroundInput(session.selected.hwnd).click_and_verify(
        click_client[0], click_client[1], verifier, timeout=timeout, poll_interval=0.10
    )


def run_item_panel(
    session: VerificationSession,
    click_client: tuple[int, int],
    *,
    diagnostic_dir: Path,
    timeout: float,
) -> int:
    profile_path = session_item_profile_path(session)
    profile = load_visual_state(profile_path)
    print(f"item_panel_open_profile={profile_path}")
    before = observe_visual(session, profile, diagnostic_dir / "before.png")
    print(f"item_panel_before={before.detected}")
    print(f"item_panel_before_status={before.status}")
    print(f"item_panel_before_confidence={before.confidence:.4f}")
    print(f"screenshot_before={diagnostic_dir / 'before.png'}")

    if before.detected:
        print("当前道具栏已打开：先用同一坐标后台点击关闭，再用同一坐标打开。")
        close = click_item_panel(
            session, profile, click_client, expected_open=False, timeout=timeout
        )
        print(f"close_click_dispatched={close.dispatched}")
        print(f"close_verification_verified={close.verified}")
        print(f"close_verification_elapsed={close.elapsed:.3f}s")
        after_close = observe_visual(session, profile, diagnostic_dir / "after-close.png")
        print(f"item_panel_after_close={after_close.detected}")
        print(f"screenshot_after_close={diagnostic_dir / 'after-close.png'}")
        if not close.verified:
            print("RESULT=FAIL")
            print("视觉验证未确认关闭；当前阶段请以人工观察为准。")
            return 10

    print("发送后台点击：目标=打开道具栏。")
    opened = click_item_panel(
        session, profile, click_client, expected_open=True, timeout=timeout
    )
    after_open = observe_visual(session, profile, diagnostic_dir / "after-open.png")
    print(f"open_click_dispatched={opened.dispatched}")
    print(f"open_verification_verified={opened.verified}")
    print(f"open_verification_timed_out={opened.timed_out}")
    print(f"open_verification_elapsed={opened.elapsed:.3f}s")
    print(f"item_panel_after_open={after_open.detected}")
    print(f"item_panel_after_open_status={after_open.status}")
    print(f"item_panel_after_open_confidence={after_open.confidence:.4f}")
    print(f"screenshot_after_open={diagnostic_dir / 'after-open.png'}")
    print("RESULT=PASS" if opened.verified else "RESULT=FAIL")
    if not opened.verified:
        print("视觉验证未确认打开；当前阶段请以人工观察为准，不据此否定坐标或点击。")
        return 11
    print("视觉验证确认打开。")
    return 0


def run_shortcut_panel(
    session: VerificationSession,
    click_client: tuple[int, int],
    *,
    diagnostic_dir: Path,
    timeout: float,
) -> int:
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    before_frame = session.capture_frame()
    save_png(before_frame, str(diagnostic_dir / "before.png"))
    before = detect_shortcut_panel_state(before_frame)
    print(f"shortcut_panel_before={'collapsed' if before.collapsed is True else 'expanded' if before.collapsed is False else 'unknown'}")
    print(f"shortcut_panel_before_confidence={before.confidence:.4f}")
    print(f"screenshot_before={diagnostic_dir / 'before.png'}")

    expected_collapsed = None if before.collapsed is None else not before.collapsed
    if expected_collapsed is None:
        print("当前箭头状态视觉检测未知，仍会按人工固定坐标发送一次 PostMessageW 点击。")
    else:
        state_text = "折叠" if expected_collapsed else "展开"
        print(f"点击后视觉验证目标：{state_text}态。")

    verifier = shortcut_verifier(session, expected_collapsed=expected_collapsed) if expected_collapsed is not None else (lambda: None)
    outcome = BackgroundInput(session.selected.hwnd).click_and_verify(
        click_client[0], click_client[1], verifier, timeout=timeout, poll_interval=0.10
    )
    after_frame = session.capture_frame()
    save_png(after_frame, str(diagnostic_dir / "after-click.png"))
    after = detect_shortcut_panel_state(after_frame)
    print(f"click_dispatched={outcome.dispatched}")
    print(f"verification_verified={outcome.verified}")
    print(f"verification_timed_out={outcome.timed_out}")
    print(f"verification_elapsed={outcome.elapsed:.3f}s")
    print(f"shortcut_panel_after={'collapsed' if after.collapsed is True else 'expanded' if after.collapsed is False else 'unknown'}")
    print(f"shortcut_panel_after_confidence={after.confidence:.4f}")
    print(f"screenshot_after_click={diagnostic_dir / 'after-click.png'}")
    print("RESULT=PASS" if outcome.verified else "RESULT=FAIL")
    if not outcome.verified:
        print("视觉验证未确认状态变化；当前阶段请以人工观察为准，不据此否定坐标或点击。")
    else:
        print("视觉验证确认状态变化。")
    return 0 if outcome.verified else 11
