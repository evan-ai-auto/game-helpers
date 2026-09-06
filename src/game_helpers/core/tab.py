"""Compatibility exports for hosted-view tab operations.

The Win32 implementation lives in :mod:`game_helpers.platform.windows.tabs`.
"""

from ..platform.windows.tabs import (
    GameViewTabSession,
    current_tab_index,
    find_tab_control,
    select_tab,
    wait_for_game_view,
)

__all__ = [
    "GameViewTabSession",
    "current_tab_index",
    "find_tab_control",
    "select_tab",
    "wait_for_game_view",
]
