"""Independent verifier for the unclaimed Soul Task icon template.

This tool deliberately does not import the production SoulTask detector. It scans
a runtime screenshot, finds the best template match inside a configurable ROI,
and saves the exact runtime patch at the winning location for visual inspection.

Example:
    python tools/verify_soul_task_unclaimed_template.py diagnostic/soul_task/character-2.png

Exit codes:
    0 = match score reached threshold
    1 = screenshot loaded, but no reliable match
    2 = invalid input/template
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


DEFAULT_TEMPLATE = Path("data/assets/ui/soul_task_unclaimed_icon.png")
DEFAULT_ROI = (0, 0, 272, 252)


def load_template(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with Image.open(path) as image:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    return rgba[..., :3], rgba[..., 3] / 255.0


def masked_mae_score(
    patch: np.ndarray,
    template_rgb: np.ndarray,
    alpha: np.ndarray,
) -> float:
    weights = alpha[..., None]
    denom = float(alpha.sum()) * 255.0
    if denom <= 1e-6:
        return 0.0
    error = np.abs(patch - template_rgb) * weights
    return max(0.0, 1.0 - float(error.sum()) / denom)


def find_best_match(
    image: Image.Image,
    template_rgb: np.ndarray,
    alpha: np.ndarray,
    roi: tuple[int, int, int, int],
) -> tuple[float, tuple[int, int] | None]:
    frame = np.asarray(image.convert("RGB"), dtype=np.float32)
    x0, y0, x1, y1 = roi
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(frame.shape[1], x1)
    y1 = min(frame.shape[0], y1)
    region = frame[y0:y1, x0:x1]

    th, tw = template_rgb.shape[:2]
    rh, rw = region.shape[:2]
    if rh < th or rw < tw:
        return 0.0, None

    best_score = 0.0
    best_xy: tuple[int, int] | None = None

    # Scan row-by-row so memory stays bounded. The standalone verifier is
    # intentionally simple and dependency-free; production code is not imported.
    for y in range(rh - th + 1):
        for x in range(rw - tw + 1):
            score = masked_mae_score(
                region[y:y + th, x:x + tw],
                template_rgb,
                alpha,
            )
            if score > best_score:
                best_score = score
                best_xy = (x0 + x, y0 + y)

    return best_score, best_xy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument(
        "--roi",
        nargs=4,
        type=int,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        default=DEFAULT_ROI,
        help="scan region in screenshot pixels; defaults to the 800x600 task area",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.82,
        help="minimum masked similarity required for PASS",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("diagnostic/soul_task/template_verify"),
    )
    args = parser.parse_args()

    if not args.screenshot.is_file():
        print(f"ERROR screenshot not found: {args.screenshot}")
        return 2
    if not args.template.is_file():
        print(f"ERROR template not found: {args.template}")
        return 2

    try:
        image = Image.open(args.screenshot).convert("RGB")
        template_rgb, alpha = load_template(args.template)
    except (OSError, ValueError) as exc:
        print(f"ERROR unable to load image/template: {exc}")
        return 2

    score, location = find_best_match(
        image,
        template_rgb,
        alpha,
        tuple(args.roi),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = args.output_dir / f"{args.screenshot.stem}.txt"

    lines = [
        f"screenshot={args.screenshot}",
        f"template={args.template}",
        f"screenshot_size={image.width}x{image.height}",
        f"template_size={template_rgb.shape[1]}x{template_rgb.shape[0]}",
        f"roi={tuple(args.roi)}",
        f"best_score={score:.4f}",
        f"threshold={args.threshold:.4f}",
        f"match_location={location}",
    ]

    if location is not None:
        x, y = location
        crop = image.crop(
            (x, y, x + template_rgb.shape[1], y + template_rgb.shape[0])
        )
        crop_path = args.output_dir / f"{args.screenshot.stem}_matched_crop.png"
        crop.save(crop_path)
        lines.append(f"matched_crop={crop_path}")

    passed = location is not None and score >= args.threshold
    lines.append(f"RESULT={'PASS' if passed else 'FAIL'}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
