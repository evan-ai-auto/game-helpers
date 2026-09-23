"""打开道具栏并扫描摄妖香所在格子。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .item_panel_flow import ItemPanelFlowNoop, run_item_panel_detect_and_toggle
from .soul_task_match import as_pil_image, load_template, masked_match, resolve_template_path
from .verification_session import VerificationSession

INCENSE_ITEM_TEMPLATE_PATH = "data/assets/ui/resolutions/800x600/incense_item_icon.png"

# Provisional 800x600 bag grid (calibrate against real open panel).
ITEM_GRID_ORIGIN = (425, 95)
ITEM_GRID_CELL = (51, 51)
ITEM_GRID_COLS = 5
ITEM_GRID_ROWS = 4
ITEM_MATCH_THRESHOLD = 0.78


@dataclass(frozen=True)
class IncenseInventoryObservation:
    status: str  # found | not_found | asset_missing | panel_not_open | skipped
    present: bool | None
    row: int | None  # 1-based
    col: int | None  # 1-based
    click_client: tuple[int, int] | None
    match_score: float
    slot_crop_path: str | None
    evidence: tuple[str, ...]


def slot_index_from_match(
    match_top_left: tuple[int, int],
    *,
    origin: tuple[int, int] = ITEM_GRID_ORIGIN,
    cell: tuple[int, int] = ITEM_GRID_CELL,
    cols: int = ITEM_GRID_COLS,
    rows: int = ITEM_GRID_ROWS,
) -> tuple[int, int, tuple[int, int]]:
    """Return 1-based (row, col) and click center for a match top-left."""
    rel_x = match_top_left[0] - origin[0]
    rel_y = match_top_left[1] - origin[1]
    col = int(round(rel_x / cell[0])) + 1
    row = int(round(rel_y / cell[1])) + 1
    col = min(max(col, 1), cols)
    row = min(max(row, 1), rows)
    center = (
        origin[0] + (col - 1) * cell[0] + cell[0] // 2,
        origin[1] + (row - 1) * cell[1] + cell[1] // 2,
    )
    return row, col, center


def _scan_incense_in_image(image: Image.Image, output: Path) -> IncenseInventoryObservation:
    template_path = resolve_template_path(INCENSE_ITEM_TEMPLATE_PATH)
    if not template_path.is_file():
        return IncenseInventoryObservation(
            "asset_missing",
            None,
            None,
            None,
            None,
            0.0,
            None,
            (f"摄妖香道具模板缺失: {template_path}", f"请提供 {INCENSE_ITEM_TEMPLATE_PATH}"),
        )

    left, top = ITEM_GRID_ORIGIN
    right = left + ITEM_GRID_COLS * ITEM_GRID_CELL[0]
    bottom = top + ITEM_GRID_ROWS * ITEM_GRID_CELL[1]
    left, top = max(0, left), max(0, top)
    right, bottom = min(image.width, right), min(image.height, bottom)
    search = image.crop((left, top, right, bottom))
    search.save(output / "item-grid-roi.png")
    roi = np.asarray(search, dtype=np.float32)
    template_rgb, alpha = load_template(template_path)
    score, location = masked_match(roi, template_rgb, alpha)
    if location is None or score < ITEM_MATCH_THRESHOLD:
        return IncenseInventoryObservation(
            "not_found",
            False,
            None,
            None,
            None,
            float(max(0.0, score)),
            None,
            (f"未在道具栏匹配到摄妖香；best_score={score:.3f}",),
        )

    abs_tl = (left + location[0], top + location[1])
    row, col, click = slot_index_from_match(abs_tl)
    th, tw = template_rgb.shape[0], template_rgb.shape[1]
    crop_box = (abs_tl[0], abs_tl[1], abs_tl[0] + tw, abs_tl[1] + th)
    crop_path = output / "incense-slot-crop.png"
    image.crop(crop_box).save(crop_path)
    return IncenseInventoryObservation(
        "found",
        True,
        row,
        col,
        click,
        float(score),
        str(crop_path),
        (
            f"found row={row} col={col} click={click} score={score:.3f}",
            f"slot_crop={crop_path}",
        ),
    )


def ensure_item_panel_open(
    parent_hwnd: int,
    selection,
    output_dir: Path,
):
    """Open item panel via existing dao_ju_lan implementation."""

    def _select_open(before) -> bool:
        if before.open:
            raise ItemPanelFlowNoop()
        return True

    return run_item_panel_detect_and_toggle(
        parent_hwnd,
        selection,
        output_dir=output_dir / "item_panel",
        target_selector=_select_open,
    )


def scan_incense_in_inventory(
    parent_hwnd: int,
    selection,
    session: VerificationSession,
    output_dir: str | Path,
    *,
    open_panel: bool = True,
) -> IncenseInventoryObservation:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    panel_ok: bool | None = None
    panel_message = ""
    if open_panel:
        panel_result = ensure_item_panel_open(parent_hwnd, selection, output)
        panel_ok = bool(panel_result.ok)
        panel_message = panel_result.message
        if panel_result.error == "cancelled":
            return IncenseInventoryObservation(
                "skipped",
                None,
                None,
                None,
                None,
                0.0,
                None,
                ("用户取消打开道具栏",),
            )
        after_open = panel_result.after.open if panel_result.after is not None else False
        if not after_open:
            return IncenseInventoryObservation(
                "panel_not_open",
                None,
                None,
                None,
                None,
                0.0,
                None,
                (f"打开道具栏失败: {panel_message}",),
            )

    image = as_pil_image(session.capture_frame()).convert("RGB")
    image.save(output / "inventory-capture.png")
    observation = _scan_incense_in_image(image, output)
    if panel_ok is not None:
        observation = IncenseInventoryObservation(
            status=observation.status,
            present=observation.present,
            row=observation.row,
            col=observation.col,
            click_client=observation.click_client,
            match_score=observation.match_score,
            slot_crop_path=observation.slot_crop_path,
            evidence=observation.evidence + (f"item_panel_ok={panel_ok}",),
        )
    return observation


__all__ = [
    "INCENSE_ITEM_TEMPLATE_PATH",
    "IncenseInventoryObservation",
    "scan_incense_in_inventory",
    "slot_index_from_match",
]
