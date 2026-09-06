"""Compatibility exports for the generic child-window discovery contract.

The Win32 implementation lives in :mod:`game_helpers.platform.windows.children`.
"""

from __future__ import annotations

from ..platform.windows.children import list_child_windows

__all__ = ["list_child_windows"]
