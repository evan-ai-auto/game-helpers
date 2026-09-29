from pathlib import Path

from PIL import Image, ImageDraw
import numpy as np

root = Path(
    r"diagnostic/workflow_runs/basic_capabilities/demon_repellent_incense"
    r"/20260929T151647627872Z/hover"
)
after = np.asarray(
    Image.open(root / "setcursor_postmessage/dwell-0.45s/after.png").convert("RGB")
)
# Find bright white arrow tip near input (665,128)
r, g, b = after[:, :, 0].astype(int), after[:, :, 1].astype(int), after[:, :, 2].astype(int)
# white-ish cursor
white = (r > 220) & (g > 220) & (b > 220)
ys, xs = np.where(white)
sel = (ys >= 90) & (ys <= 160) & (xs >= 620) & (xs <= 720)
ys, xs = ys[sel], xs[sel]
print("white pixels near clock", len(xs))
if len(xs):
    # tip roughly topmost then leftmost among top band
    top = int(ys.min())
    tip_band = (ys <= top + 2)
    tip_x = int(xs[tip_band].min())
    print("white tip approx", tip_x, top, "bbox", int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))

vision = (653, 120)
input_pt = (665, 128)
print("vision", vision, "input", input_pt)
if len(xs):
    print("tip - vision", tip_x - vision[0], top - vision[1])
    print("tip - input", tip_x - input_pt[0], top - input_pt[1])
    # To put tip on vision mark: need to move input by (vision - tip)
    print("suggested delta to input (vision-tip)", vision[0] - tip_x, vision[1] - top)
    print(
        "new nudge = old(12,8) + delta",
        12 + (vision[0] - tip_x),
        8 + (vision[1] - top),
    )

ann = Image.fromarray(after)
draw = ImageDraw.Draw(ann)
draw.ellipse([vision[0] - 4, vision[1] - 4, vision[0] + 4, vision[1] + 4], outline=(255, 0, 0), width=2)
draw.ellipse([input_pt[0] - 4, input_pt[1] - 4, input_pt[0] + 4, input_pt[1] + 4], outline=(0, 255, 255), width=2)
if len(xs):
    draw.ellipse([tip_x - 4, top - 4, tip_x + 4, top + 4], outline=(255, 255, 0), width=2)
ann.crop((620, 85, 720, 160)).save(root / "_nudge-measure.png")
print("saved", root / "_nudge-measure.png")
