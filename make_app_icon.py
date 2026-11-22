# -*- coding: utf-8 -*-
"""
Build the PWA / Play Store app icons from hydrant-mark.png.

    python -I make_app_icon.py

Writes icon-512.png and icon-192.png.

Why the generous margin: manifest.json declares these icons "any maskable",
so Android may crop them to a circle or squircle. A maskable icon is only
guaranteed to keep what sits inside a centred circle of 80% of the width, so
the hydrant is scaled to ~67% of the canvas height and centred. It looks
airy as a flat square and correct once the launcher masks it.

Background is opaque white: Play prefers no alpha on the 512 listing icon,
and the mark is red with a black outline, which needs a light field to read
at launcher size.
"""
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MARK = os.path.join(HERE, "hydrant-mark.png")

BG          = (0xFF, 0xFF, 0xFF, 255)
CANVAS      = 512
MARK_HEIGHT = 344          # ~67% of canvas - inside the maskable safe circle
SIZES       = {"icon-512.png": 512, "icon-192.png": 192}


def main():
    mark = Image.open(MARK).convert("RGBA")
    mark = mark.crop(mark.getbbox())                     # trim transparent padding

    scale = MARK_HEIGHT / float(mark.size[1])
    w, h = int(round(mark.size[0] * scale)), MARK_HEIGHT
    mark = mark.resize((w, h), Image.LANCZOS)

    base = Image.new("RGBA", (CANVAS, CANVAS), BG)
    base.alpha_composite(mark, ((CANVAS - w) // 2, (CANVAS - h) // 2))
    flat = base.convert("RGB")                           # no alpha for Play

    for name, px in SIZES.items():
        out = flat if px == CANVAS else flat.resize((px, px), Image.LANCZOS)
        path = os.path.join(HERE, name)
        out.save(path, optimize=True)
        print("wrote %-14s %dx%d  %.0f KB" % (name, px, px,
                                              os.path.getsize(path) / 1024.0))


if __name__ == "__main__":
    main()
