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
