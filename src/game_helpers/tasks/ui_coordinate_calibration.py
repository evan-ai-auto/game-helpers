"""Manual fixed-coordinate calibration for the two supported 梦幻西游 UI controls.

The experiment deliberately keeps coordinate collection separate from visual
state verification. A coordinate is collected once for the selected target and
resolution, then the existing PostMessageW click + visual verification path is
run. At this stage a PASS/FAIL result is only an auxiliary signal; the operator
should use the saved before/after screenshots and the live game view as the
manual source of truth when the visual assets are incomplete.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .fixed_ui_coordinate import DEFAULT_COORDINATES_PATH
from .manual_coordinate import collect_client_coordinate
from .shortcut_panel_vision import detect_shortcut_panel_state
from .soul_task import SOUL_TASK_BASELINE_SIZE
from .verification_session import VerificationSession
from .visual_state import (
    VisualStateObservation,
    VisualStateProfile,
    detect_visual_state,
    load_visual_state,
    make_visual_state_verifier,
)

TARGET_ITEM_PANEL = "item_panel_toggle"
TARGET_SHORTCUT_PANEL = "shortcut_panel_toggle"


def _load_samples(path: Path) -> dict:
    if not path.exists():
        return {
            "version": 1,
            "game": "梦幻西游",
            "coordinate_type": "fixed_ui",
            "samples": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError(f"不支持的坐标标定文件格式：{path}")
    samples = payload.get("samples")
    if not isinstance(samples, dict):
        raise ValueError(f"坐标标定文件缺少 samples：{path}")
    return payload


def _write_sample(
    path: Path,
    *,
    resolution_key: str,
    target: str,
    sample,
    character_name: str,
    identity: str,
) -> None:
    payload = _load_samples(path)
    payload["samples"][resolution_key] = payload["samples"].get(resolution_key, {})
    payload["samples"][resolution_key][target] = {
        "client": list(sample.client),
        "screen": list(sample.screen),
        "target_hwnd": sample.target_hwnd,
        "character_name": character_name,
        "identity": identity,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _observe_visual(
    session: VerificationSession,
    profile: VisualStateProfile,
    output_path: Path,
) -> VisualStateObservation:
    frame = session.capture_frame()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_png(frame, str(output_path))
    return detect_visual_state(frame, profile)


def _shortcut_verifier(
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


def _click_item_panel(
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


def _run_item_panel(
    session: VerificationSession,
    click_client: tuple[int, int],
    *,
    diagnostic_dir: Path,
    timeout: float,
) -> int:
    profile_path = session_item_profile_path(session)
    profile = load_visual_state(profile_path)
    print(f"item_panel_open_profile={profile_path}")
    before = _observe_visual(session, profile, diagnostic_dir / "before.png")
    print(f"item_panel_before={before.detected}")
    print(f"item_panel_before_status={before.status}")
    print(f"item_panel_before_confidence={before.confidence:.4f}")
    print(f"screenshot_before={diagnostic_dir / 'before.png'}")

    if before.detected:
        print("当前道具栏已打开：先用同一坐标后台点击关闭，再用同一坐标打开。")
        close = _click_item_panel(
            session, profile, click_client, expected_open=False, timeout=timeout
        )
        print(f"close_click_dispatched={close.dispatched}")
        print(f"close_verification_verified={close.verified}")
        print(f"close_verification_elapsed={close.elapsed:.3f}s")
        after_close = _observe_visual(session, profile, diagnostic_dir / "after-close.png")
        print(f"item_panel_after_close={after_close.detected}")
        print(f"screenshot_after_close={diagnostic_dir / 'after-close.png'}")
        if not close.verified:
            print("RESULT=FAIL")
            print("视觉验证未确认关闭；当前阶段请以人工观察为准。")
            return 10

    print("发送后台点击：目标=打开道具栏。")
    opened = _click_item_panel(
        session, profile, click_client, expected_open=True, timeout=timeout
    )
    after_open = _observe_visual(session, profile, diagnostic_dir / "after-open.png")
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


def session_item_profile_path(session: VerificationSession) -> Path:
    from .asset_resolution import resolve_resolution_asset

    geometry = session.geometry()
    return resolve_resolution_asset("item_panel_open.json", (geometry.client_width, geometry.client_height))


def _run_shortcut_panel(
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

    verifier = _shortcut_verifier(session, expected_collapsed=expected_collapsed) if expected_collapsed is not None else (lambda: None)
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


def main() -> int:
    if sys.platform != "win32":
        print("本实验仅支持 Windows。")
        return 2

    parser = argparse.ArgumentParser(description="梦幻西游固定位置 UI 坐标采集与后台点击实验。")
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output", default=str(DEFAULT_COORDINATES_PATH))
    parser.add_argument("--diagnostic-dir", default="diagnostic/calibration/ui_click")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        print("--timeout 必须大于 0。")
        return 2

    parent = find_window(args.title)
    if parent is None:
        print(f"未找到游戏主窗口: {args.title!r}")
        return 2

    scan = scan_game_accounts(parent.hwnd)
    accounts = logged_in_accounts(scan)
    print(f"parent hwnd={parent.hwnd}")
    print(f"logged_in characters={len(accounts)}")
    if not accounts:
        print("未发现已登录角色，无法采坐标。")
        return 3
    for index, account in enumerate(accounts, 1):
        resolution = account.expected_resolution
        resolution_text = f"{resolution[0]}x{resolution[1]}" if resolution else "unknown"
        print(f"  [{index}] {account.character_name!r} | 实例=#{account.view_index} | client={resolution_text} | identity={account.identity!r}")

    try:
        choice = int(input("请选择角色编号：").strip())
    except (EOFError, ValueError):
        print("角色编号无效。")
        return 4
    if not 1 <= choice <= len(accounts):
        print(f"角色编号必须在 1 到 {len(accounts)} 之间。")
        return 4

    selected = select_character(scan, accounts[choice - 1].view_index)
    sync_selected_character(parent.hwnd, selected)
    resolution = selected.account.expected_resolution
    if resolution != SOUL_TASK_BASELINE_SIZE:
        print(f"当前角色分辨率为 {resolution!r}，本实验只接受 800x600。")
        return 8
    resolution_key = f"{resolution[0]}x{resolution[1]}"
    session = VerificationSession(
        parent_hwnd=parent.hwnd,
        selected=selected,
        manager=GameViewManager(parent.hwnd, timeout=2.0),
        capture=WindowsGraphicsCapture(),
    )
    print(f"selected character={selected.character_name!r} view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"resolution_key={resolution_key}")

    print("\n[800×600 固定位置 UI 坐标采集 + 后台点击实验]")
    print("请选择采集目标：")
    print("1. 道具栏")
    print("2. 任务图标集合开关")
    print("0. 退出")
    try:
        target_choice = input("请选择采集目标：").strip()
    except EOFError:
        print("已取消。")
        return 0
    targets = {"1": TARGET_ITEM_PANEL, "2": TARGET_SHORTCUT_PANEL}
    target = targets.get(target_choice)
    if target is None:
        if target_choice == "0":
            print("已退出。")
            return 0
        print("采集目标无效。")
        return 5

    prompt = (
        "请采集当前 800×600 底部「道具」图标坐标。"
        if target == TARGET_ITEM_PANEL
        else "请采集当前 800×600 左侧「任务图标集合开关」固定位置坐标；折叠态和展开态共用此坐标。"
    )
    sample = collect_client_coordinate(
        selected.hwnd,
        prompt=prompt,
        foreground_hwnd_for_hover=parent.hwnd,
    )
    click_client = tuple(sample.client)
    output = Path(args.output)
    _write_sample(
        output,
        resolution_key=resolution_key,
        target=target,
        sample=sample,
        character_name=selected.character_name,
        identity=selected.account.identity,
    )
    print("\nMANUAL_FIXED_UI_COORDINATE")
    print(f"target={target}")
    print(f"resolution_key={resolution_key}")
    print(f"click_client={click_client}")
    print(f"cursor_screen={sample.screen}")
    print(f"target_hwnd={sample.target_hwnd}")
    print(f"saved_to={output}")
    print("坐标已记录。现在开始按现有规则执行后台点击 + 视觉验证。")

    diagnostic_dir = Path(args.diagnostic_dir) / target
    if target == TARGET_ITEM_PANEL:
        return _run_item_panel(
            session,
            click_client,
            diagnostic_dir=diagnostic_dir,
            timeout=args.timeout,
        )
    return _run_shortcut_panel(
        session,
        click_client,
        diagnostic_dir=diagnostic_dir,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
