#!/usr/bin/env python3
"""Write a simple 128x128 PNG icon (stdlib only)."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def write_simple_png(path: Path, size: int = 128, rgb: tuple[int, int, int] = (46, 125, 50)) -> None:
    """Solid-color RGB PNG (green-ish, ReShade-adjacent)."""
    r, g, b = rgb
    row = bytes([0, r, g, b]) * size
    raw = b"".join(row for _ in range(size))
    compressed = zlib.compress(raw, level=9)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", ihdr)
    png += _png_chunk(b"IDAT", compressed)
    png += _png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "reshade-shader-manager.png"
    write_simple_png(out)
    print(out)
