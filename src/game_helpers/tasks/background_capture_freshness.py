"""Layered WGC freshness diagnostic for covered-game validation.

Diagnostic-only: captures the host window once per sample, then derives the
selected WSGAME child crop from screen/client geometry. It does not alter
production capture or coordinate configuration.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from PIL import Image

from ..vision.scene_coordinate import read_player_location
from ..vision.windows_ocr import WindowsNativeOCRBackend
from .soul_shortcut_diagnostic_flow import (
    MOTION_PLAYFIELD_BOX,
    MOTION_PLAYFIELD_RATIO,
    MOTION_RIGHT_EDGE_BOX,
    MOTION_RIGHT_EDGE_RATIO,
    _refresh_capture_surface,
    image_diff,
)
from .soul_task_match import as_pil_image
from .verification_session import VerificationSession


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def _crop_selected(host: Image.Image, session: VerificationSession) -> Image.Image:
    from ..core.surface import query_surface_geometry

    selected = session.geometry()
    host_geometry = query_surface_geometry(session.parent_hwnd)
    left = selected.screen_left - host_geometry.screen_left
    top = selected.screen_top - host_geometry.screen_top
    right = left + selected.client_width
    bottom = top + selected.client_height
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(host.width, right), min(host.height, bottom)
    if x1 <= x0 or y1 <= y0:
        raise RuntimeError(
            "selected WSGAME crop is outside host frame: "
            f"rect=({left},{top},{right},{bottom}) host={host.width}x{host.height}"
        )
    return host.crop((x0, y0, x1, y1))


def run_background_capture_freshness(
    session: VerificationSession,
    output: str | Path,
    *,
    wait_seconds: float = 5.0,
    sample_interval: float = 0.25,
    refresh_before_sampling: bool = False,
) -> dict[str, object]:
    """Measure freshness at Host WGC -> WSGAME crop -> playfield -> OCR.

    refresh_before_sampling=False is the pure covered test.
    True applies the current Surface-switch/RedrawWindow refresh once before
    sampling, keeping the two experiments directly comparable.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    refresh = None
    if refresh_before_sampling:
        refresh = _refresh_capture_surface(session)
        print(
            "[命魂诊断] Freshness：采样前执行当前 Surface 刷新："
            f"{'成功' if refresh['ok'] else '失败'}；"
            f"切换他窗={'是' if refresh.get('switched') else '否'}"
            + (f"；原因={refresh['reason']}" if refresh.get("reason") else "")
        )
    else:
        print("[命魂诊断] Freshness：纯覆盖模式，不执行 Surface/RedrawWindow 刷新")

    samples: list[dict[str, object]] = []
    first_host: Image.Image | None = None
    first_child: Image.Image | None = None
    started = time.monotonic()
    frame_count = max(2, int(wait_seconds / sample_interval) + 1)

    for index in range(frame_count):
        if index:
            target = started + index * sample_interval
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)

        host_frame = session.capture.capture(session.parent_hwnd)
        host_image = as_pil_image(host_frame).convert("RGB")
        child_image = _crop_selected(host_image, session)

        if first_host is None:
            first_host = host_image
            first_child = child_image
            host_ratio = child_ratio = 0.0
            play_ratio = right_ratio = 0.0
        else:
            host_ratio = image_diff(first_host, host_image).ratio
            child_ratio = image_diff(first_child, child_image).ratio
            play_ratio = image_diff(
                first_child.crop(MOTION_PLAYFIELD_BOX),
                child_image.crop(MOTION_PLAYFIELD_BOX),
            ).ratio
            right_ratio = image_diff(
                first_child.crop(MOTION_RIGHT_EDGE_BOX),
                child_image.crop(MOTION_RIGHT_EDGE_BOX),
            ).ratio

        elapsed = time.monotonic() - started
        sample = {
            "index": index + 1,
            "elapsed_seconds": round(elapsed, 3),
            "host_diff_ratio": host_ratio,
            "child_diff_ratio": child_ratio,
            "playfield_ratio": play_ratio,
            "right_edge_ratio": right_ratio,
        }
        samples.append(sample)
        _save(host_image, output / f"host-{index + 1:02d}.png")
        _save(child_image, output / f"wsgame-{index + 1:02d}.png")
        print(
            f"[命魂诊断] Freshness：第 {index + 1}/{frame_count} 帧 "
            f"t={elapsed:.2f}s Host={host_ratio:.3f} "
            f"WSGAME={child_ratio:.3f} Playfield={play_ratio:.3f} "
            f"RightEdge={right_ratio:.3f}"
        )

    assert first_host is not None and first_child is not None

    _save(first_host, output / "host-first.png")
    _save(first_child, output / "wsgame-first.png")
    _save(host_image, output / "host-last.png")
    _save(child_image, output / "wsgame-last.png")

    def series(key: str, threshold: float = 0.0) -> dict[str, object]:
        changed = [s for s in samples[1:] if float(s[key]) >= threshold]
        values = [float(s[key]) for s in samples[1:]]
        return {
            "frame_count": len(samples),
            "changed_frame_count": len(changed),
            "max_diff_ratio": max(values, default=0.0),
            "first_change": changed[0] if changed else None,
            "last_change": changed[-1] if changed else None,
            "threshold": threshold,
        }

    ocr: dict[str, object] = {"backend": "不可用", "first": None, "last": None}
    try:
        backend = WindowsNativeOCRBackend(language="zh-Hans-CN")
        first_reading = read_player_location(first_child, backend)
        last_reading = read_player_location(child_image, backend)
        ocr = {
            "backend": "Windows.Media.Ocr",
            "language": backend.language,
            "first": {
                "formatted": first_reading.formatted,
                "parsed_coordinate": list(first_reading.parsed) if first_reading.parsed else None,
            },
            "last": {
                "formatted": last_reading.formatted,
                "parsed_coordinate": list(last_reading.parsed) if last_reading.parsed else None,
            },
        }
    except RuntimeError as exc:
        ocr["reason"] = str(exc)

    report = {
        "experiment": "background_capture_freshness",
        "refresh_before_sampling": refresh_before_sampling,
        "refresh": refresh,
        "wait_seconds": wait_seconds,
        "sample_interval": sample_interval,
        "frame_count": len(samples),
        "host": series("host_diff_ratio"),
        "wsgame_crop": series("child_diff_ratio"),
        "playfield": series("playfield_ratio", MOTION_PLAYFIELD_RATIO),
        "right_edge": series("right_edge_ratio", MOTION_RIGHT_EDGE_RATIO),
        "ocr": ocr,
        "samples": samples,
        "production_coordinate_changed": False,
        "production_config_changed": False,
    }
    (output / "validation-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[命魂诊断] Freshness：报告={output / 'validation-report.json'}")
    return report


__all__ = ["run_background_capture_freshness"]
