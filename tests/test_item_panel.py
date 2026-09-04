import numpy as np

from game_helpers.capture.models import Frame
from game_helpers.core.models import Rect, WindowInfo
from game_helpers.tasks.item_panel import (
    DEFAULT_ITEM_PANEL_UI,
    ItemPanelStatus,
    compare_item_panel_state,
)


def _frame(data: bytes, width: int = 100, height: int = 100) -> Frame:
    window = WindowInfo(1, "test", "WSGAME", Rect(0, 0, width, height), True)
    return Frame(window, width, height, data, 0.0, "test")


def test_item_panel_detects_large_roi_change():
    before = np.zeros((100, 100, 4), dtype=np.uint8)
    after = before.copy()
    left = round(DEFAULT_ITEM_PANEL_UI.left * 100)
    top = round(DEFAULT_ITEM_PANEL_UI.top * 100)
    right = round(DEFAULT_ITEM_PANEL_UI.right * 100)
    bottom = round(DEFAULT_ITEM_PANEL_UI.bottom * 100)
    after[top:bottom, left:right, :3] = 255
    result = compare_item_panel_state(_frame(before.tobytes()), _frame(after.tobytes()))
    assert result.status == ItemPanelStatus.DETECTED
    assert result.detected
    assert result.changed_ratio > 0.9


def test_item_panel_ignores_small_change():
    before = np.zeros((100, 100, 4), dtype=np.uint8)
    after = before.copy()
    after[50:52, 50:52, :3] = 255
    result = compare_item_panel_state(_frame(before.tobytes()), _frame(after.tobytes()))
    assert result.status == ItemPanelStatus.NOT_DETECTED
    assert not result.detected


def test_item_panel_rejects_dimension_mismatch():
    before = np.zeros((100, 100, 4), dtype=np.uint8)
    after = np.zeros((90, 100, 4), dtype=np.uint8)
    result = compare_item_panel_state(_frame(before.tobytes()), _frame(after.tobytes(), 100, 90))
    assert result.status == ItemPanelStatus.INVALID
