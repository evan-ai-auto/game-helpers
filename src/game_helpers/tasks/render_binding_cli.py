"""Manual MVP for character-selection to rendered-surface binding."""

from __future__ import annotations

import argparse
import hashlib
import sys
import time

from ..capture import WindowsGraphicsCapture, save_png
from ..core.window import find_window
from .accounts import scan_game_accounts
from .render_binding import verify_render_binding


def _log(step: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[验证] {step}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify selected 梦幻西游 character render binding")
    parser.add_argument("title", nargs="?", default="梦幻西游 ONLINE")
    parser.add_argument("--game-index", type=int, required=True, help="one-based WSGAME index from account scan")
    args = parser.parse_args()

    if sys.platform != "win32":
        print("ERROR: this MVP requires Windows")
        return 2

    _log("1/7 查找游戏主窗口")
    parent = find_window(args.title)
    if parent is None:
        print(f"ERROR: parent window not found: {args.title!r}")
        return 2

    _log("2/7 扫描游戏实例")
    scan = scan_game_accounts(parent.hwnd)
    if not 1 <= args.game_index <= len(scan.accounts):
        print(f"ERROR: game index must be between 1 and {len(scan.accounts)}")
        return 2

    selected = scan.accounts[args.game_index - 1]
    print(f"selected index={selected.view_index}")
    print(f"identity={selected.identity!r}")
    print(f"hwnd={selected.hwnd} pid={selected.process_id}")
    print(f"title={selected.metadata.get('title', '')!r}")

    _log("3/7 捕获当前画面", "建立基线（不作为身份证明）")
    baseline = WindowsGraphicsCapture().capture(parent.hwnd)
    baseline_sha = hashlib.sha256(baseline.data).hexdigest()
    print(f"baseline_sha256={baseline_sha}")

    _log("4/7 后台切换到选中实例", f"WSGAME #{selected.view_index}")
    _log("5/7 捕获并检查渲染绑定")
    binding = verify_render_binding(
        parent.hwnd,
        selected.view_index,
        identity=selected.identity,
        previous_frame_sha256=baseline_sha,
    )
    print(f"status={binding.status}")
    print(f"visible_surface_index={binding.visible_surface_index}")
    print(f"frame_sha256={binding.frame_sha256}")
    print(f"frame_changed_from_baseline={binding.frame_changed_from_previous}")
    print(f"foreground_before={binding.foreground_hwnd_before}")
    print(f"foreground_after={binding.foreground_hwnd_after}")

    _log("6/7 保存选中实例截图")
    frame = WindowsGraphicsCapture().capture(parent.hwnd)
    output = f"diagnostic/render_binding_selected_{selected.view_index}.png"
    save_png(frame, output)
    print(f"output={output}")

    _log("7/7 完成", "请人工确认截图中的角色身份")
    time.sleep(0.05)
    return 0 if binding.status == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
