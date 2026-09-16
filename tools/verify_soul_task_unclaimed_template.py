"""Verify Soul Task templates with configurable two-stage crops."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

DEFAULT_ROI = (0, 0, 272, 252)
DEFAULT_CROPS = ((0, 0, 272, 252), (10, 125, 125, 240))


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
    weight = template.alpha
    total = float(weight.sum())
    if total <= 1e-6:
        return 0.0

    rgb = 1.0 - float((np.abs(patch - template.rgb).mean(2) * weight).sum()) / total / 255.0
    patch_gray, template_gray = gray(patch), gray(template.rgb)
    patch_norm = (patch_gray - patch_gray.mean()) / (patch_gray.std() + 1e-6)
    template_norm = (template_gray - template_gray.mean()) / (template_gray.std() + 1e-6)
    structure = 1.0 - float((np.abs(patch_norm - template_norm) * weight).sum()) / total / 4.0
    patch_edges, template_edges = edges(patch_gray), edges(template_gray)
    edge_scale = max(float(template_edges.max()), 1.0)
    edge = 1.0 - float((np.abs(patch_edges - template_edges) / edge_scale * weight).sum()) / total
    return float(0.45 * rgb + 0.30 * structure + 0.25 * edge)


def find_best(frame: np.ndarray, template: Template, roi: tuple[int, int, int, int]):
    x0, y0, x1, y1 = roi
    region = frame[y0:y1, x0:x1]
    template_height, template_width = template.rgb.shape[:2]
    if region.shape[0] < template_height or region.shape[1] < template_width:
        return 0.0, None

    best, location = -float("inf"), None
    for y in range(region.shape[0] - template_height + 1):
        for x in range(region.shape[1] - template_width + 1):
            value = score(region[y:y + template_height, x:x + template_width], template)
            if value > best:
                best, location = value, (x0 + x, y0 + y)
    return max(0.0, float(best)), location


def parse_rect(value: str) -> tuple[int, int, int, int]:
    parts = tuple(int(item) for item in value.split(","))
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("rect must be x0,y0,x1,y1")
    x0, y0, x1, y1 = parts
    if x1 <= x0 or y1 <= y0:
        raise argparse.ArgumentTypeError("rect must have positive width and height")
    return parts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("template1", type=Path)
    parser.add_argument("template3", type=Path)
    parser.add_argument("--roi", type=parse_rect, default=DEFAULT_ROI)
    parser.add_argument("--crop", action="append", type=parse_rect, dest="crops", help="relative crop rect; repeat twice")
    parser.add_argument("--threshold", type=float, default=0.82)
    parser.add_argument("--output-dir", type=Path, default=Path("diagnostic/soul_task/template_verify"))
    args = parser.parse_args()

    paths = (args.screenshot, args.template1, args.template3)
    if any(not path.is_file() for path in paths):
        print("ERROR screenshot or template not found")
        return 2

    try:
        with Image.open(args.screenshot) as image:
            frame = np.asarray(image.convert("RGB"), dtype=np.float32)
        template1 = load_template(args.template1)
        template3 = load_template(args.template3)
    except (OSError, ValueError) as exc:
        print(f"ERROR unable to load image/template: {exc}")
        return 2

    crops = tuple(args.crops or DEFAULT_CROPS)
    if len(crops) != 2:
        print("ERROR exactly two --crop values are required")
        return 2

    results = []
    for index, rect in enumerate(crops, 1):
        # Each crop is relative to the original screenshot. Do not reuse the
        # previous crop as the source, otherwise crop 2 is cropped twice.
        x0, y0, x1, y1 = rect
        source = frame[y0:y1, x0:x1]
        if source.size == 0:
            print(f"ERROR empty crop {index}")
            return 2

        source_height, source_width = source.shape[:2]
        score1, location1 = find_best(source, template1, (0, 0, source_width, source_height))
        score3, location3 = find_best(source, template3, (0, 0, source_width, source_height))
        results.append((index, rect, source_width, source_height, score1, location1, score3, location3))

    best1 = max(results, key=lambda result: result[4])
    best3 = max(results, key=lambda result: result[6])
    passed = best1[5] is not None and best3[7] is not None and best1[4] >= args.threshold and best3[6] >= args.threshold
    status = "PASS" if passed else ("UNKNOWN" if best1[4] >= args.threshold else "FAIL")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"screenshot={args.screenshot}",
        f"threshold={args.threshold:.4f}",
        f"frame_size={frame.shape[1]}x{frame.shape[0]}",
        f"template1_size={template1.rgb.shape[1]}x{template1.rgb.shape[0]}",
        f"template3_size={template3.rgb.shape[1]}x{template3.rgb.shape[0]}",
        f"crop_count={len(results)}",
    ]
    for index, rect, width, height, score1, location1, score3, location3 in results:
        lines += [
            f"crop{index}_rect={rect}",
            f"crop{index}_size={width}x{height}",
            f"crop{index}_template1_score={score1:.4f}",
            f"crop{index}_template1_match_location={location1}",
            f"crop{index}_template3_score={score3:.4f}",
            f"crop{index}_template3_match_location={location3}",
        ]
    lines += [
        f"best_template1_crop={best1[0]}",
        f"best_template3_crop={best3[0]}",
        f"combined_score={0.65 * best1[4] + 0.35 * best3[6]:.4f}",
        f"RESULT={status}",
    ]

    report = args.output_dir / f"{args.screenshot.stem}.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
