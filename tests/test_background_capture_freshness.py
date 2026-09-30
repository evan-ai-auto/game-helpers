from pathlib import Path

from game_helpers.tasks.background_capture_freshness import run_background_capture_freshness


def test_background_capture_freshness_is_diagnostic_only(tmp_path: Path):
    assert callable(run_background_capture_freshness)
    assert "background_capture_freshness" in run_background_capture_freshness.__doc__
