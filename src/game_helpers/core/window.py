"""Compatibility exports for the generic window contract.

The Windows implementation lives in :mod:`game_helpers.platform.windows.window`.
"""

from ..platform.windows.window import find_window, get_window_info, list_windows

__all__ = ["find_window", "get_window_info", "list_windows"]
