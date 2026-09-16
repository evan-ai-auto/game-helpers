"""Verify Soul Task claimed templates with independent searches and diagnostics."""
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
    rgb_score = 1.0 - float((rgb_error * weights).sum()) / total / 255.0

    patch_gray = gray(patch)
    template_gray = gray(template.rgb)
    patch_norm = (patch_gray - patch_gray.mean()) / (patch_gray.std() + 1e-6)
    template_norm = (template_gray - template_gray.mean()) / (template_gray.std() + 1e-6)
    structure_score = 1.0 - float(
        (np.abs(patch_norm - template_norm) * weights).sum()
    ) / total / 4.0

    # Both edge maps use the same raw grayscale scale.
    patch_edge = edges(patch_gray)
    template_edge = edges(template_gray)
    edge_scale = max(float(template_edge.max()), 1.0)
    edge_score = 1.0 - float(
        (np.abs(patch_edge - template_edge) / edge_scale * weights).sum()
    ) / total

    return float(0.45 * rgb_score + 0.30 * structure_score + 0.25 * edge_score)


def find_best(
    frame: np.ndarray,
    template: Template,
    roi: tuple[int, int, int, int],
    center: tuple[int, int] | None = None,
    radius: int | None = None,
) -> tuple[float, tuple[int, int] | None]:
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

    best_score = -float("inf")
    best_xy: tuple[int, int] | None = None
    for y in range(region.shape[0] - th + 1):
        for x in range(region.shape[1] - tw + 1):
            value = score(region[y:y + th, x:x + tw], template)
            if value > best_score:
                best_score, best_xy = value, (x0 + x, y0 + y)

    if best_xy is None or not np.isfinite(best_score):
        return 0.0, None
    return max(0.0, float(best_score)), best_xy


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

    paths = [args.screenshot, args.template1, args.template3]
    if any(not path.is_file() for path in paths):
        print("ERROR screenshot or template not found")
        return 2

    try:
        image = Image.open(args.screenshot).convert("RGB")
        frame = np.asarray(image, dtype=np.float32)
        template1 = load_template(args.template1)
        template3 = load_template(args.template3)
    except (OSError, ValueError) as exc:
        print(f"ERROR unable to load image/template: {exc}")
        return 2

    # Search both templates independently. Do not assume they share the same origin.
    template1_score, template1_xy = find_best(frame, template1, tuple(args.roi))
    template3_score, template3_xy = find_best(frame, template3, tuple(args.roi))

    offset = None
    if template1_xy is not None and template3_xy is not None:
        offset = float(np.hypot(template1_xy[0] - template3_xy[0], template1_xy[1] - template3_xy[1]))

    combined = 0.65 * template1_score + 0.35 * template3_score
    passed = (
        template1_xy is not None
        and template3_xy is not None
        and template1_score >= args.threshold
        and template3_score >= args.threshold
    )
    status = "PASS" if passed else ("UNKNOWN" if template1_score >= args.threshold else "FAIL")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"screenshot={args.screenshot}",
        f"template1={args.template1}",
        f"template3={args.template3}",
        f"screenshot_size={image.width}x{image.height}",
        f"roi={tuple(args.roi)}",
        f"threshold={args.threshold:.4f}",
        f"template1_score={template1_score:.4f}",
        f"template1_match_location={template1_xy}",
        f"template3_score={template3_score:.4f}",
        f"template3_match_location={template3_xy}",
        f"location_offset={offset}",
        f"combined_score={combined:.4f}",
        f"RESULT={status}",
    ]

    if template1_xy is not None:
        x, y = template1_xy
        tw, th = template1.rgb.shape[1], template1.rgb.shape[0]
        crop = args.output_dir / f"{args.screenshot.stem}_template1_crop.png"
        image.crop((x, y, x + tw, y + th)).save(crop)
        lines.append(f"template1_crop={crop}")

    if template3_xy is not None:
        x, y = template3_xy
        tw, th = template3.rgb.shape[1], template3.rgb.shape[0]
        crop = args.output_dir / f"{args.screenshot.stem}_template3_crop.png"
        image.crop((x, y, x + tw, y + th)).save(crop)
        lines.append(f"template3_crop={crop}")

    report = args.output_dir / f"{args.screenshot.stem}.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
