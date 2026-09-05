"""Generic visual state detection from user-provided feature assets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from ..capture.models import Frame


class VisualStateStatus(str):
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    INVALID = "invalid"


class VisualPositionType(str):
    """Spatial behavior declared by a visual asset."""

    FIXED = "fixed"
    FLOATING = "floating"


@dataclass(frozen=True)
class VisualAnchor:
    name: str
    image_path: Path
    offset_x: int = 0
    offset_y: int = 0
    threshold: float = 0.92
    search_step: int = 1
    position_type: str = VisualPositionType.FLOATING
    expected_x: float | None = None
    expected_y: float | None = None
    position_tolerance: int = 12


@dataclass(frozen=True)
class VisualStateProfile:
    name: str
    anchors: tuple[VisualAnchor, ...]
    consecutive_frames: int = 2


@dataclass(frozen=True)
class VisualStateObservation:
    state: str
    status: str
    confidence: float
    origin: tuple[int, int] | None = None
    anchor_scores: tuple[tuple[str, float], ...] = ()
    evidence: tuple[str, ...] = ()

    @property
    def detected(self) -> bool:
        return self.status == VisualStateStatus.DETECTED


def _frame_gray(frame: Frame) -> np.ndarray:
    expected = frame.width * frame.height * 4
    if frame.width <= 0 or frame.height <= 0 or len(frame.data) != expected:
        raise ValueError("invalid Frame")
    bgra = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 4)
    b, g, r = bgra[..., 0].astype(np.float32), bgra[..., 1].astype(np.float32), bgra[..., 2].astype(np.float32)
    return (0.114 * b + 0.587 * g + 0.299 * r).astype(np.float32)


def _template_gray(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)


def _integral(array: np.ndarray) -> np.ndarray:
    return np.pad(array.cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def _window_sum(integral: np.ndarray, height: int, width: int) -> np.ndarray:
    return integral[height:, width:] - integral[:-height, width:] - integral[height:, :-width] + integral[:-height, :-width]


def _ncc_map(image: np.ndarray, template: np.ndarray, step: int = 1) -> np.ndarray:
    h, w = template.shape
    H, W = image.shape
    if h > H or w > W:
        return np.empty((0, 0), dtype=np.float32)
    shape = (H + h - 1, W + w - 1)
    corr = np.fft.irfftn(np.fft.rfftn(image, shape) * np.conj(np.fft.rfftn(template, shape)), shape).real[: H - h + 1, : W - w + 1]
    n = float(h * w)
    t_mean = float(template.mean())
    t_energy = float(np.sum((template - t_mean) ** 2))
    if t_energy <= 1e-8:
        raise ValueError("template has no variance")
    ii = _integral(image)
    ii2 = _integral(image * image)
    sums = _window_sum(ii, h, w)
    sums2 = _window_sum(ii2, h, w)
    numerator = corr - sums * t_mean
    denominator = np.sqrt(np.maximum((sums2 - (sums * sums) / n) * t_energy, 1e-8))
    result = numerator / denominator
    return result[::step, ::step].astype(np.float32) if step > 1 else result.astype(np.float32)


def _load_profile(path: str | Path) -> VisualStateProfile:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    anchors = tuple(
        VisualAnchor(
            name=item["name"],
            image_path=(base / item["image"]).resolve(),
            offset_x=int(item.get("offset_x", 0)),
            offset_y=int(item.get("offset_y", 0)),
            threshold=float(item.get("threshold", 0.92)),
            search_step=max(1, int(item.get("search_step", 1))),
            position_type=str(item.get("position_type", VisualPositionType.FLOATING)),
            expected_x=(float(item["expected_x"]) if item.get("expected_x") is not None else None),
            expected_y=(float(item["expected_y"]) if item.get("expected_y") is not None else None),
            position_tolerance=max(0, int(item.get("position_tolerance", 12))),
        )
        for item in payload["anchors"]
    )
    if not anchors:
        raise ValueError("visual state profile has no anchors")
    for anchor in anchors:
        if anchor.position_type not in (VisualPositionType.FIXED, VisualPositionType.FLOATING):
            raise ValueError(f"unsupported position_type: {anchor.position_type}")
        if anchor.position_type == VisualPositionType.FIXED and (
            anchor.expected_x is None
            or anchor.expected_y is None
            or not 0.0 <= anchor.expected_x <= 1.0
            or not 0.0 <= anchor.expected_y <= 1.0
        ):
            raise ValueError(f"fixed anchor {anchor.name} requires normalized expected_x/expected_y")
    return VisualStateProfile(str(payload["name"]), anchors, max(1, int(payload.get("consecutive_frames", 2))))


def _candidate_origins(image: np.ndarray, anchor: VisualAnchor, scores: np.ndarray) -> list[tuple[int, int, float]]:
    """Return candidate template origins according to the anchor's position contract."""
    h, w = image.shape
    th, tw = _template_gray(anchor.image_path).shape
    if scores.size == 0:
        return []
    if anchor.position_type == VisualPositionType.FLOATING:
        ys, xs = np.where(scores >= anchor.threshold)
        return [(int(x * anchor.search_step), int(y * anchor.search_step), float(scores[y, x])) for y, x in zip(ys, xs)]

    assert anchor.expected_x is not None and anchor.expected_y is not None
    expected_x = int(round(anchor.expected_x * w))
    expected_y = int(round(anchor.expected_y * h))
    # expected_x/y refer to the template origin. Search a bounded pixel window around it.
    x0 = max(0, expected_x - anchor.position_tolerance)
    x1 = min(w - tw, expected_x + anchor.position_tolerance)
    y0 = max(0, expected_y - anchor.position_tolerance)
    y1 = min(h - th, expected_y + anchor.position_tolerance)
    if x1 < x0 or y1 < y0:
        return []
    sx0, sx1 = x0 // anchor.search_step, x1 // anchor.search_step
    sy0, sy1 = y0 // anchor.search_step, y1 // anchor.search_step
    window = scores[sy0 : sy1 + 1, sx0 : sx1 + 1]
    if window.size == 0:
        return []
    local_y, local_x = np.unravel_index(int(np.argmax(window)), window.shape)
    score = float(window[local_y, local_x])
    if score < anchor.threshold:
        return []
    return [(int((sx0 + local_x) * anchor.search_step), int((sy0 + local_y) * anchor.search_step), score)]


