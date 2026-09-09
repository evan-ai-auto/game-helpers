import json

from game_helpers.tasks.fixed_ui_coordinate import load_fixed_ui_coordinate


def test_load_fixed_ui_coordinate_by_resolution(tmp_path):
    path = tmp_path / "ui_coordinates.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "game": "梦幻西游",
                "coordinate_type": "fixed_ui",
                "samples": {
                    "800x600": {
                        "item_panel_toggle": {"client": [427, 575]},
                        "shortcut_panel_toggle": {"client": [8, 93]},
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert load_fixed_ui_coordinate(
        "item_panel_toggle", resolution=(800, 600), path=path
    ) == (427, 575)
    assert load_fixed_ui_coordinate(
        "shortcut_panel_toggle", resolution=(800, 600), path=path
    ) == (8, 93)
    assert load_fixed_ui_coordinate(
        "item_panel_toggle", resolution=(1024, 768), path=path
    ) is None


def test_load_fixed_ui_coordinate_rejects_invalid_point(tmp_path):
    path = tmp_path / "ui_coordinates.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "game": "梦幻西游",
                "coordinate_type": "fixed_ui",
                "samples": {
                    "800x600": {
                        "item_panel_toggle": {"client": [800, 600]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    assert load_fixed_ui_coordinate(
        "item_panel_toggle", resolution=(800, 600), path=path
    ) is None
