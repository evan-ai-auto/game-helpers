from pathlib import Path

from PIL import Image, ImageDraw
import numpy as np

root = Path(
    r"diagnostic/workflow_runs/basic_capabilities/demon_repellent_incense"
    r"/20260929T134539791112Z/hover"
)
after = np.asarray(Image.open(root / "setcursor/dwell-0.90s/after.png").convert("RGB"))
before = np.asarray(
    Image.open(root / "setcursor/dwell-0.90s/before.png").convert("RGB"), dtype=np.int16
)
diff = np.abs(after.astype(np.int16) - before).mean(axis=2)

# Focus tightly on clock header band
y0, y1, x0, x1 = 85, 145, 620, 700
sub = diff[y0:y1, x0:x1]
# top-N peaks
flat = sub.reshape(-1)
idx = np.argsort(flat)[-20:]
print("top diff peaks in clock band:")
for i in idx[::-1]:
    yy, xx = divmod(int(i), sub.shape[1])
    print(" ", x0 + xx, y0 + yy, round(float(sub[yy, xx]), 1))

# Manual: save annotated zoom with hover + maxdiff + a few candidate tip points
ann = Image.fromarray(after).convert("RGB")
draw = ImageDraw.Draw(ann)
draw.ellipse([653 - 5, 120 - 5, 653 + 5, 120 + 5], outline=(255, 0, 0), width=2)
yy, xx = np.unravel_index(sub.argmax(), sub.shape)
mx, my = x0 + int(xx), y0 + int(yy)
draw.ellipse([mx - 5, my - 5, mx + 5, my + 5], outline=(0, 255, 255), width=2)
print("maxdiff", mx, my, "vs hover", 653, 120, "delta", mx - 653, my - 120)

# Also check +4x and -8x offset after images for cursor relative to clock
for label, hx, hy in [
    ("setcursor/dwell-0.90s", 653, 120),
    ("setcursor/dwell-0.45s_off-+4_+0", 657, 120),
    ("setcursor/dwell-0.45s_off--8_-4", 645, 116),
    ("setcursor/dwell-0.45s_off-+0_+4", 653, 124),
]:
    a = np.asarray(Image.open(root / label / "after.png").convert("RGB"))
    b = np.asarray(Image.open(root / label / "before.png").convert("RGB"), dtype=np.int16)
    d = np.abs(a.astype(np.int16) - b).mean(axis=2)
    s = d[y0:y1, x0:x1]
    yy, xx = np.unravel_index(s.argmax(), s.shape)
    print(label, "hover", (hx, hy), "maxdiff", (x0 + int(xx), y0 + int(yy)))

out = root / "_aim-zoom.png"
ann.crop((620, 85, 720, 160)).save(out)
print("saved", out)