def detect_visual_state(frame: Frame, profile: VisualStateProfile) -> VisualStateObservation:
    """Detect a composite visual state while honoring each anchor's position contract."""
    try:
        image = _frame_gray(frame)
        loaded = [(anchor, _template_gray(anchor.image_path)) for anchor in profile.anchors]
        matches = [(anchor, template, _ncc_map(image, template, anchor.search_step)) for anchor, template in loaded]
        base, base_template, base_scores = matches[0]
        candidates = _candidate_origins(image, base, base_scores)
        if not candidates:
            return VisualStateObservation(profile.name, VisualStateStatus.NOT_DETECTED, float(base_scores.max()) if base_scores.size else 0.0, evidence=(f"anchor {base.name} not found",))
        candidates.sort(key=lambda item: item[2], reverse=True)
        for bx, by, base_score in candidates[:64]:
            scores_for_origin = [(base.name, base_score)]
            valid = True
            for anchor, _template, scores in matches[1:]:
                if anchor.position_type == VisualPositionType.FIXED:
                    anchor_candidates = _candidate_origins(image, anchor, scores)
                    if not anchor_candidates:
                        valid = False
                        break
                    ax, ay, score = anchor_candidates[0]
                    scores_for_origin.append((anchor.name, score))
                    continue
                ax = bx + anchor.offset_x - base.offset_x
                ay = by + anchor.offset_y - base.offset_y
                sx, sy = ax // anchor.search_step, ay // anchor.search_step
                if sx < 0 or sy < 0 or sy >= scores.shape[0] or sx >= scores.shape[1]:
                    valid = False
                    break
                score = float(scores[sy, sx])
                scores_for_origin.append((anchor.name, score))
                if score < anchor.threshold:
                    valid = False
                    break
            if valid:
                return VisualStateObservation(profile.name, VisualStateStatus.DETECTED, min(s for _, s in scores_for_origin), (bx - base.offset_x, by - base.offset_y), tuple(scores_for_origin), ("all required anchors matched",))
        return VisualStateObservation(profile.name, VisualStateStatus.NOT_DETECTED, float(base_scores.max()), evidence=("required anchors did not satisfy their position contracts",))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return VisualStateObservation(profile.name, VisualStateStatus.INVALID, 0.0, evidence=(str(exc),))


def load_visual_state(path: str | Path) -> VisualStateProfile:
    return _load_profile(path)


def make_visual_state_verifier(capture: Callable[[], Frame], profile: VisualStateProfile) -> Callable[[], VisualStateObservation | None]:
    """Return a stateful verifier requiring consecutive positive frames."""
    consecutive = 0

    def verify() -> VisualStateObservation | None:
        nonlocal consecutive
        observation = detect_visual_state(capture(), profile)
        if observation.detected:
            consecutive += 1
            if consecutive >= profile.consecutive_frames:
                return observation
        else:
            consecutive = 0
        return None

    return verify
