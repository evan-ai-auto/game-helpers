"""摄妖香：tooltip 解析、格号换算与子菜单选项。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from game_helpers.tasks.incense_capability_flow import INCENSE_SUBTASKS, choose_incense_subtask
from game_helpers.tasks.incense_inventory_scan import ITEM_GRID_ORIGIN, slot_index_from_match
from game_helpers.tasks.incense_status_vision import detect_right_strip_collapsed, parse_incense_tooltip

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
    assert [item[0] for item in INCENSE_SUBTASKS] == ["full", "usage", "inventory"]
    assert INCENSE_SUBTASKS[0][1] == "完整流程"


def test_choose_incense_subtask_menu(monkeypatch):
    answers = iter(["1", "2", "3", "0", "9"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert choose_incense_subtask() == "full"
    assert choose_incense_subtask() == "usage"
    assert choose_incense_subtask() == "inventory"
    assert choose_incense_subtask() is None
    assert choose_incense_subtask() is None


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
