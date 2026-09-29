from pathlib import Path

from PIL import Image
import numpy as np

path = Path(
    r"diagnostic/workflow_runs/basic_capabilities/demon_repellent_incense"
    r"/20260929T134539791112Z/hover/_cursor-vs-mark.png"
)
img = np.asarray(Image.open(path).convert("RGB"))
print("crop size", img.shape)
ox, oy = 580, 50
r, g, b = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
red = (r > 200) & (g < 80) & (b < 80)
ys, xs = np.where(red)
print(
    "red pixels",
    len(xs),
    "centroid full",
    int(xs.mean()) + ox if len(xs) else None,
    int(ys.mean()) + oy if len(xs) else None,
)
blue = (b > 160) & (g > 120) & (r < 140) & ((b - r) > 50)
ys2, xs2 = np.where(blue)
print("blue pixels", len(xs2))
if len(xs2):
    top = int(ys2.min())
    tip_xs = xs2[ys2 <= top + 3]
    print(
        "blue tip full",
        int(tip_xs.mean()) + ox,
        top + oy,
        "centroid full",
        int(xs2.mean()) + ox,
        int(ys2.mean()) + oy,
    )
print("intended hover full", 653, 120)
