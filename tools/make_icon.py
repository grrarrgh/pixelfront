"""Writes pixelfront.ico (the exe's icon) from the art in sprites.py.

    python tools/make_icon.py [output.ico]

The .ico holds every size Windows asks for, each as an embedded PNG (supported since Vista).
"""
import io
import logging
import os
import struct
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)
log = logging.getLogger("make_icon")


def png_bytes(surf):
    buf = io.BytesIO()
    pygame.image.save(surf, buf, "icon.png")
    return buf.getvalue()


def write_ico(path, images):
    """images: [(size, png bytes)]. A size of 256 is stored as 0, as the format requires."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = [], []
    for size, data in images:
        dim = 0 if size >= 256 else size
        entries.append(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        blobs.append(data)
        offset += len(data)
    with open(path, "wb") as f:
        f.write(header + b"".join(entries) + b"".join(blobs))


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "pixelfront.ico")
    pygame.init()
    pygame.display.set_mode((1, 1))
    from pixelfront.sprites import Sprites, app_icon
    sprites = Sprites()
    images = [(s, png_bytes(app_icon(s, sprites))) for s in SIZES]
    write_ico(out, images)
    log.info("Wrote %s (%s px, %d bytes)", out, ", ".join(map(str, SIZES)), os.path.getsize(out))


if __name__ == "__main__":
    main()
