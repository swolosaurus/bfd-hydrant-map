"""Geometry + glyph segmentation shared by the harvester and the parser."""
import numpy as np
from PIL import Image

def load(path):
    return np.asarray(Image.open(path).convert('L'))

# Every generated v2.1 card is laid out on the same 932px grid.
COLUMN_RULES = (194, 283, 372, 461, 550, 786, 931)

def grid(a):
    """Return (horizontal rule rows, vertical rule cols) of the card table.

    Columns are checked against the fixed layout rather than discovered: a few
    cards merge cells so a rule does not run the full height, and lowering the
    threshold far enough to catch those starts picking up dense text instead."""
    dark = a < 128; H, W = dark.shape
    hl = [i for i in range(H) if dark[i].sum() > 0.80 * W]
    if len(hl) < 5 or W != 932:
        return hl, []
    band = dark[hl[3] + 1:hl[-1] - 1]; bh = max(1, band.shape[0])
    vl = [j for j in COLUMN_RULES if band[:, j].sum() > 0.55 * bh]
    return hl, vl

def lines_of(dark):
    """Split a cell into text lines by horizontal projection."""
    rp = dark.sum(1); out = []; s = None
    for i, v in enumerate(rp):
        if v and s is None: s = i
        elif not v and s is not None: out.append((s, i)); s = None
    if s is not None: out.append((s, len(rp)))
    return out

def blobs_of(band):
    """Split one text line into ink blobs. A blob is a run of columns with ink;
    glyphs that touch share a blob, so the matcher has to take them apart.
    Returns (tight bitmap, dy from the line's cap-top, x0, x1)."""
    rows = np.where(band.any(1))[0]
    if not len(rows): return []
    cap = rows[0]
    cp = band.sum(0); out = []; s = None
    for j, v in enumerate(cp):
        if v and s is None: s = j
        elif not v and s is not None: out.append((s, j)); s = None
    if s is not None: out.append((s, len(cp)))
    res = []
    for x0, x1 in out:
        g = band[:, x0:x1]
        r = np.where(g.any(1))[0]
        res.append((np.ascontiguousarray(g[r[0]:r[-1] + 1]), int(r[0] - cap), x0, x1))
    return res

def cell_blobs(a, y0, y1, x0, x1):
    """All blobs in a cell, grouped per text line."""
    sub = a[y0:y1, x0:x1]
    if sub.size == 0: return []
    dark = sub < 160
    return [blobs_of(dark[ls:le]) for ls, le in lines_of(dark)]
