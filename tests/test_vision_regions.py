from game_helpers.core.models import Rect
from game_helpers.vision.ocr import parse_integer, parse_scene_coordinate
from game_helpers.vision.regions import VisionRegion


def test_parse_scene_coordinate():
    assert parse_scene_coordinate("四方城[34,44]") == ("四方城", 34, 44)
    assert parse_scene_coordinate("四方城 [34，44]") == ("四方城", 34, 44)


def test_parse_integer():
    assert parse_integer("现银 87,199") == 87199
    assert parse_integer("87199") == 87199


def test_region_scales_from_reference_resolution():
    region = VisionRegion("location", (0, 0, 150, 70), 1024, 768)
    assert region.resolve(800, 600) == Rect(0, 0, 117, 55)
