from PIL import Image

from game_helpers.tasks.soul_shortcut_diagnostic_flow import (
    SHORTCUT_DIAGNOSTIC_SUBTYPES,
    classify_motion,
    image_diff,
)


def test_subtypes_list_full_then_independent_experiments():
    """Menu order: full first, then each stand-alone subtype."""
    assert SHORTCUT_DIAGNOSTIC_SUBTYPES == (
        ("full", "完整验证流程"),
        ("motion", "角色运动状态验证"),
        ("ocr_roi_compare", "800×600 OCR 多 ROI 对照验证"),
        ("hover", "Hover 二级 ROI 隔离验证"),
        ("postmessage_hover", "PostMessageW Hover 验证"),
        ("click_hotspot", "后台 Click + Hotspot 验证"),
        ("background_capture_freshness", "后台覆盖捕获新鲜度分层验证"),
    )


def test_classify_motion_uses_coordinates_and_playfield():
    assert classify_motion(("四方城", 34, 44), ("四方城", 34, 44)) == "静止候选"
    assert classify_motion(("四方城", 34, 44), ("四方城", 35, 44)) == "移动"
    assert classify_motion(None, ("四方城", 35, 44)) == "未知"
    assert (
        classify_motion(("四方城", 34, 44), ("四方城", 34, 44), playfield_ratio=0.0)
        == "静止候选"
    )
    assert (
        classify_motion(("四方城", 34, 44), ("四方城", 34, 44), playfield_ratio=0.01)
        == "同格运动候选"
    )
    assert (
        classify_motion(("四方城", 34, 44), ("四方城", 35, 44), playfield_ratio=0.01)
        == "移动"
    )
    assert (
        classify_motion(
            ("四方城", 34, 44),
            ("四方城", 34, 44),
            playfield_ratio=0.0,
            right_edge_ratio=0.05,
        )
        == "画面未刷新"
    )
    assert (
        classify_motion(None, None, playfield_ratio=0.0, right_edge_ratio=0.05)
        == "画面未刷新"
    )


def test_image_diff_detects_identical_and_changed_images():
    first = Image.new("RGB", (4, 4), 0)
    same = Image.new("RGB", (4, 4), 0)
    changed = Image.new("RGB", (4, 4), 0)
    changed.putpixel((2, 1), (255, 255, 255))

    assert image_diff(first, same).changed_pixels == 0
    result = image_diff(first, changed)
    assert result.changed_pixels == 1
    assert result.bbox == (2, 1, 3, 2)
    assert result.centroid == (2.0, 1.0)
