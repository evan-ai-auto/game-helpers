"""Tests for parameterized UI icon detection with Shortcut gate."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from game_helpers.tasks.ui_icon_targets import DEFAULT_ICON_TARGET_ID, resolve_icon_target
from game_helpers.tasks import ui_icon_vision as vision


def test_default_target_is_soul_task_claimed():
    target = resolve_icon_target()
    assert target.id == DEFAULT_ICON_TARGET_ID
    assert "命魂" in target.name


def test_unknown_target_raises():
    with pytest.raises(KeyError, match="unknown icon target"):
        resolve_icon_target("not_registered")


def test_collapsed_panel_skips_icon_match(monkeypatch):
    panel = SimpleNamespace(
        collapsed=True,
        matched_template="right_light",
        match_score=0.9,
        reason=SimpleNamespace(value="panel_collapsed"),
        evidence=("collapsed",),
        match_location=(1, 2),
        confidence=0.9,
        second_template=None,
        second_score=None,
    )
    called = {"icon": False}

    def fake_panel(_image):
        return panel

    def fake_icon(*_args, **_kwargs):
        called["icon"] = True
        raise AssertionError("icon match must not run when collapsed")

    monkeypatch.setattr(vision, "detect_shortcut_panel_state", fake_panel)
    monkeypatch.setattr(vision, "detect_icon_in_image", fake_icon)

    result = vision.detect_ui_icon_with_shortcut_gate(Image.new("RGB", (80, 80)), target_id=DEFAULT_ICON_TARGET_ID)
    assert result.panel_state == "折叠"
    assert result.icon_checked is False
    assert result.icon is None
    assert called["icon"] is False


def test_expanded_panel_runs_icon_match(monkeypatch):
    panel = SimpleNamespace(
        collapsed=False,
        matched_template="left_light",
        match_score=0.9,
        reason=SimpleNamespace(value="panel_expanded"),
        evidence=("expanded",),
        match_location=(1, 2),
        confidence=0.9,
        second_template=None,
        second_score=None,
    )
    icon = vision.IconMatchObservation(
        found=True,
        score=0.91,
        reason="icon_found",
        match_location=(10, 20),
        search_roi=(0, 0, 40, 40),
        evidence=("ok",),
        target_id=DEFAULT_ICON_TARGET_ID,
        target_name="命魂任务已领取图标",
    )

    monkeypatch.setattr(vision, "detect_shortcut_panel_state", lambda _image: panel)
    monkeypatch.setattr(vision, "detect_icon_in_image", lambda _image, _target: icon)

    result = vision.detect_ui_icon_with_shortcut_gate(Image.new("RGB", (80, 80)))
    assert result.panel_state == "展开"
    assert result.icon_checked is True
    assert result.icon is not None
    assert result.icon.found is True
    assert result.icon.score == pytest.approx(0.91)


def test_unknown_panel_skips_icon_match(monkeypatch):
    panel = SimpleNamespace(
        collapsed=None,
        matched_template=None,
        match_score=0.0,
        reason=SimpleNamespace(value="unknown"),
        evidence=("unknown",),
        match_location=None,
        confidence=0.0,
        second_template=None,
        second_score=None,
    )
    monkeypatch.setattr(vision, "detect_shortcut_panel_state", lambda _image: panel)
    monkeypatch.setattr(vision, "detect_icon_in_image", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("icon match must not run")))

    result = vision.detect_ui_icon_with_shortcut_gate(Image.new("RGB", (80, 80)))
    assert result.panel_state == "未知"
    assert result.icon_checked is False
    assert result.icon is None


def test_claimed_icon_search_region_is_expanded_icon_list_band():
    """1,1,6 searches the Shortcut icon-list band, not the old top-left HUD rect."""
    from game_helpers.tasks.soul_task_models import SHORTCUT_EXPANDED_ICON_LIST_REGION

    target = resolve_icon_target()
    assert target.region == SHORTCUT_EXPANDED_ICON_LIST_REGION
    box = target.region.pixel(800, 600)
    assert box == (4, 80, 200, 250)
    # Historical success match top-left ~(67,145) with 29x30 template must fit.
    assert 4 <= 67 and 67 + 29 <= 200
    assert 80 <= 145 and 145 + 30 <= 250
    # First-row icons (梦/新) sit near y≈90–120; top must include padding above them.
    assert box[1] <= 85


def test_historical_success_source_still_finds_claimed_icon():
    from pathlib import Path

    path = Path(
        "diagnostic/workflow_runs/basic_capabilities/ui_icon_vision/"
        "20260923T131614902143Z/source.png"
    )
    if not path.is_file():
        pytest.skip("historical success source missing")
    image = Image.open(path).convert("RGB")
    expected_roi = resolve_icon_target().region.pixel(image.width, image.height)
    observation = vision.detect_icon_in_image(image, target=DEFAULT_ICON_TARGET_ID)
    assert observation.found is True
    assert observation.score >= 0.78
    assert observation.search_roi == expected_roi
    assert observation.match_location is not None
    assert observation.match_location[0] == pytest.approx(67, abs=2)
    assert observation.match_location[1] == pytest.approx(145, abs=2)


def test_shortcut_icon_slots_are_enumerated_and_written(tmp_path):
    from game_helpers.tasks.shortcut_icon_slots import (
        SHORTCUT_ICON_SLOT_COLS,
        SHORTCUT_ICON_SLOT_ROWS,
        write_shortcut_icon_slot_artifacts,
    )

    image = Image.new("RGB", (800, 600), color=(30, 40, 50))
    slots = write_shortcut_icon_slot_artifacts(image, tmp_path)
    assert len(slots) == SHORTCUT_ICON_SLOT_COLS * SHORTCUT_ICON_SLOT_ROWS
    slots_dir = tmp_path / "shortcut-icon-slots"
    assert (slots_dir / "slots.json").is_file()
    for item in slots:
        assert (slots_dir / item.artifact_name).is_file()
        assert item.row >= 1 and item.col >= 1
        left, top, right, bottom = item.client_rect
        assert right > left and bottom > top
        assert item.seed_rect is not None


def test_shortcut_slot_grid_covers_historical_claimed_icon():
    from game_helpers.tasks.shortcut_icon_slots import iter_shortcut_icon_slot_rects

    # Historical claimed-icon match top-left ~(67,145) should fall in r2c2 seed.
    rects = {(row, col): rect for row, col, rect, _ in iter_shortcut_icon_slot_rects()}
    left, top, right, bottom = rects[(2, 2)]
    assert left <= 67 < right
    assert top <= 145 < bottom
