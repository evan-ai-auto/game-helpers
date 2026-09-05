"""Shared fingerprint and capture helpers for surface transition diagnostics."""
from __future__ import annotations

import numpy as np
from ..capture.models import Frame


def fingerprint(frame: Frame, size: int = 48) -> np.ndarray:
    raw = np.frombuffer(frame.data, dtype=np.uint8)
    expected = frame.width * frame.height * 4
    bgra = raw[:expected].reshape(frame.height, frame.width, 4)
    gray = (0.114 * bgra[:, :, 0] + 0.587 * bgra[:, :, 1] + 0.299 * bgra[:, :, 2]).astype(np.float32)
    ys = np.linspace(0, frame.height - 1, size).astype(np.int32)
    xs = np.linspace(0, frame.width - 1, size).astype(np.int32)
    return gray[np.ix_(ys, xs)]


def delta(previous: np.ndarray | None, current: np.ndarray) -> float | None:
    return None if previous is None else float(np.mean(np.abs(previous - current)))
