"""Independent verifier for claimed Soul Task icon templates.

The verifier accepts one or more transparent templates. It combines masked RGB,
greyscale structure, edge structure, and a soft location prior. The existing
threshold is intentionally unchanged; uncertain or conflicting matches remain
FAIL rather than being accepted by lowering the threshold.

Example:
    python -m tools.verify_soul_task_unclaimed_template \
        diagnostic/soul_task/character-2.png \
        data/assets/ui/soul_task_claimed_icon.json \
        data/assets/ui/soul_task_claimed_icon_full.png
"""
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


def _gray(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def _edges(gray: np.ndarray) -> np.ndarray:
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    return np.hypot(gx, gy)


def _masked_mae(patch: np.ndarray, template: Template) -> float:
    weights = template.alpha
    total = float(weights.sum())
    if total <= 1e-6:
        return 0.0
    error = np.abs(patch - template.rgb).mean(axis=2)
    return max(0.0, 1.0 - float((error * weights).sum()) / total / 255.0)


def _masked_structure(patch: np.ndarray, template: Template) -> float:
    weights = template.alpha
    total = float(weights.sum())
    if total <= 1e-6:
        return 0.0
    patch_gray = _gray(patch)
    template_gray = _gray(template.rgb)
    patch_gray = (patch_gray - patch_gray.mean()) / (patch_gray.std() + 1e-6)
    template_gray = (template_gray - template_gray.mean()) / (template_gray.std() + 1e-6)
    error = np.abs(patch_gray - template_gray)
    return max(0.0, 1.0 - float((error * weights).sum()) / total / 4.0)


def _masked_edges(patch: np.ndarray, template: Template) -> float:
    weights = template.alpha
    total = float(weights.sum())
    if total <= 1e-6:
        return 0.0
    patch_edge = _edges(_gray(patch))
    template_edge = _edges(_gray(template.rgb))
    scale = max(float(template_edge.max()), 1.0)
    error = np.abs(patch_edge - template_edge) / scale
    return max(0.0, 1.0 - float((error * weights).sum()) / total)


def _candidate_score(patch: np.ndarray, template: Template) -> float:
    # RGB remains useful, but it is no longer the only evidence. Structure and
    # edges are less sensitive to map texture and moderate colour changes.
    rgb = _masked_mae(patch, template)
    structure = _masked_structure(patch, template)
    edges = _masked_edges(patch, template)
    return 0.45 * rgb + 0.30 * structure + 0.25 * edges


def find_best_match(
    image: Image.Image,
    template: Template,
    roi: tuple[int, int, int, int],
    expected_xy: tuple[int, int] | None = None,
) -> tuple[float, tuple[int, int] | None]:
    frame = np.asarray(image.convert("RGB"), dtype=np.float32)
    x0, y0, x1, y1 = roi
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
    region = frame[y0:y1, x0:x1]
    th, tw = template.rgb.shape[:2]
    rh, rw = region.shape[:2]
    if rh < th or rw < tw:
        return 0.0, None

    best_score = -1.0
    best_xy = None
    for y in range(rh - th + 1):
        for x in range(rw - tw + 1):
            score = _candidate_score(region[y:y + th, x:x + tw], template)
            absolute = (x0 + x, y0 + y)
            if expected_xy is not None:
                distance = float(np.hypot(absolute[0] - expected_xy[0], absolute[1] - expected_xy[1]))
                score -= min(0.12, distance / 500.0)
            if score > best_score:
                best_score, best_xy = score, absolute
    return max(0.0, best_score), best_xy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("templates", type=Path, nargs="+")
    parser.add_argument("--roi", nargs=4, type=int, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"), default=DEFAULT_ROI)
    parser.add_argument("--threshold", type=float, default=0.82, help="minimum combined similarity required for PASS")
    parser.add_argument("--expected", nargs=2, type=int, metavar=("X", "Y"), help="optional soft prior for the icon top-left")
    parser.add_argument("--output-dir", type=Path, default=Path("diagnostic/soul_task/template_verify"))
    args = parser.parse_args()

    if not args.screenshot.is_file():
        print(f"ERROR screenshot not found: {args.screenshot}")
        return 2
    missing = [path for path in args.templates if not path.is_file()]
    if missing:
        print(f"ERROR template not found: {missing[0]}")
        return 2

    try:
        image = Image.open(args.screenshot).convert("RGB")
        templates = [load_template(path) for path in args.templates]
    except (OSError, ValueError) as exc:
        print(f"ERROR unable to load image/template: {exc}")
        return 2

    expected_xy = tuple(args.expected) if args.expected else None
    results = [find_best_match(image, template, tuple(args.roi), expected_xy) for template in templates]
    results.sort(key=lambda item: item[0], reverse=True)
    best_score, location = results[0]
    locations = [item[1] for item in results if item[1] is not None]
    consistent = len(locations) <= 1 or max(
        float(np.hypot(a[0] - b[0], a[1] - b[1])) for a in locations for b in locations
    ) <= 18.0
    passed = location is not None and best_score >= args.threshold and consistent

    args.output_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"screenshot={args.screenshot}",
        f"templates={','.join(str(path) for path in args.templates)}",
        f"screenshot_size={image.width}x{image.height}",
        f"roi={tuple(args.roi)}",
        f"threshold={args.threshold:.4f}",
        f"template_count={len(templates)}",
    ]
    for index, (score, match) in enumerate(results, start=1):
        lines.append(f"template_{index}_score={score:.4f}")
        lines.append(f"template_{index}_match_location={match}")
    lines.append(f"locations_consistent={consistent}")
    lines.append(f"best_score={best_score:.4f}")
    lines.append(f"match_location={location}")

    if location is not None:
        x, y = location
        tw = templates[0].rgb.shape[1]
        th = templates[0].rgb.shape[0]
        crop_path = args.output_dir / f"{args.screenshot.stem}_matched_crop.png"
        image.crop((x, y, x + tw, y + th)).save(crop_path)
        lines.append(f"matched_crop={crop_path}")

    lines.append(f"RESULT={'PASS' if passed else 'FAIL'}")
    report = args.output_dir / f"{args.screenshot.stem}.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
