import sys

from game_helpers.core import find_window, list_windows


def test_window_discovery_is_safe_on_non_windows():
    if sys.platform != "win32":
        assert list_windows() == []
        assert find_window("definitely-not-a-real-window") is None
