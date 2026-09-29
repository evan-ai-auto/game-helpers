from pathlib import Path

from PIL import Image, ImageDraw
import numpy as np

root = Path(
    r"diagnostic/workflow_runs/basic_capabilities/demon_repellent_incense"
    r"/20260929T151647627872Z/hover/setcursor_postmessage/dwell-0.45s"
)
after = np.asarray(Image.open(root / "after.png").convert("RGB"))
before = np.asarray(Image.open(root / "before.png").convert("RGB"), dtype=np.int16)
diff = np.abs(after.astype(np.int16) - before).mean(axis=2)

# Search around expected input / clock
y0, y1, x0, x1 = 80, 160, 620, 720
sub = diff[y0:y1, x0:x1]
# Find connected high-diff cluster near top-left of high region (cursor tip)
thr = np.percentile(sub, 98)
ys, xs = np.where(sub >= thr)
print("high-diff count", len(xs), "thr", thr)
if len(xs):
    # tip candidate: smallest y, then among those smallest x
    top = int(ys.min())
    left_of_top = xs[ys <= top + 3]
    tip = (x0 + int(left_of_top.min()), y0 + top)
    print("diff tip candidate", tip)
    print("centroid", x0 + int(xs.mean()), y0 + int(ys.mean()))
    print("bbox", x0 + int(xs.min()), y0 + int(ys.min()), x0 + int(xs.max()), y0 + int(ys.max()))

vision, input_pt = (653, 120), (665, 128)
yy, xx = np.unravel_index(sub.argmax(), sub.shape)
print("maxdiff", x0 + int(xx), y0 + int(yy), float(sub.max()))

ann = Image.fromarray(after)
d = ImageDraw.Draw(ann)
d.ellipse([vision[0] - 4, vision[1] - 4, vision[0] + 4, vision[1] + 4], outline=(255, 0, 0), width=2)
d.ellipse([input_pt[0] - 4, input_pt[1] - 4, input_pt[0] + 4, input_pt[1] + 4], outline=(0, 255, 255), width=2)
if len(xs):
    d.ellipse([tip[0] - 4, tip[1] - 4, tip[0] + 4, tip[1] + 4], outline=(255, 255, 0), width=2)
out = root.parent / "_nudge-measure.png"
ann.crop((620, 85, 720, 160)).save(out)
print("saved", out)

# Manual read of attached user image if different size
attached = Path(
    r"C:\Users\Administrator\.cursor\projects\e-work-dev-workspace-my-windows-game-helpers"
    r"\assets\e__work_dev_workspace_my_windows_game-helpers_diagnostic_workflow_runs_"
    r"basic_capabilities_demon_repellent_incense_20260929T151647627872Z_hover_"
    r"setcursor_postmessage_dwell-0.45s_after.png"
)
print("attached exists", attached.exists(), "size", Image.open(attached).size if attached.exists() else None)
print("after size", after.shape[1], after.shape[0])
