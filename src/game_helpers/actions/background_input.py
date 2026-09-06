"""Compatibility exports for the Win32 background input transport.

The implementation lives in :mod:`game_helpers.platform.windows.input`.
"""

from ..platform.windows.input import BackgroundClickVerification, BackgroundInput

__all__ = ["BackgroundClickVerification", "BackgroundInput"]
