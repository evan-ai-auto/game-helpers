"""命魂任务检测用的图像转换与模板匹配。"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from ..capture.models import Frame
from .soul_task_models import SoulTaskUiProfile


def as_pil_image(image: Image.Image | Frame) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, Frame):
        expected = image.width * image.height * 4
        if len(image.data) != expected:
            raise ValueError("invalid Frame BGRA payload")
        return Image.frombytes(
            "RGBA", (image.width, image.height), image.data, "raw", "BGRA"
        ).convert("RGB")
    raise TypeError(f"unsupported image type: {type(image).__name__}")


def resolve_template_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    cwd_candidate = Path.cwd() / candidate
    if cwd_candidate.is_file():
        return cwd_candidate
    repo_candidate = Path(__file__).resolve().parents[3] / candidate
    if repo_candidate.is_file():
        return repo_candidate
    return cwd_candidate


def load_template(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load a PNG template as RGB + normalized alpha mask."""
    resolved = resolve_template_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    with Image.open(resolved) as image:
        rgba = image.convert("RGBA")
    return (
        np.asarray(rgba, dtype=np.float32)[..., :3],
        np.asarray(rgba, dtype=np.float32)[..., 3] / 255.0,
    )


def load_claimed_icon_template(path: str | Path) -> np.ndarray:
    resolved = resolve_template_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    raw_json = json.loads(resolved.read_text(encoding="utf-8"))
    payload = raw_json
    if isinstance(payload, dict) and isinstance(payload.get("content"), str):
        try:
            payload = json.loads(payload["content"])
        except json.JSONDecodeError:
            pass
    if not isinstance(payload, dict) or "template_base64" not in payload:
        raise ValueError("template_base64 missing")
    raw = base64.b64decode(payload["template_base64"], validate=True)
    return np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=np.float32)


def ncc(roi: np.ndarray, template: np.ndarray) -> tuple[float, tuple[int, int] | None]:
    h, w = template.shape[:2]
    rh, rw = roi.shape[:2]
    if rh < h or rw < w:
        return 0.0, None
    t_gray = 0.299 * template[..., 0] + 0.587 * template[..., 1] + 0.114 * template[..., 2]
    t_gray = t_gray - t_gray.mean()
    t_norm = float(np.sqrt((t_gray * t_gray).sum()))
    if t_norm <= 1e-6:
        return 0.0, None
    roi_gray = 0.299 * roi[..., 0] + 0.587 * roi[..., 1] + 0.114 * roi[..., 2]
    best, best_xy = -1.0, None
    for y in range(rh - h + 1):
        for x in range(rw - w + 1):
            patch = roi_gray[y:y + h, x:x + w]
            p = patch - patch.mean()
            denom = float(np.sqrt((p * p).sum()) * t_norm)
            if denom <= 1e-6:
                continue
            score = float((p * t_gray).sum() / denom)
            if score > best:
                best, best_xy = score, (x, y)
    return best, best_xy


def masked_match(
    roi: np.ndarray,
    template_rgb: np.ndarray,
    alpha: np.ndarray,
) -> tuple[float, tuple[int, int] | None]:
    """Color similarity that ignores transparent template pixels."""
    h, w = template_rgb.shape[:2]
    rh, rw = roi.shape[:2]
    if rh < h or rw < w:
        return 0.0, None
    weights = np.asarray(alpha, dtype=np.float32)
    if weights.shape != (h, w) or float(weights.sum()) <= 1e-6:
        return 0.0, None
    weight_sum = float(weights.sum())
    best_score, best_xy = 0.0, None
    for y in range(rh - h + 1):
        for x in range(rw - w + 1):
            patch = roi[y:y + h, x:x + w]
            error = float(
                (np.abs(patch - template_rgb).mean(axis=2) * weights).sum()
                / weight_sum
            )
            score = max(0.0, 1.0 - error / 255.0)
            if score > best_score:
                best_score, best_xy = score, (x, y)
    return best_score, best_xy


def toggle_templates(profile: SoulTaskUiProfile) -> tuple[tuple[str, str, bool], ...]:
    return (
        ("right_light", profile.toggle_right_light_template_path, True),
        ("right_gray", profile.toggle_right_gray_template_path, True),
        ("left_light", profile.toggle_left_light_template_path, False),
    )
