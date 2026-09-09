"""Minimal manual calibration probe for the 800x600 item-panel toggle.

This is deliberately separate from normal item-panel automation. It lets the
operator hover the real ``道具`` icon, press F8, and persist the resulting
screen/client coordinate under a resolution-specific key. The sample can then
be used as evidence for a later fixed-coordinate input experiment.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..core.window import find_window
from .accounts import scan_game_accounts
from .character_selection import logged_in_accounts, select_character, sync_selected_character
from .manual_coordinate import collect_client_coordinate
from .soul_task import SOUL_TASK_BASELINE_SIZE

DEFAULT_OUTPUT = Path("diagnostic/calibration/item_panel_coordinates.json")


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


def _write_sample(path: Path, *, resolution_key: str, sample, character_name: str, identity: str) -> None:
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


def main() -> int:
    if sys.platform != "win32":
        print("本探针仅支持 Windows。")
        return 2

    parser = argparse.ArgumentParser(
        description="人工采集梦幻西游道具栏开关坐标；当前仅接受 800×600。"
    )
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

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
    print(f"selected character={selected.character_name!r} view_index={selected.view_index} hwnd={selected.hwnd}")
    print(f"resolution_key={resolution_key}")
    print("\n[800×600 道具坐标标定]")
    print("1. 程序会临时把游戏窗口置前。")
    print("2. 请把真实鼠标移到‘道具’图标，确认出现‘道具 (Alt+E)’ tooltip。")
    print("3. 保持鼠标不动，按 F8；ESC 取消。")

    sample = collect_client_coordinate(
        selected.hwnd,
        prompt="请采集当前 800×600 的底部「道具」图标坐标。",
        foreground_hwnd_for_hover=parent.hwnd,
    )
    output = Path(args.output)
    _write_sample(
        output,
        resolution_key=resolution_key,
        sample=sample,
        character_name=selected.character_name,
        identity=selected.account.identity,
    )

    print("\nMANUAL_ITEM_PANEL_COORDINATE")
    print(f"resolution_key={resolution_key}")
    print(f"click_client={sample.client}")
    print(f"cursor_screen={sample.screen}")
    print(f"target_hwnd={sample.target_hwnd}")
    print(f"saved_to={output}")
    print("采集完成：本次仅记录坐标，不发送后台点击，不修改游戏状态。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
