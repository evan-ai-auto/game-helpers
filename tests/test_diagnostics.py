import sys

import pytest

from game_helpers.core import diagnose_window


def test_diagnose_window_is_windows_only():
    if sys.platform == "win32":
        pytest.skip("Windows-only guard is not exercised on Windows")
    with pytest.raises(RuntimeError, match="only available on Windows"):
        diagnose_window(0)
