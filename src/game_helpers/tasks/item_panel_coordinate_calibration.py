"""Backward-compatible entry point for the fixed UI coordinate calibration experiment.

The implementation now lives in :mod:`game_helpers.tasks.ui_coordinate_calibration`
and supports the two current calibration targets: 道具栏 and 任务图标集合开关.
"""
from __future__ import annotations

from .ui_coordinate_calibration import main


if __name__ == "__main__":
    raise SystemExit(main())
