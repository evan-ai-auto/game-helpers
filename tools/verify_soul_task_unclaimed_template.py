"""Verify Soul Task templates with configurable two-stage crops."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PIL import Image

DEFAULT_ROI = (0, 0, 272, 252)
DEFAULT_CROPS = ((0, 0, 272, 252), (20, 140, 100, 220))

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
    gx = np.zeros_like(value); gy = np.zeros_like(value)
    gx[:, 1:-1] = value[:, 2:] - value[:, :-2]
    gy[1:-1, :] = value[2:, :] - value[:-2, :]
    return np.hypot(gx, gy)

def score(patch: np.ndarray, template: Template) -> float:
    w = template.alpha; total = float(w.sum())
    if total <= 1e-6: return 0.0
    rgb = 1.0 - float((np.abs(patch - template.rgb).mean(2) * w).sum()) / total / 255.0
    pg, tg = gray(patch), gray(template.rgb)
    pn = (pg - pg.mean()) / (pg.std() + 1e-6); tn = (tg - tg.mean()) / (tg.std() + 1e-6)
    structure = 1.0 - float((np.abs(pn - tn) * w).sum()) / total / 4.0
    pe, te = edges(pg), edges(tg); scale = max(float(te.max()), 1.0)
    edge = 1.0 - float((np.abs(pe - te) / scale * w).sum()) / total
    return float(0.45 * rgb + 0.30 * structure + 0.25 * edge)

def find_best(frame: np.ndarray, template: Template, roi: tuple[int, int, int, int]):
    x0, y0, x1, y1 = roi; region = frame[y0:y1, x0:x1]
    th, tw = template.rgb.shape[:2]
    if region.shape[0] < th or region.shape[1] < tw: return 0.0, None
    best, xy = -float("inf"), None
    for y in range(region.shape[0] - th + 1):
        for x in range(region.shape[1] - tw + 1):
            value = score(region[y:y + th, x:x + tw], template)
            if value > best: best, xy = value, (x0 + x, y0 + y)
    return max(0.0, float(best)), xy

def parse_rect(value: str) -> tuple[int, int, int, int]:
    parts = tuple(int(v) for v in value.split(","))
    if len(parts) != 4: raise argparse.ArgumentTypeError("rect must be x0,y0,x1,y1")
    return parts

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("screenshot", type=Path); p.add_argument("template1", type=Path); p.add_argument("template3", type=Path)
    p.add_argument("--roi", type=parse_rect, default=DEFAULT_ROI)
    p.add_argument("--crop", action="append", type=parse_rect, dest="crops", help="relative crop rect; repeat twice")
    p.add_argument("--threshold", type=float, default=0.82)
    p.add_argument("--output-dir", type=Path, default=Path("diagnostic/soul_task/template_verify"))
    a = p.parse_args(); paths = (a.screenshot, a.template1, a.template3)
    if any(not x.is_file() for x in paths): print("ERROR screenshot or template not found"); return 2
    try:
        image = Image.open(a.screenshot).convert("RGB"); frame = np.asarray(image, dtype=np.float32)
        t1, t3 = load_template(a.template1), load_template(a.template3)
    except (OSError, ValueError) as exc: print(f"ERROR unable to load image/template: {exc}"); return 2
    crops = tuple(a.crops or DEFAULT_CROPS)
    if len(crops) != 2: print("ERROR exactly two --crop values are required"); return 2
    results = []
    source = frame
    for index, rect in enumerate(crops, 1):
        x0, y0, x1, y1 = rect; source = source[y0:y1, x0:x1]
        if source.size == 0: print(f"ERROR empty crop {index}"); return 2
        s1, xy1 = find_best(source, t1, (0, 0, source.shape[1], source.shape[0]))
        s3, xy3 = find_best(source, t3, (0, 0, source.shape[1], source.shape[0]))
        results.append((index, rect, s1, xy1, s3, xy3))
    best1 = max(results, key=lambda r: r[2]); best3 = max(results, key=lambda r: r[4])
    passed = best1[3] is not None and best3[5] is not None and best1[2] >= a.threshold and best3[4] >= a.threshold
    status = "PASS" if passed else ("UNKNOWN" if best1[2] >= a.threshold else "FAIL")
    a.output_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"screenshot={a.screenshot}", f"threshold={a.threshold:.4f}", f"crop_count={len(results)}"]
    for i, rect, s1, xy1, s3, xy3 in results:
        lines += [f"crop{i}_rect={rect}", f"crop{i}_template1_score={s1:.4f}", f"crop{i}_template1_match_location={xy1}", f"crop{i}_template3_score={s3:.4f}", f"crop{i}_template3_match_location={xy3}"]
    lines += [f"best_template1_crop={best1[0]}", f"best_template3_crop={best3[0]}", f"combined_score={0.65 * best1[2] + 0.35 * best3[4]:.4f}", f"RESULT={status}"]
    report = a.output_dir / f"{a.screenshot.stem}.txt"; report.write_text("\n".join(lines) + "\n", encoding="utf-8"); print("\n".join(lines))
    return 0 if status == "PASS" else 1

if __name__ == "__main__": raise SystemExit(main())
