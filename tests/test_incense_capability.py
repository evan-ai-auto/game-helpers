"""摄妖香：tooltip 解析、格号换算与子菜单选项。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from game_helpers.tasks.incense_capability_flow import INCENSE_SUBTASKS, choose_incense_subtask
from game_helpers.tasks.incense_inventory_scan import ITEM_GRID_ORIGIN, slot_index_from_match
from game_helpers.tasks.incense_status_vision import (
    CLOCK_SEARCH_REGION,
    _match_clock,
    _save_hover_on_search_roi,
    detect_right_strip_collapsed,
    hover_target_box,
    parse_incense_tooltip,
    tooltip_looks_like_task_tracker,
    tooltip_ocr_box,
)

ROOT = Path(__file__).resolve().parent.parent
INCENSE_RUNS = ROOT / "diagnostic" / "workflow_runs" / "basic_capabilities" / "demon_repellent_incense"


def test_parse_incense_tooltip_unused():
    usage, minutes = parse_incense_tooltip("暂无时间提醒信息")
    assert usage == "unused"
    assert minutes is None


def test_parse_incense_tooltip_active_minutes():
    usage, minutes = parse_incense_tooltip("剩余 87 分")
    assert usage == "active"
    assert minutes == 87


def test_parse_incense_tooltip_active_compact():
    usage, minutes = parse_incense_tooltip("剩余30分")
    assert usage == "active"
    assert minutes == 30


def test_parse_incense_tooltip_unknown():
    usage, minutes = parse_incense_tooltip("无关文本")
    assert usage == "unknown"
    assert minutes is None


def test_slot_index_from_match_first_cell():
    row, col, click = slot_index_from_match(ITEM_GRID_ORIGIN)
    assert (row, col) == (1, 1)
    assert click == (ITEM_GRID_ORIGIN[0] + 25, ITEM_GRID_ORIGIN[1] + 25)


def test_slot_index_from_match_row2_col3():
    origin = ITEM_GRID_ORIGIN
    top_left = (origin[0] + 2 * 51, origin[1] + 1 * 51)
    row, col, click = slot_index_from_match(top_left)
    assert (row, col) == (2, 3)
    assert click == (origin[0] + 2 * 51 + 25, origin[1] + 1 * 51 + 25)


def test_incense_submenu_options():
    assert [item[0] for item in INCENSE_SUBTASKS] == ["full", "usage", "hover", "inventory"]
    assert INCENSE_SUBTASKS[0][1] == "完整流程"


def test_choose_incense_subtask_menu(monkeypatch):
    answers = iter(["1", "2", "3", "4", "0", "9"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert choose_incense_subtask() == "full"
    assert choose_incense_subtask() == "usage"
    assert choose_incense_subtask() == "hover"
    assert choose_incense_subtask() == "inventory"
    assert choose_incense_subtask() is None
    assert choose_incense_subtask() is None


def test_hover_transport_dispatches_expected_mouse_message():
    from game_helpers.tasks.incense_status_vision import _hover_transport

    class FakeDriver:
        def __init__(self):
            self.calls = []

        def mouse_move(self, x, y):
            self.calls.append(("postmessage", x, y))

        def mouse_move_sync(self, x, y):
            self.calls.append(("sendmessage", x, y))

    driver = FakeDriver()
    _hover_transport(driver, strategy="postmessage", x=654, y=121)
    _hover_transport(driver, strategy="sendmessage", x=654, y=121)
    assert driver.calls == [("postmessage", 654, 121), ("sendmessage", 654, 121)]


def test_hover_diagnostic_settle_sequence_is_ordered():
    from game_helpers.tasks.incense_status_vision import HOVER_DIAGNOSTIC_SETTLE_SECONDS

    assert HOVER_DIAGNOSTIC_SETTLE_SECONDS == (0.20, 0.45, 0.90)
    assert HOVER_DIAGNOSTIC_SETTLE_SECONDS == tuple(sorted(HOVER_DIAGNOSTIC_SETTLE_SECONDS))


def test_right_strip_expanded_uses_top_band_arrow():
    """Regression: right arrow near ROI top must decide expanded via geometry."""
    path = INCENSE_RUNS / "20260929T080752020791Z" / "usage" / "capture.png"
    observation = detect_right_strip_collapsed(Image.open(path))
    assert observation.collapsed is False
    assert any(item.startswith("decide=arrow-direction") for item in observation.evidence)
    assert any(item.startswith("arrow-direction=right") for item in observation.evidence)


def test_right_strip_collapsed_not_misread_as_expanded():
    """Regression: left arrow near ROI top must not fall back to right_* template."""
    path = INCENSE_RUNS / "20260929T080821789358Z" / "usage" / "capture.png"
    observation = detect_right_strip_collapsed(Image.open(path))
    assert observation.collapsed is True
    assert any(item.startswith("decide=arrow-direction") for item in observation.evidence)
    assert any(item.startswith("arrow-direction=left") for item in observation.evidence)

def test_incense_clock_template_asset_present_and_loadable():
    """Regression: the supplied 800x600 clock asset is present and loadable."""
    from game_helpers.tasks.incense_status_vision import CLOCK_TEMPLATE_PATH
    from game_helpers.tasks.soul_task_match import load_template, resolve_template_path

    path = resolve_template_path(CLOCK_TEMPLATE_PATH)
    assert path.is_file()
    template_rgb, alpha = load_template(path)
    assert template_rgb.shape[:2] == (25, 26)
    assert alpha.shape == (25, 26)
    assert float(alpha.sum()) > 0.0


def test_clock_search_roi_covers_task_tracker_header():
    left, top, right, bottom = CLOCK_SEARCH_REGION.pixel(800, 600)
    assert (left, top, right, bottom) == (620, 90, 800, 145)


def test_match_clock_hits_header_not_task_body():
    """Regression: header-band ROI must hit the 任务追踪 clock, not task body."""
    path = INCENSE_RUNS / "20260929T092457347199Z" / "usage" / "capture.png"
    image = Image.open(path).convert("RGB")
    found, score, hover, reason, box, _thr, _ev = _match_clock(image)
    assert found is True
    assert reason == "icon_found"
    assert box == (620, 90, 800, 145)
    assert score >= 0.90
    assert hover is not None
    # True clock center ~ (654,121); reject old false hover ~(763,198).
    assert abs(hover[0] - 654) <= 20
    assert abs(hover[1] - 121) <= 20
    assert hover[1] < 145


def test_parse_rejects_task_tracker_ocr_as_incense_tooltip():
    usage, minutes = parse_incense_tooltip("任务追踪 宠环 找到转轮王")
    assert usage == "unknown"
    assert minutes is None
    assert tooltip_looks_like_task_tracker("签到答题 (0/5)")


def test_hover_target_box_is_small_around_clock_center():
    box = hover_target_box((654, 121), width=800, height=600)
    assert box == (630, 97, 678, 145)
    assert box[2] - box[0] == 48
    assert box[3] - box[1] == 48


def test_tooltip_ocr_box_is_narrow_band_above_clock():
    box = tooltip_ocr_box((654, 121), width=800, height=600)
    left, top, right, bottom = box
    assert right - left == 180
    assert bottom - top == 56
    assert bottom <= 121  # stays above hover center
    assert top < bottom


def test_hover_evidence_artifacts_cover_clock_on_search_roi(tmp_path):
    """Manual-review crops: hover crosshair must land on the clock in search ROI."""
    path = INCENSE_RUNS / "20260929T092457347199Z" / "usage" / "capture.png"
    image = Image.open(path).convert("RGB")
    found, _score, hover, _reason, search_box, _thr, _ev = _match_clock(image)
    assert found and hover is not None
    target = hover_target_box(hover, width=image.width, height=image.height)
    image.crop(target).save(tmp_path / "hover-target-roi.png")
    _save_hover_on_search_roi(
        image, search_box=search_box, hover=hover, path=tmp_path / "hover-on-search-roi.png"
    )
    annotated = Image.open(tmp_path / "hover-on-search-roi.png")
    assert annotated.size == (search_box[2] - search_box[0], search_box[3] - search_box[1])
    tip = tooltip_ocr_box(hover, width=image.width, height=image.height)
    assert tip[3] - tip[1] <= 60
    assert tip[2] - tip[0] <= 200
    # Hover stays inside the clock search band used for matching.
    assert search_box[0] <= hover[0] <= search_box[2]
    assert search_box[1] <= hover[1] <= search_box[3]
