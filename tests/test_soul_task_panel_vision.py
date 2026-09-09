from pathlib import Path
from PIL import Image
from game_helpers.games.menghuanxiyou.soul_task import (
    SoulTaskUiProfile,
    UiPoint,
    UiRect,
    detect_soul_task_panel_collapsed,
)

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "data" / "assets" / "ui"


def _profile() -> SoulTaskUiProfile:
    return SoulTaskUiProfile(
        task_entry_toggle=UiPoint(0.45, 0.5),
        task_panel_icon=UiPoint(0.1, 0.1),
        claimed_icon_region=UiRect(0.0, 0.0, 1.0, 1.0),
        collapsed_toggle_region=UiRect(0.0, 0.0, 1.0, 1.0),
    )


def _scene(asset_name: str, background=(104, 72, 48)) -> Image.Image:
    image = Image.new("RGB", (80, 80), background)
    arrow = Image.open(ASSET_DIR / asset_name).convert("RGBA")
    image.paste(arrow, (28, 28), arrow)
    return image


def test_right_light_arrow_means_collapsed():
    observation = detect_soul_task_panel_collapsed(
        _scene("shortcut_toggle_right_light.png"), profile=_profile()
    )
    assert observation.collapsed is True
    assert observation.click_location is not None


def test_right_gray_arrow_means_collapsed():
    observation = detect_soul_task_panel_collapsed(
        _scene("shortcut_toggle_right_gray.png"), profile=_profile()
    )
    assert observation.collapsed is True
    assert observation.click_location is not None


def test_left_light_arrow_means_expanded():
    observation = detect_soul_task_panel_collapsed(
        _scene("shortcut_toggle_left_light.png"), profile=_profile()
    )
    assert observation.collapsed is False
    assert observation.click_location is not None


def test_toggle_assets_have_transparent_background():
    for name in (
        "shortcut_toggle_right_light.png",
        "shortcut_toggle_right_gray.png",
        "shortcut_toggle_left_light.png",
    ):
        alpha = Image.open(ASSET_DIR / name).convert("RGBA").getchannel("A")
        assert alpha.getextrema()[0] == 0
