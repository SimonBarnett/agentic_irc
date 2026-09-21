#!/usr/bin/env python3
"""Write src/moot_thin/airc-moot-thin.ico (16+32 px, blue radio motif)."""

from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "moot_thin" / "airc-moot-thin.ico"


def rgba(size: int) -> bytes:
    px = bytearray(size * size * 4)
    cx, cy = (size - 1) / 2.0, (size - 1) / 2.0
    r = size * 0.38
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy
            d = (dx * dx + dy * dy) ** 0.5
            i = (y * size + x) * 4
            if d <= r:
                px[i : i + 4] = bytes((0x1a, 0x6b, 0xd4, 0xff))
            elif d <= r + 1.2:
                px[i : i + 4] = bytes((0xff, 0xff, 0xff, 0xff))
            elif abs(dx) < 1.2 and abs(dy) > r * 0.15:
                px[i : i + 4] = bytes((0xff, 0xff, 0xff, 0xff))
            else:
                px[i : i + 4] = bytes((0, 0, 0, 0))
    return bytes(px)


def write_ico(path: Path) -> None:
    images = [(16, rgba(16)), (32, rgba(32))]
    offset = 6 + 16 * len(images)
    chunks: list[bytes] = []
    for size, bmp in images:
        header = struct.pack(
            "<IIIHHIIIIII",
            40,
            size,
            size * 2,
            1,
            32,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        # ICO stores BMP bottom-up with padded rows
        row = size * 4
        pad = (4 - (row % 4)) % 4
        flipped = bytearray()
        for y in range(size - 1, -1, -1):
            flipped.extend(bmp[y * row : (y + 1) * row])
            flipped.extend(b"\x00" * pad)
        and_mask = b"\x00" * (((size + 31) // 32) * 4 * size)
        blob = header + bytes(flipped) + and_mask
        chunks.append(blob)
    out = bytearray()
    out += struct.pack("<HHH", 0, 1, len(images))
    for i, (size, _) in enumerate(images):
        out += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,
            size if size < 256 else 0,
            0,
            0,
            1,
            32,
            len(chunks[i]),
            offset,
        )
        offset += len(chunks[i])
    for c in chunks:
        out += c
    path.write_bytes(out)


if __name__ == "__main__":
    write_ico(OUT)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
