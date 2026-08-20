"""Generate assets/icon.ico — pure stdlib, so the build needs nothing installed.

Writes classic BMP (DIB) icon entries rather than PNG-compressed ones: every
Windows version and every resource packer understands them. Run this only when
the artwork changes; the .ico itself is committed.
"""

from __future__ import annotations

import struct
from pathlib import Path

SIZES = (16, 32, 48, 64, 256)
SUPERSAMPLE = 4

GREEN = (0x1B, 0x7A, 0x43)
GREEN_DEEP = (0x14, 0x60, 0x34)
PAGE = (0xFA, 0xF8, 0xF1)

# Open book: two leaves meeting at a centre spine, in normalised coordinates.
LEFT_PAGE = ((0.18, 0.38), (0.48, 0.32), (0.48, 0.70), (0.18, 0.64))
RIGHT_PAGE = ((0.52, 0.32), (0.82, 0.38), (0.82, 0.64), (0.52, 0.70))


def _inside_polygon(x: float, y: float, polygon) -> bool:
    inside = False
    count = len(polygon)
    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < crossing:
                inside = not inside
    return inside


def _inside_rounded_square(x: float, y: float, radius: float) -> bool:
    near_x = min(max(x, radius), 1.0 - radius)
    near_y = min(max(y, radius), 1.0 - radius)
    dx, dy = x - near_x, y - near_y
    return dx * dx + dy * dy <= radius * radius


def _sample(x: float, y: float):
    """Colour at a point, or None where the icon is transparent."""
    if not _inside_rounded_square(x, y, 0.21):
        return None
    if _inside_polygon(x, y, LEFT_PAGE) or _inside_polygon(x, y, RIGHT_PAGE):
        return PAGE
    # Subtle vertical shading keeps the tile from looking flat.
    blend = y * 0.55
    return tuple(
        round(GREEN[channel] + (GREEN_DEEP[channel] - GREEN[channel]) * blend)
        for channel in range(3)
    )


def _render(size: int) -> bytes:
    """Bottom-up BGRA rows, supersampled for smooth edges."""
    step = 1.0 / (size * SUPERSAMPLE)
    rows = []
    for row in range(size):
        pixels = bytearray()
        for column in range(size):
            red = green = blue = alpha = 0
            for sub_y in range(SUPERSAMPLE):
                for sub_x in range(SUPERSAMPLE):
                    x = (column * SUPERSAMPLE + sub_x + 0.5) * step
                    y = (row * SUPERSAMPLE + sub_y + 0.5) * step
                    colour = _sample(x, y)
                    if colour is not None:
                        red += colour[0]
                        green += colour[1]
                        blue += colour[2]
                        alpha += 255
            samples = SUPERSAMPLE * SUPERSAMPLE
            covered = alpha // 255
            if covered:
                pixels += bytes((blue // covered, green // covered, red // covered))
            else:
                pixels += b"\x00\x00\x00"
            pixels.append(alpha // samples)
        rows.append(bytes(pixels))
    return b"".join(reversed(rows))  # DIB rows run bottom-up


def build(destination: Path) -> None:
    images = []
    for size in SIZES:
        header = struct.pack(
            "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, size * size * 4, 0, 0, 0, 0
        )
        mask_row = b"\x00" * (((size + 31) // 32) * 4)  # 32-bit alpha carries shape
        images.append(header + _render(size) + mask_row * size)

    offset = 6 + 16 * len(images)
    directory = struct.pack("<HHH", 0, 1, len(images))
    for size, image in zip(SIZES, images):
        directory += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(image), offset
        )
        offset += len(image)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(directory + b"".join(images))


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    build(target)
    print(f"wrote {target} ({target.stat().st_size:,} bytes)")
