"""Small dependency-free PNG writer for captured BGRA frames."""

from __future__ import annotations

import struct
import zlib

from .models import Frame


def save_png(frame: Frame, path: str) -> None:
    """Save a ``Frame`` as a standard RGBA PNG without external packages."""
    raw = bytearray()
    data = frame.data
    stride = frame.width * 4
    for y in range(frame.height):
        raw.append(0)  # PNG filter: None
        row = data[y * stride : (y + 1) * stride]
        for x in range(0, len(row), 4):
            b, g, r, a = row[x : x + 4]
            raw.extend((r, g, b, a))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", frame.width, frame.height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(bytes(raw)))
    png += chunk(b"IEND", b"")

    with open(path, "wb") as output:
        output.write(png)
