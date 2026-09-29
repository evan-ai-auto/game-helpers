from pathlib import Path

from PIL import Image

from game_helpers.core.models import Rect
from game_helpers.tasks.incense_status_vision import (
    tooltip_ocr_box,
    tooltip_ocr_box_below,
)
from game_helpers.vision.windows_ocr import WindowsNativeOCRBackend

root = Path(
    r"diagnostic/workflow_runs/basic_capabilities/demon_repellent_incense"
    r"/20260929T154224745823Z/hover/setcursor_postmessage/dwell-0.90s"
)
after = Image.open(root / "after.png").convert("RGB")
input_pt = (647, 144)
backend = WindowsNativeOCRBackend(language="zh-Hans-CN")
boxes = {
    "above": tooltip_ocr_box(input_pt, width=800, height=600),
    "below": tooltip_ocr_box_below(input_pt, width=800, height=600),
    "left": (560, 100, 660, 160),
    "under_clock": (620, 125, 720, 180),
    "wide_under": (600, 120, 750, 190),
}
lines = []
for name, box in boxes.items():
    text = " ".join(item.text for item in backend.read(after, region=Rect(*box)))
    lines.append(f"{name} {box}: {text}")
    after.crop(box).save(root / f"_ocr-{name}.png")
(root / "_ocr-probe.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
