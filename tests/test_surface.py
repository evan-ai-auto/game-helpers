from game_helpers.capture.models import Frame
from game_helpers.core.models import Rect, WindowInfo
from game_helpers.core.surface import SurfaceGeometry, inspect_surface


def _frame(width: int, height: int) -> Frame:
    window = WindowInfo(hwnd=1, title="test", class_name="WSGAME", bounds=Rect(0, 0, width, height))
    return Frame.from_bgra(window, width, height, bytes(width * height * 4), backend="test")


def test_surface_health_ready_when_capture_matches_client() -> None:
    geometry = SurfaceGeometry(1, 1024, 768, 100, 200, 96)
    health = inspect_surface(_frame(1024, 768), geometry)
    assert health.status == "ready"
    assert health.ready
    assert health.scale_x == 1.0
    assert health.scale_y == 1.0


def test_surface_health_scaled_when_aspect_and_scale_match() -> None:
    geometry = SurfaceGeometry(1, 1024, 768, 100, 200, 96)
    health = inspect_surface(_frame(512, 384), geometry)
    assert health.status == "scaled"
    assert not health.ready
    assert health.geometry_mismatch


def test_surface_health_mismatch_when_aspect_changes() -> None:
    geometry = SurfaceGeometry(1, 1024, 768, 100, 200, 96)
    health = inspect_surface(_frame(800, 500), geometry)
    assert health.status == "mismatch"
    assert not health.ready
