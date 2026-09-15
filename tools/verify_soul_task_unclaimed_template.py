"""Verify a claimed Soul Task icon with a primary and local secondary template."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

DEFAULT_ROI = (0, 0, 272, 252)

@dataclass(frozen=True)
class Template:
    path: Path
    rgb: np.ndarray
    alpha: np.ndarray


def load_template(path: Path) -> Template:
    with Image.open(path) as image:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    return Template(path, rgba[..., :3], rgba[..., 3] / 255.0)


def gray(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def edges(value: np.ndarray) -> np.ndarray:
    gx = np.zeros_like(value)
    gy = np.zeros_like(value)
    gx[:, 1:-1] = value[:, 2:] - value[:, :-2]
    gy[1:-1, :] = value[2:, :] - value[:-2, :]
    return np.hypot(gx, gy)


def score(patch: np.ndarray, template: Template) -> float:
    weights = template.alpha
    total = float(weights.sum())
    if total <= 1e-6:
        return 0.0
    rgb_error = np.abs(patch - template.rgb).mean(axis=2)
    rgb = 1.0 - float((rgb_error * weights).sum()) / total / 255.0
    patch_gray = gray(patch)
    template_gray = gray(template.rgb)
    patch_gray = (patch_gray - patch_gray.mean()) / (patch_gray.std() + 1e-6)
    template_gray = (template_gray - template_gray.mean()) / (template_gray.std() + 1e-6)
    structure = 1.0 - float((np.abs(patch_gray - template_gray) * weights).sum()) / total / 4.0
    patch_edge = edges(gray(patch))
    template_edge = edges(template_gray)
    edge_scale = max(float(template_edge.max()), 1.0)
    edge_score = 1.0 - float((np.abs(patch_edge - template_edge) / edge_scale * weights).sum()) / total
    return float(np.clip(0.45 * rgb + 0.30 * structure + 0.25 * edge_score, 0.0, 1.0))


def find_best(frame: np.ndarray, template: Template, roi: tuple[int, int, int, int], center: tuple[int, int] | None = None, radius: int | None = None):
    x0, y0, x1, y1 = roi
    if center is not None and radius is not None:
        x0, y0 = max(x0, center[0] - radius), max(y0, center[1] - radius)
        x1, y1 = min(x1, center[0] + radius + 1), min(y1, center[1] + radius + 1)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
    region = frame[y0:y1, x0:x1]
    th, tw = template.rgb.shape[:2]
    if region.shape[0] < th or region.shape[1] < tw:
        return 0.0, None
    best = (-1.0, None)
    for y in range(region.shape[0] - th + 1):
        for x in range(region.shape[1] - tw + 1):
            value = score(region[y:y + th, x:x + tw], template)
            if value > best[0]:
                best = (value, (x0 + x, y0 + y))
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("template1", type=Path)
    parser.add_argument("template3", type=Path)
    parser.add_argument("--roi", nargs=4, type=int, default=DEFAULT_ROI)
    parser.add_argument("--threshold", type=float, default=0.82)
    parser.add_argument("--local-radius", type=int, default=18)
    parser.add_argument("--output-dir", type=Path, default=Path("diagnostic/soul_task/template_verify"))
    args = parser.parse_args()
    if not args.screenshot.is_file() or not args.template1.is_file() or not args.template3.is_file():
        print("ERROR screenshot or template not found")
        return 2
    try:
        image = Image.open(args.screenshot).convert("RGB")
        frame = np.asarray(image, dtype=np.float32)
        primary = load_template(args.template1)
        secondary = load_template(args.template3)
    except (OSError, ValueError) as exc:
        print(f"ERROR unable to load image/template: {exc}")
        return 2
    primary_score, primary_xy = find_best(frame, primary, tuple(args.roi))
    secondary_score, secondary_xy = find_best(frame, secondary, tuple(args.roi), primary_xy, args.local_radius) if primary_xy else (0.0, None)
    offset = None if not primary_xy or not secondary_xy else float(np.hypot(primary_xy[0] - secondary_xy[0], primary_xy[1] - secondary_xy[1]))
    combined = 0.65 * primary_score + 0.35 * secondary_score
    passed = primary_xy is not None and secondary_xy is not None and primary_score >= args.threshold and secondary_score >= args.threshold and offset <= args.local_radius
    status = "PASS" if passed else ("UNKNOWN" if primary_xy is not None and primary_score >= args.threshold else "FAIL")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"screenshot={args.screenshot}", f"template1={args.template1}", f"template3={args.template3}",
        f"screenshot_size={image.width}x{image.height}", f"roi={tuple(args.roi)}", f"threshold={args.threshold:.4f}",
        f"primary_score={primary_score:.4f}", f"primary_match_location={primary_xy}",
        f"secondary_local_score={secondary_score:.4f}", f"secondary_local_match_location={secondary_xy}",
        f"location_offset={offset}", f"combined_score={combined:.4f}", f"RESULT={status}",
    ]
    if primary_xy:
        x, y = primary_xy
        tw, th = primary.rgb.shape[1], primary.rgb.shape[0]
        crop = args.output_dir / f"{args.screenshot.stem}_primary_crop.png"
        image.crop((x, y, x + tw, y + th)).save(crop)
        lines.append(f"primary_crop={crop}")
    report = args.output_dir / f"{args.screenshot.stem}.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
