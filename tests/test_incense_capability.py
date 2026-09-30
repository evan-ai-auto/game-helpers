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


def test_hover_transport_dispatches_expected_mouse_message(monkeypatch):
    import ctypes

    from game_helpers.tasks import incense_status_vision as vision

    class FakeDriver:
        def __init__(self):
            self.calls = []

        def mouse_move(self, x, y):
            self.calls.append(("postmessage", x, y))

        def mouse_move_sync(self, x, y):
            self.calls.append(("sendmessage", x, y))

    class FakeSession:
        class selected:
            hwnd = 42

    screen_calls = []
    cursor_calls = []

    monkeypatch.setattr(
        "game_helpers.tasks.manual_coordinate.client_to_screen",
        lambda hwnd, x, y: screen_calls.append((hwnd, x, y)) or (1000 + x, 200 + y),
    )
    monkeypatch.setattr(
        "game_helpers.tasks.manual_coordinate.cursor_screen_pos",
        lambda: (1654, 321),
    )
    monkeypatch.setattr(
        "game_helpers.tasks.manual_coordinate.screen_to_client",
        lambda hwnd, x, y: (654, 121),
    )
    monkeypatch.setattr(
        ctypes.windll.user32,
        "SetCursorPos",
        lambda x, y: cursor_calls.append((x, y)) or 1,
    )
    monkeypatch.setattr(vision.time, "sleep", lambda _seconds: None)

    driver = FakeDriver()
    vision._hover_transport(driver, strategy="postmessage", x=654, y=121)
    vision._hover_transport(driver, strategy="sendmessage", x=654, y=121)
    vision._hover_transport(
        driver, strategy="setcursor", x=654, y=121, session=FakeSession()
    )
    vision._hover_transport(
        driver, strategy="setcursor_postmessage", x=654, y=121, session=FakeSession()
    )
    assert driver.calls == [
        ("postmessage", 654, 121),
        ("sendmessage", 654, 121),
        ("postmessage", 654, 121),
    ]
    assert screen_calls == [(42, 654, 121), (42, 654, 121)]
    assert cursor_calls == [(1654, 321), (1654, 321)]


def test_match_clock_hover_uses_template_hotspot_not_bbox_center():
    from game_helpers.tasks.incense_status_vision import CLOCK_HOVER_IN_TEMPLATE

    path = INCENSE_RUNS / "20260929T163316022195Z" / "hover" / "capture.png"
    image = Image.open(path).convert("RGB")
    found, _score, hover, _reason, _box, _thr, evidence = _match_clock(image)
    assert found and hover is not None
    match_tl = None
    match_box = None
    for item in evidence:
        if item.startswith("match_top_left="):
            match_tl = tuple(int(v) for v in item.split("=", 1)[1].strip("[]").split(","))
        if item.startswith("match_box="):
            match_box = tuple(int(v) for v in item.split("=", 1)[1].strip("[]").split(","))
    assert match_tl is not None and match_box is not None
    expected = (
        match_tl[0] + CLOCK_HOVER_IN_TEMPLATE[0],
        match_tl[1] + CLOCK_HOVER_IN_TEMPLATE[1],
    )
    assert hover == expected
    geom_center = (
        (match_box[0] + match_box[2]) // 2,
        (match_box[1] + match_box[3]) // 2,
    )
    assert hover != geom_center
    assert hover[0] < geom_center[0]
    assert hover[1] <= geom_center[1]


def test_capture_to_input_nudge_aims_left_up_of_vision():
    """Human: X +2 right from (-21,8) → (-19, 8); Y stays +8."""
    from game_helpers.tasks.incense_status_vision import (
        CLOCK_CAPTURE_TO_INPUT_NUDGE,
        CLOCK_HOVER_IN_TEMPLATE,
        _vision_hover_to_input,
    )

    assert CLOCK_HOVER_IN_TEMPLATE == (12, 12)
    assert CLOCK_CAPTURE_TO_INPUT_NUDGE == (-19, 8)
    vision = (654, 121)
    aimed = _vision_hover_to_input(vision, width=800, height=600)
    assert aimed == (635, 129)


def test_hover_diagnostic_offsets_include_human_preferred_relative():
    from game_helpers.tasks.incense_status_vision import HOVER_DIAGNOSTIC_OFFSETS

    assert HOVER_DIAGNOSTIC_OFFSETS == ((0, 0), (0, 0), (0, 0), (0, 0))


def test_parse_incense_tooltip_accepts_yu_minutes():
    usage, minutes = parse_incense_tooltip("余38分钟")
    assert usage == "active"
    assert minutes == 38


def test_tooltip_looks_like_incense_for_time_reminder_title():
    from game_helpers.tasks.incense_status_vision import tooltip_looks_like_incense

    assert tooltip_looks_like_incense("时间提醒")
    assert tooltip_looks_like_incense("时间提醒 余38分钟")


def test_hover_diagnostic_strategies_include_setcursor_hybrid():
    from game_helpers.tasks.incense_status_vision import (
        DEFAULT_HOVER_STRATEGY,
        HOVER_DIAGNOSTIC_SETTLE_SECONDS,
        HOVER_DIAGNOSTIC_STRATEGIES,
    )

    # Locked verification matrix (discovery sweep retired).
    assert HOVER_DIAGNOSTIC_SETTLE_SECONDS == (0.90,)
    assert HOVER_DIAGNOSTIC_STRATEGIES == ("setcursor_postmessage",)
    assert DEFAULT_HOVER_STRATEGY == "setcursor_postmessage"


def test_tooltip_looks_like_incense_rejects_task_tracker_and_empty():
    from game_helpers.tasks.incense_status_vision import tooltip_looks_like_incense

    assert tooltip_looks_like_incense("暂无时间提醒信息")
    assert tooltip_looks_like_incense("剩余 87 分")
    assert not tooltip_looks_like_incense("")
    assert not tooltip_looks_like_incense("任务追踪 宠环")
    assert not tooltip_looks_like_incense("186伤害符")


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


def test_tooltip_ocr_box_is_tall_band_from_dial_downward():
    box = tooltip_ocr_box((654, 121), width=800, height=600)
    left, top, right, bottom = box
    assert right - left == 320
    assert bottom - top == 94
    assert top == 121 - 23
    assert bottom == top + 94
    assert left >= 480
    assert (right - left) > (bottom - top)  # X is the long axis


def test_tooltip_ocr_box_below_is_under_clock():
    from game_helpers.tasks.incense_status_vision import tooltip_ocr_box_below

    box = tooltip_ocr_box_below((654, 121), width=800, height=600)
    left, top, right, bottom = box
    assert top >= 121
    assert left >= 480
    assert right - left == 320
    assert bottom - top == 64


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
    assert tip[3] - tip[1] == 94
    assert tip[2] - tip[0] == 320
    assert tip[0] >= 480
    assert tip[3] >= hover[1] - 23
    # Hover stays inside the clock search band used for matching.
    assert search_box[0] <= hover[0] <= search_box[2]
    assert search_box[1] <= hover[1] <= search_box[3]
