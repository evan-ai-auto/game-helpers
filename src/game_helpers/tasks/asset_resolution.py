"""Resolve UI assets by child-client resolution (e.g. 800x600)."""

from __future__ import annotations

from pathlib import Path

UI_ASSETS_ROOT = Path("data/assets/ui")
RESOLUTIONS_ROOT = UI_ASSETS_ROOT / "resolutions"
DEFAULT_BASELINE = (800, 600)


def resolution_key(client_size: tuple[int, int]) -> str:
    width, height = int(client_size[0]), int(client_size[1])
    return f"{width}x{height}"


def resolution_dir(client_size: tuple[int, int]) -> Path:
    return RESOLUTIONS_ROOT / resolution_key(client_size)


def resolve_resolution_asset(
    relative_name: str,
    client_size: tuple[int, int],
    *,
    required: bool = True,
) -> Path:
    """Return ``data/assets/ui/resolutions/{WxH}/{relative_name}``.

    Multi-resolution files live under per-size folders. Missing folders/files
    raise with a clear message so we never silently reuse another resolution.
    """
    path = resolution_dir(client_size) / relative_name
    if path.exists():
        return path
    if not required:
        return path
    key = resolution_key(client_size)
    raise FileNotFoundError(
        f"缺少分辨率资产 {key}/{relative_name}。"
        f"请放到 {RESOLUTIONS_ROOT / key}/ 下。"
        f"当前开发优先维护 {DEFAULT_BASELINE[0]}x{DEFAULT_BASELINE[1]}；"
        "其它分辨率等功能完成后再补资产验证。"
    )
