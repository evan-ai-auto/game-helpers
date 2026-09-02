"""Data models for captured window frames."""

from __future__ import annotations

from dataclasses import dataclass
from time import time

from game_helpers.core.models import WindowInfo


@dataclass(frozen=True)
class Frame:
    """A captured BGRA image associated with a source window.

    ``data`` contains tightly packed BGRA bytes, four bytes per pixel.
    Keeping the capture layer independent of NumPy lets callers choose their
    preferred image-processing stack later.
    """

    window: WindowInfo
    width: int
    height: int
    data: bytes
    captured_at: float
    backend: str

    @classmethod
    def from_bgra(
        cls,
        window: WindowInfo,
        width: int,
        height: int,
        data: bytes,
        *,
        backend: str,
    ) -> "Frame":
        expected = width * height * 4
        if width <= 0 or height <= 0:
            raise ValueError("frame dimensions must be positive")
        if len(data) != expected:
            raise ValueError(f"expected {expected} BGRA bytes, got {len(data)}")
        return cls(window, width, height, bytes(data), time(), backend)
