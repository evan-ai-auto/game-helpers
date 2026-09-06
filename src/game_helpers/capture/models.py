"""Data models for captured window frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Mapping

from game_helpers.core.models import WindowInfo


@dataclass(frozen=True)
class Frame:
    """A captured BGRA image associated with a source window.

    ``metadata`` is an optional bridge for platform-specific perception
    adapters. Vision engines should prefer pixels, but can attach OCR or
    capture-side hints without coupling the capture layer to an OCR engine.
    """

    window: WindowInfo
    width: int
    height: int
    data: bytes
    captured_at: float
    backend: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_bgra(
        cls,
        window: WindowInfo,
        width: int,
        height: int,
        data: bytes,
        *,
        backend: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> "Frame":
        expected = width * height * 4
        if width <= 0 or height <= 0:
            raise ValueError("frame dimensions must be positive")
        if len(data) != expected:
            raise ValueError(f"expected {expected} BGRA bytes, got {len(data)}")
        return cls(window, width, height, bytes(data), time(), backend, metadata or {})
