from pathlib import Path

from PIL import Image

from game_helpers.tasks.shortcut_panel_vision import detect_shortcut_panel_state


ROOT = Path(__file__).resolve().parent.parent


def test_realistic_left_edge_arrow_is_detected_and_clicked_near_edge():
    image = Image.new("RGB", (800, 600), (104, 72, 48))
    arrow = Image.open(
        ROOT / "data/assets/ui/shortcut_toggle_right_light.png"
    ).convert("RGBA")
    image.paste(arrow, (0, 90), arrow)

    observation = detect_shortcut_panel_state(image)

    assert observation.collapsed is True
    assert observation.click_location is not None
    assert observation.click_location[0] < 20
    assert 90 <= observation.click_location[1] <= 115
