"""800x600 item-panel coordinate calibration and background-click experiment.

This probe intentionally goes one step beyond coordinate collection: after the
operator records the real ``道具`` icon coordinate, it sends a background
PostMessageW click to that exact client coordinate and verifies the item-panel
visual state changed. This makes the calibration useful for deciding whether
the coordinate and the current background input channel are actually valid.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.window import find_window
from ..core.view_manager import GameViewManager
from .accounts import scan_game_accounts
from .asset_resolution import resolve_resolution_asset
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .manual_coordinate import collect_client_coordinate
from .soul_task import SOUL_TASK_BASELINE_SIZE
from .verification_session import VerificationSession
from .visual_state import detect_visual_state, load_visual_state, make_visual_state_verifier

DEFAULT_OUTPUT = Path("diagnostic/calibration/item_panel_coordinates.json")
DEFAULT_DIAGNOSTIC_DIR = Path("diagnostic/calibration/item_panel_click")


def _load_samples(path: Path) -> dict:
    if not path.exists():
        return {
            "version": 1,
            "game": "梦幻西游",
            "coordinate_type": "item_panel_toggle",
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
    sample,
    character_name: str,
    identity: str,
) -> None:
    payload = _load_samples(path)
    payload.setdefault("version", 1)
    payload.setdefault("game", "梦幻西游")
    payload.setdefault("coordinate_type", "item_panel_toggle")
    payload.setdefault("samples", {})
    payload["samples"][resolution_key] = {
        "client": list(sample.client),
        "screen": list(sample.screen),
        "target_hwnd": sample.target_hwnd,
        "character_name": character_name,
        "identity": identity,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _observe(session: VerificationSession, profile, output_path: Path):
    frame = session.capture_frame()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_png(frame, str(output_path))
    return detect_visual_state(frame, profile)


def _click_and_verify(
    *,
    session: VerificationSession,
    click_client: tuple[int, int],
    profile,
    expected_open: bool,
    timeout: float,
):
    verifier = make_visual_state_verifier(
        session.capture_frame,
        profile,
        expected_detected=expected_open,
    )
    return BackgroundInput(session.selected.hwnd).click_and_verify(
        click_client[0],
        click_client[1],
        verifier,
        timeout=timeout,
        poll_interval=0.10,
    )


def main() -> int:
    if sys.platform != "win32":
        print("本实验仅支持 Windows。")
        return 2

    parser = argparse.ArgumentParser(
        description=(
            "人工采集梦幻西游 800×600 道具栏坐标，并用该坐标发送后台点击、"
            "验证道具栏是否实际打开。"
        )
    )
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--diagnostic-dir", default=str(DEFAULT_DIAGNOSTIC_DIR))
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
        print(
            f"  [{index}] {account.character_name!r} | 实例=#{account.view_index} | "
            f"client={resolution_text} | identity={account.identity!r}"
        )

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
        print(
            f"当前角色分辨率为 {resolution!r}，本实验只接受 "
            f"{SOUL_TASK_BASELINE_SIZE[0]}x{SOUL_TASK_BASELINE_SIZE[1]}。"
        )
        return 8

    resolution_key = f"{resolution[0]}x{resolution[1]}"
    diagnostic_dir = Path(args.diagnostic_dir)
    output = Path(args.output)
    profile_path = resolve_resolution_asset("item_panel_open.json", resolution)
    profile = load_visual_state(profile_path)
    session = VerificationSession(
        parent_hwnd=parent.hwnd,
        selected=selected,
        manager=GameViewManager(parent.hwnd, timeout=2.0),
        capture=WindowsGraphicsCapture(),
    )

    print(
        f"selected character={selected.character_name!r} "
        f"view_index={selected.view_index} hwnd={selected.hwnd}"
    )
    print(f"resolution_key={resolution_key}")
    print(f"item_panel_open_profile={profile_path}")

    print("\n[800×600 道具坐标 + 后台点击验证实验]")
    print("1. 程序会临时把游戏窗口置前。")
    print("2. 请把真实鼠标移到‘道具’图标，确认出现‘道具 (Alt+E)’ tooltip。")
    print("3. 保持鼠标不动，按 F8；ESC 取消。")
    print("4. 采点完成后程序会恢复原前台窗口，然后用该 client 坐标发送 PostMessageW 后台点击。")
    print("5. 若道具栏已打开，会先用同一坐标关闭，再用同一坐标重新打开，确保测试包含‘打开’动作。")

    sample = collect_client_coordinate(
        selected.hwnd,
        prompt="请采集当前 800×600 的底部「道具」图标坐标。",
        foreground_hwnd_for_hover=parent.hwnd,
    )
    click_client = tuple(sample.client)
    _write_sample(
        output,
        resolution_key=resolution_key,
        sample=sample,
        character_name=selected.character_name,
        identity=selected.account.identity,
    )

    print("\nMANUAL_ITEM_PANEL_COORDINATE")
    print(f"resolution_key={resolution_key}")
    print(f"click_client={click_client}")
    print(f"cursor_screen={sample.screen}")
    print(f"target_hwnd={sample.target_hwnd}")
    print(f"saved_to={output}")
    print("坐标已记录。现在开始实际后台点击验证（PostMessageW）。")

    before = _observe(session, profile, diagnostic_dir / "before.png")
    print(f"item_panel_before={before.detected}")
    print(f"item_panel_before_status={before.status}")
    print(f"item_panel_before_confidence={before.confidence:.4f}")
    print(f"screenshot_before={diagnostic_dir / 'before.png'}")

    if before.detected:
        print("当前道具栏已打开：先用同一坐标后台点击关闭，再用同一坐标打开。")
        close_outcome = _click_and_verify(
            session=session,
            click_client=click_client,
            profile=profile,
            expected_open=False,
            timeout=args.timeout,
        )
        print(f"close_click_dispatched={close_outcome.dispatched}")
        print(f"close_verification_verified={close_outcome.verified}")
        print(f"close_verification_elapsed={close_outcome.elapsed:.3f}s")
        after_close = _observe(session, profile, diagnostic_dir / "after-close.png")
        print(f"item_panel_after_close={after_close.detected}")
        print(f"screenshot_after_close={diagnostic_dir / 'after-close.png'}")
        if not close_outcome.verified:
            print("RESULT=FAIL")
            print("失败原因：同一人工坐标无法通过 PostMessageW 后台点击使已打开的道具栏关闭。")
            return 10

    print("发送后台点击：目标=打开道具栏。")
    open_outcome = _click_and_verify(
        session=session,
        click_client=click_client,
        profile=profile,
        expected_open=True,
        timeout=args.timeout,
    )
    after_open = _observe(session, profile, diagnostic_dir / "after-open.png")
    print(f"open_click_dispatched={open_outcome.dispatched}")
    print(f"open_verification_verified={open_outcome.verified}")
    print(f"open_verification_timed_out={open_outcome.timed_out}")
    print(f"open_verification_elapsed={open_outcome.elapsed:.3f}s")
    print(f"item_panel_after_open={after_open.detected}")
    print(f"item_panel_after_open_status={after_open.status}")
    print(f"item_panel_after_open_confidence={after_open.confidence:.4f}")
    print(f"screenshot_after_open={diagnostic_dir / 'after-open.png'}")

    if not open_outcome.verified:
        print("RESULT=FAIL")
        print(
            "失败原因：坐标已采集，但 PostMessageW 点击后未观察到道具栏打开。"
            "下一步应根据 before/after-open 截图判断是点击命中区、HWND/input surface，还是消息通道问题。"
        )
        return 11

    print("RESULT=PASS")
    print("结论：800×600 人工坐标有效，并且当前选中 HWND 可通过 PostMessageW 后台点击打开道具栏。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
