# -*- coding: utf-8 -*-
"""
Regenerate the 1024x500 Google Play feature graphic.

Kept in the repo because the original was built inline in a chat session and
then had to be reverse-engineered (colours and positions sampled back out of
the PNG) when the app was renamed. Don't delete it.

    python -I make_feature_graphic.py

Colours and metrics below were sampled from the pre-rename graphic so the
house style survives future edits.
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1024, 500

BG_L, BG_R = (0x11, 0x11, 0x11), (0x19, 0x19, 0x1C)   # bg gradient, left -> right
RED        = (0xC8, 0x10, 0x2E)                        # BFD red: spine + accent word
WHITE      = (0xFF, 0xFF, 0xFF)
YELLOW     = (0xFF, 0xD6, 0x0A)                        # rule under the title
STRAP      = (0xDE, 0xDE, 0xE2)
META       = (0x9A, 0x9A, 0xA0)

SPINE_W = 15
X       = 68          # common left margin for every text element

# Title is split across two lines, first white second red. Before the rename
# this was BOSTON / HYDRANT MAP; the city was dropped from the title on
# 2026-11-22 and now lives only in the coverage line at the bottom.
TITLE_1, TITLE_2 = "HYDRANT", "MAPS"
STRAP_1 = "Nearest hydrants to any address \u2014 ranked,"
STRAP_2 = "color-coded, and fully offline."
META_LINE = "BOSTON  \u00b7  10 MUTUAL-AID COMMUNITIES  \u00b7  25,700+ HYDRANTS"

FONTS = "C:/Windows/Fonts/"
OUT   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feature-graphic.png")


def main():
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)

    for x in range(W):
        t = x / float(W - 1)
        d.line([(x, 0), (x, H)],
               fill=tuple(int(BG_L[i] + (BG_R[i] - BG_L[i]) * t) for i in range(3)))

    d.rectangle([0, 0, SPINE_W - 1, H], fill=RED)

    title = ImageFont.truetype(FONTS + "ariblk.ttf", 112)
    strap = ImageFont.truetype(FONTS + "arialbd.ttf", 27)
    meta = ImageFont.truetype(FONTS + "arialbd.ttf", 16)

    def draw_at(text, font, cap_top, fill):
        """Draw so the glyph cap-height lands exactly on cap_top."""
        inset = d.textbbox((0, 0), text, font=font)[1]
        d.text((X, cap_top - inset), text, font=font, fill=fill)

    draw_at(TITLE_1, title, 128, WHITE)
    draw_at(TITLE_2, title, 238, RED)

    d.rectangle([X, 344, X + 104, 350], fill=YELLOW)

    draw_at(STRAP_1, strap, 378, STRAP)
    draw_at(STRAP_2, strap, 410, STRAP)
    draw_at(META_LINE, meta, 458, META)

    im.save(OUT, optimize=True)
    print("wrote %s  %dx%d  %.0f KB" % (OUT, W, H, os.path.getsize(OUT) / 1024.0))


if __name__ == "__main__":
    main()
