"""Fixed UI coordinate sample IO and target constants."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .verification_session import VerificationSession

TARGET_ITEM_PANEL = "item_panel_toggle"
TARGET_SHORTCUT_PANEL = "shortcut_panel_toggle"


def load_samples(path: Path) -> dict:
    if not path.exists():
        return {
            "version": 1,
            "game": "梦幻西游",
            "coordinate_type": "fixed_ui",
            "samples": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError(f"不支持的坐标标定文件格式：{path}")
    samples = payload.get("samples")
    if not isinstance(samples, dict):
        raise ValueError(f"坐标标定文件缺少 samples：{path}")
    return payload


def write_sample(
    path: Path,
    *,
    resolution_key: str,
    target: str,
    sample,
    character_name: str,
    identity: str,
) -> None:
    payload = load_samples(path)
    payload["samples"][resolution_key] = payload["samples"].get(resolution_key, {})
    payload["samples"][resolution_key][target] = {
        "client": list(sample.client),
        "screen": list(sample.screen),
        "target_hwnd": sample.target_hwnd,
        "character_name": character_name,
        "identity": identity,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def session_item_profile_path(session: VerificationSession) -> Path:
    from .asset_resolution import resolve_resolution_asset

    geometry = session.geometry()
    return resolve_resolution_asset("item_panel_open.json", (geometry.client_width, geometry.client_height))
