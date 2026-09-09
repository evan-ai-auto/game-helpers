"""Load operator-calibrated fixed UI coordinates for the current game/resolution."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_COORDINATES_PATH = Path("diagnostic/calibration/ui_coordinates.json")


def load_fixed_ui_coordinate(
    target: str,
    *,
    resolution: tuple[int, int],
    path: str | Path = DEFAULT_COORDINATES_PATH,
) -> tuple[int, int] | None:
    """Return a calibrated client coordinate, or ``None`` when not calibrated."""
    resolved = Path(path)
    if not resolved.is_file():
        return None
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return None
    resolution_key = f"{resolution[0]}x{resolution[1]}"
    samples = payload.get("samples")
    if not isinstance(samples, dict):
        return None
    resolution_samples = samples.get(resolution_key)
    if not isinstance(resolution_samples, dict):
        return None
    item = resolution_samples.get(target)
    if not isinstance(item, dict):
        return None
    client = item.get("client")
    if not isinstance(client, list) or len(client) != 2:
        return None
    try:
        x, y = int(client[0]), int(client[1])
    except (TypeError, ValueError):
        return None
    if x < 0 or y < 0 or x >= resolution[0] or y >= resolution[1]:
        return None
    return x, y
