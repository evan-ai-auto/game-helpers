"""联合验证命魂快捷图标状态检测、视觉坐标与人工有效点击坐标。"""
from __future__ import annotations

import json
from pathlib import Path

from ..actions.background_input import BackgroundInput
from ..capture import WindowsGraphicsCapture, save_png
from ..core.view_manager import GameViewManager
from .background_context import BackgroundRunGuard
from .character_selection import CharacterSelectionResult, sync_selected_character
from .manual_coordinate import collect_client_coordinate, screen_to_client
from .shortcut_panel_vision import detect_shortcut_panel_state
from .soul_task import SOUL_TASK_BASELINE_SIZE
from .verification_session import VerificationSession


def _point(value: tuple[int, int]) -> list[int]:
    return [int(value[0]), int(value[1])]


def run_soul_task_detection_coordinate_validation(
    parent_hwnd: int,
    selection: CharacterSelectionResult,
    *,
    output_dir: str | Path = "diagnostic/workflow_runs/soul_task_detection_coordinate",
) -> dict[str, object]:
    """Capture full frame, crop the fixed ROI, collect manual points and verify them."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manager = GameViewManager(parent_hwnd, timeout=2.0)
    guard = BackgroundRunGuard.begin(manager)
    session = VerificationSession(
        parent_hwnd=parent_hwnd,
        selected=selection,
        manager=manager,
        capture=WindowsGraphicsCapture(),
    )
    report: dict[str, object] = {"character": selection.character_name, "samples": []}
    try:
        sync_selected_character(parent_hwnd, selection)
        geometry = session.geometry()
        client_size = (geometry.client_width, geometry.client_height)
        if client_size != SOUL_TASK_BASELINE_SIZE:
            raise RuntimeError(f"当前客户区为 {client_size[0]}x{client_size[1]}，仅支持 800x600。")

        frame = session.capture_frame()
        full_path = output / f"character-{selection.view_index}-full-before-detect.png"
        save_png(frame, str(full_path))
        panel = detect_shortcut_panel_state(frame)

        roi_left, roi_top, roi_right, roi_bottom = 0, 80, 40, 128
        roi = frame.crop((roi_left, roi_top, roi_right, roi_bottom))
        roi_path = output / f"character-{selection.view_index}-shortcut-roi.png"
        save_png(roi, str(roi_path))

        evidence = {
            "full_screenshot": str(full_path),
            "roi_screenshot": str(roi_path),
            "client_size": list(client_size),
            "roi_client": [roi_left, roi_top, roi_right, roi_bottom],
            "matched_template": panel.matched_template,
            "match_score": panel.match_score,
            "second_template": panel.second_template,
            "second_score": panel.second_score,
            "match_location_client": _point(panel.match_location) if panel.match_location else None,
            "visual_center_client": _point(panel.click_location) if panel.click_location else None,
            "collapsed": panel.collapsed,
            "evidence": list(panel.evidence),
        }
        report["detection"] = evidence
        print(f"[命魂联合验证] 完整截图：{full_path}")
        print(f"[命魂联合验证] ROI：client=({roi_left},{roi_top})-({roi_right},{roi_bottom})；截图={roi_path}")
        print(f"[命魂联合验证] 匹配框左上角：client={panel.match_location}")
        print(f"[命魂联合验证] 匹配框中心：client={panel.click_location}")
        print(f"[命魂联合验证] 模板={panel.matched_template or '无'}；score={panel.match_score:.3f}")
        print(f"[命魂联合验证] 当前状态={'折叠' if panel.collapsed is True else '展开' if panel.collapsed is False else '未知'}")

        print("[命魂联合验证] 请手动点击快捷图标，使状态发生变化；按 F9 采点，按 ESC 结束。")
        while True:
            try:
                sample = collect_client_coordinate(
                    selection.hwnd,
                    prompt="请把鼠标移到可成功展开/折叠的图标位置，按 F9；按 ESC 结束",
                    foreground_hwnd_for_hover=parent_hwnd,
                )
            except (KeyboardInterrupt, EOFError):
                break
            remapped = screen_to_client(selection.hwnd, sample.screen[0], sample.screen[1])
            before_frame = session.capture_frame()
            before = detect_shortcut_panel_state(before_frame)
            dispatch = BackgroundInput(selection.hwnd).click(*remapped)
            after_frame = session.capture_frame()
            after = detect_shortcut_panel_state(after_frame)
            changed = before.collapsed is not None and after.collapsed is not None and before.collapsed != after.collapsed
            item = {
                "screen": _point(sample.screen),
                "sample_client": _point(sample.client),
                "remapped_client": _point(remapped),
                "dispatch": list(dispatch),
                "before_collapsed": before.collapsed,
                "after_collapsed": after.collapsed,
                "state_changed": changed,
            }
            report["samples"].append(item)  # type: ignore[union-attr]
            print(f"[命魂联合验证] 候选点：client={remapped}；消息={dispatch}；状态变化={'是' if changed else '否'}")
            answer = input("本次坐标是否人工确认有效？y=计入样本，n=不计入，q=结束：").strip().lower()
            if answer in {"q", "quit", "exit", "esc"}:
                break
            item["manual_confirmed"] = answer in {"y", "yes", "是", "有效"}

        report_path = output / f"character-{selection.view_index}-validation-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[命魂联合验证] 报告：{report_path}")
        return report
    finally:
        restore = guard.finish()
        print(f"[命魂联合验证] Surface 恢复：{'成功' if restore['restored_surface'] else '失败'}")
        print(f"[命魂联合验证] 标签恢复：{'成功' if restore['restored_tab'] else '失败'}")
        print(f"[命魂联合验证] 前台窗口：{'未变化' if restore['foreground_unchanged'] else '已变化'}")
