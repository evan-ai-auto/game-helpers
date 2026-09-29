import json
from pathlib import Path

from PIL import Image, ImageDraw
import numpy as np

root = Path(
    r"diagnostic/workflow_runs/basic_capabilities/demon_repellent_incense/20260929T134539791112Z"
)
data = json.loads((root / "result.json").read_text(encoding="utf-8"))
trials = data["hover_diagnostic"]["trials"]
for t in trials:
    if not str(t["strategy"]).startswith("setcursor"):
        continue
    print(
        f"{t['strategy']:22} dwell={t['dwell_seconds']} off={t['hover_offset']} "
        f"hover={t['hover_point']} cursor_after={t['cursor_client_after_move']} "
        f"delta={t['tooltip_pixel_delta_mean']}"
    )

after = np.asarray(Image.open(root / "hover/setcursor/dwell-0.90s/after.png").convert("RGB"))
before = np.asarray(
    Image.open(root / "hover/setcursor/dwell-0.90s/before.png").convert("RGB"),
    dtype=np.int16,
)
diff = np.abs(after.astype(np.int16) - before).mean(axis=2)
for y0, y1, x0, x1 in [(60, 160, 580, 720), (80, 150, 620, 700)]:
    sub = diff[y0:y1, x0:x1]
    yy, xx = np.unravel_index(sub.argmax(), sub.shape)
    print("maxdiff", x0 + xx, y0 + yy, float(sub.max()), "region", (x0, y0, x1, y1))

r, g, b = after[:, :, 0].astype(int), after[:, :, 1].astype(int), after[:, :, 2].astype(int)
mask = (b > 150) & (g > 100) & (r < 120) & ((b - r) > 40)
ys, xs = np.where(mask)
sel = (ys >= 50) & (ys <= 200) & (xs >= 500) & (xs <= 750)
ys, xs = ys[sel], xs[sel]
print("blue count", len(xs))
tipx = tipy = None
if len(xs):
    top = int(ys.min())
    tipx = int(xs[ys <= top + 4].mean())
    tipy = top
    print(
        "blue tip",
        tipx,
        tipy,
        "bbox",
        int(xs.min()),
        int(ys.min()),
        int(xs.max()),
        int(ys.max()),
    )
    print("intended hover", 653, 120, "delta tip-hover", tipx - 653, tipy - 120)

ann = Image.fromarray(after)
draw = ImageDraw.Draw(ann)
draw.ellipse([653 - 6, 120 - 6, 653 + 6, 120 + 6], outline=(255, 0, 0), width=2)
if tipx is not None:
    draw.ellipse([tipx - 6, tipy - 6, tipx + 6, tipy + 6], outline=(0, 255, 255), width=2)
out = root / "hover/_cursor-vs-mark.png"
ann.crop((580, 50, 740, 180)).save(out)
print("saved", out)
