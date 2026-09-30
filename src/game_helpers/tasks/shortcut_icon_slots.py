"""Geometric Shortcut expanded-icon slots for evidence and multi-target matching."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ..capture.models import Frame
from .soul_task_match import (
    as_pil_image,
    load_claimed_icon_template,
    load_template,
    masked_match,
    ncc,
    resolve_template_path,
)
from .ui_icon_targets import ICON_DETECT_TARGETS, IconDetectTarget

# 800×600 floating shortcut icons under 指引.
# Anchored so row2/col2 covers historical 命魂 hit ~(67,145). Live overlays showed
# the previous seed sitting slightly low/right; nudge origin up-left and use a
# 32px crop for a bit more glyph padding.
SHORTCUT_ICON_SLOT_ORIGIN = (34, 99)
SHORTCUT_ICON_SLOT_CELL = (31, 43)
SHORTCUT_ICON_SLOT_SIZE = (32, 32)
SHORTCUT_ICON_SLOT_COLS = 3
SHORTCUT_ICON_SLOT_ROWS = 2
SHORTCUT_ICON_SLOT_REFINE_PAD = 6


@dataclass(frozen=True)
class ShortcutIconSlotObservation:
    index: int
    row: int
    col: int
    client_rect: tuple[int, int, int, int]
    seed_rect: tuple[int, int, int, int]
    center: tuple[int, int]
    best_target_id: str | None
    best_target_name: str | None
    best_score: float
    artifact_name: str


def iter_shortcut_icon_slot_rects(
    *,
    origin: tuple[int, int] = SHORTCUT_ICON_SLOT_ORIGIN,
    cell: tuple[int, int] = SHORTCUT_ICON_SLOT_CELL,
    size: tuple[int, int] = SHORTCUT_ICON_SLOT_SIZE,
    cols: int = SHORTCUT_ICON_SLOT_COLS,
    rows: int = SHORTCUT_ICON_SLOT_ROWS,
) -> tuple[tuple[int, int, tuple[int, int, int, int], tuple[int, int]], ...]:
    """Yield (row, col, client_rect, center) with 1-based row/col."""
    items: list[tuple[int, int, tuple[int, int, int, int], tuple[int, int]]] = []
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            left = origin[0] + (col - 1) * cell[0]
            top = origin[1] + (row - 1) * cell[1]
            right = left + size[0]
            bottom = top + size[1]
            center = (left + size[0] // 2, top + size[1] // 2)
            items.append((row, col, (left, top, right, bottom), center))
    return tuple(items)


def _iconness_score(patch: np.ndarray) -> float:
    """Prefer compact colorful UI glyphs; penalize beige stall-label patches."""
    if patch.size == 0:
        return -1.0
    chroma = patch.max(axis=2) - patch.min(axis=2)
    lum = 0.299 * patch[..., 0] + 0.587 * patch[..., 1] + 0.114 * patch[..., 2]
    # Beige stall labels: high luminance, moderate chroma, flat texture.
    beige = (lum >= 160) & (lum <= 230) & (chroma >= 15) & (chroma <= 70)
    colorful = chroma >= 40
    score = float(colorful.mean()) - 0.55 * float(beige.mean())
    # Prefer some structure (not flat ground).
    gx = np.abs(np.diff(lum, axis=1)).mean() if lum.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(lum, axis=0)).mean() if lum.shape[0] > 1 else 0.0
    score += 0.002 * float(gx + gy)
    return score


def _score_target_in_slot(slot_rgb: np.ndarray, target: IconDetectTarget) -> float:
    path = resolve_template_path(target.template_path)
    if not path.is_file():
        return 0.0
    try:
        if target.matcher == "claimed_json":
            template = load_claimed_icon_template(path)
            score, _ = ncc(slot_rgb, template)
            return float(score)
        if target.matcher == "masked_png":
            template_rgb, alpha = load_template(path)
            score, _ = masked_match(slot_rgb, template_rgb, alpha)
            return float(score)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return 0.0
    return 0.0


def refine_slot_rect(
    image: Image.Image,
    seed: tuple[int, int, int, int],
    *,
    targets: tuple[IconDetectTarget, ...] = (),
    pad: int = SHORTCUT_ICON_SLOT_REFINE_PAD,
) -> tuple[int, int, int, int]:
    """Snap seed rect within ±pad using registered-target score (fallback: iconness)."""
    left, top, right, bottom = seed
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return seed
    rgb = np.asarray(image, dtype=np.float32)
    best = seed
    best_score = -1e9
    for dy in range(-pad, pad + 1):
        for dx in range(-pad, pad + 1):
            l = left + dx
            t = top + dy
            r = l + width
            b = t + height
            if l < 0 or t < 0 or r > image.width or b > image.height:
                continue
            patch = rgb[t:b, l:r]
            if targets:
                score = max((_score_target_in_slot(patch, target) for target in targets), default=0.0)
                # Prefer staying near seed when target evidence is weak (stall clutter).
                if score < 0.45:
                    score = 0.25 * score + 0.75 * _iconness_score(patch) - 0.01 * (abs(dx) + abs(dy))
            else:
                score = _iconness_score(patch)
            if score > best_score:
                best_score = score
                best = (l, t, r, b)
    return best


def extract_shortcut_icon_slots(
    image: Image.Image | Frame,
    *,
    targets: tuple[IconDetectTarget, ...] = ICON_DETECT_TARGETS,
    refine: bool = True,
) -> tuple[ShortcutIconSlotObservation, ...]:
    """Crop geometric slots (optionally locally refined) and score registered targets."""
    image = as_pil_image(image).convert("RGB")
    observations: list[ShortcutIconSlotObservation] = []
    for index, (row, col, seed, _center) in enumerate(iter_shortcut_icon_slot_rects(), start=1):
        rect = refine_slot_rect(image, seed, targets=targets) if refine else seed
        left, top, right, bottom = rect
        left = max(0, left)
        top = max(0, top)
        right = min(image.width, right)
        bottom = min(image.height, bottom)
        rect = (left, top, right, bottom)
        crop = image.crop(rect)
        slot_rgb = np.asarray(crop, dtype=np.float32)
        best_id = None
        best_name = None
        best_score = 0.0
        for target in targets:
            score = _score_target_in_slot(slot_rgb, target)
            if score > best_score:
                best_score = score
                best_id = target.id
                best_name = target.name
        if best_score < 0.60:
            best_id = None
            best_name = None
        artifact = f"slot-{index:02d}-r{row}c{col}.png"
        center = ((left + right) // 2, (top + bottom) // 2)
        observations.append(
            ShortcutIconSlotObservation(
                index=index,
                row=row,
                col=col,
                client_rect=rect,
                seed_rect=seed,
                center=center,
                best_target_id=best_id,
                best_target_name=best_name,
                best_score=float(best_score),
                artifact_name=artifact,
            )
        )
    return tuple(observations)


def write_shortcut_icon_slot_artifacts(
    image: Image.Image | Frame,
    output_dir: str | Path,
    *,
    targets: tuple[IconDetectTarget, ...] = ICON_DETECT_TARGETS,
) -> tuple[ShortcutIconSlotObservation, ...]:
    """Write per-slot crops + JSON list under output_dir/shortcut-icon-slots/."""
    image = as_pil_image(image).convert("RGB")
    slots_dir = Path(output_dir) / "shortcut-icon-slots"
    slots_dir.mkdir(parents=True, exist_ok=True)
    observations = extract_shortcut_icon_slots(image, targets=targets)
    for obs in observations:
        left, top, right, bottom = obs.client_rect
        image.crop((left, top, right, bottom)).save(slots_dir / obs.artifact_name)
    payload = {
        "slot_count": len(observations),
        "grid": {
            "origin": list(SHORTCUT_ICON_SLOT_ORIGIN),
            "cell": list(SHORTCUT_ICON_SLOT_CELL),
            "size": list(SHORTCUT_ICON_SLOT_SIZE),
            "cols": SHORTCUT_ICON_SLOT_COLS,
            "rows": SHORTCUT_ICON_SLOT_ROWS,
            "refine_pad": SHORTCUT_ICON_SLOT_REFINE_PAD,
        },
        "slots": [
            {
                **asdict(obs),
                "client_rect": list(obs.client_rect),
                "seed_rect": list(obs.seed_rect),
                "center": list(obs.center),
                "artifact": f"shortcut-icon-slots/{obs.artifact_name}",
            }
            for obs in observations
        ],
    }
    (slots_dir / "slots.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return observations


__all__ = [
    "SHORTCUT_ICON_SLOT_CELL",
    "SHORTCUT_ICON_SLOT_COLS",
    "SHORTCUT_ICON_SLOT_ORIGIN",
    "SHORTCUT_ICON_SLOT_REFINE_PAD",
    "SHORTCUT_ICON_SLOT_ROWS",
    "SHORTCUT_ICON_SLOT_SIZE",
    "ShortcutIconSlotObservation",
    "extract_shortcut_icon_slots",
    "iter_shortcut_icon_slot_rects",
    "refine_slot_rect",
    "write_shortcut_icon_slot_artifacts",
]
