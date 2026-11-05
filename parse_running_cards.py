"""
parse_running_cards.py — read the BFD v2.1 running cards straight off the
pixels, with no OCR engine and no API calls.

The v2.1 cards are generated, not scanned: identical font, identical column
geometry, no antialiasing jitter. So every glyph in the corpus is one of a few
dozen exact bitmaps, and a cell can be decoded by covering its ink with those
bitmaps. Anything that cannot be covered exactly is reported instead of
guessed, which is the whole point — the v1.0 data came from OCR and spent
months accumulating fixes for invented units (D34, TL17, E40).

Scanned cards (the 82xx mutual-aid sheets and the harbour-island photos) have
no fixed geometry and are skipped; those still need the vision pipeline in
ocr_running_cards.py, or the previous parse carried forward.

Usage:  python parse_running_cards.py [--src DIR] [--out running_cards.json]
"""
import argparse, collections, json, pickle, re
from pathlib import Path

import numpy as np

from cardlib import load, grid, cell_blobs

FONT = Path("card_font.pkl")
TITLE_FONT = Path("card_font_title.pkl")
COLS = ['engine', 'ladder', 'special', 'chief']
COV = ['engine', 'ladder']
SPACE_GAP = 4          # px; intra-token gaps are 1-2, inter-token 6-8


def load_font():
    tpl = pickle.load(FONT.open('rb'))
    by_w = collections.defaultdict(list)
    for (h, w, dy, b), ch in tpl.items():
        by_w[w].append((h, dy, b, ch))
    return by_w, max(by_w)


def _covers(g, dy, by_w, maxw, advances, cap=4):
    H, W = g.shape
    out = set()

    def walk(x, placed, text):
        if len(out) >= cap: return
        if x >= W:
            canvas = np.zeros((H, W), dtype=bool)
            for px, top, th, tw, arr in placed:
                canvas[top:top + th, px:px + tw] |= arr
            if np.array_equal(canvas, g): out.add(text)
            return
        for w in range(1, min(maxw, W - x) + 1):
            for th, tdy, tb, ch in by_w.get(w, ()):
                top = tdy - dy
                if top < 0 or top + th > H: continue
                if g[top:top + th, x:x + w].tobytes() != tb: continue
                arr = np.frombuffer(tb, dtype=bool).reshape(th, w)
                for adv in advances(w):
                    if adv <= 0: continue
                    walk(x + adv, placed + [(x, top, th, w, arr)], text + ch)
                    if len(out) >= cap: return

    walk(0, [], '')
    return out


# Neighbouring glyphs can share up to two columns of ink. Allowing that
# everywhere invents readings, so pack tightly first and loosen only when
# nothing fits. A blob with more than one exact cover is reported, not guessed.
STAGES = (lambda w: (w,), lambda w: (w, w - 1), lambda w: (w, w - 1, w - 2))


_CACHE = {}


def decode_blob(g, dy, by_w, maxw):
    # The corpus only contains ~100 distinct blobs across 1.2M instances, so
    # the search runs about that many times rather than once per glyph.
    key = (g.shape, dy, g.tobytes())
    if key in _CACHE:
        return _CACHE[key]
    val = None
    for adv in STAGES:
        r = _covers(g, dy, by_w, maxw, adv)
        if len(r) == 1:
            val = r.pop(); break
        if len(r) > 1:
            break
    _CACHE[key] = val
    return val


def decode_cell(a, y0, y1, x0, x1, by_w, maxw, problems, where):
    tokens = []
    for line in cell_blobs(a, y0, y1, x0, x1):
        cur, prev_end = '', None
        for g, dy, bx0, bx1 in line:
            txt = decode_blob(g, dy, by_w, maxw)
            if txt is None:
                problems.append(f"{where}: undecodable {g.shape[0]}x{g.shape[1]} blob")
                txt = '\ufffd'
            if prev_end is not None and bx0 - prev_end >= SPACE_GAP:
                if cur: tokens.append(cur)
                cur = ''
            cur += txt
            prev_end = bx1
        if cur: tokens.append(cur)
    # A narrow cell wraps "D01-ACCT" onto two lines; the hyphen is a break,
    # not part of the code, so stitch those back together.
    merged = []
    for t in tokens:
        if merged and merged[-1].endswith('-'):
            merged[-1] += t
        else:
            merged.append(t)
    return merged


DD_RE = re.compile(r'District:(\d+)Division:(\d+)')


def parse_district_division(a, hl, title_font, problems, box):
    """The card prints its own District / Division in the title band; take them
    from there rather than from the box bundle, whose district field disagrees
    on 171 boxes and carries a district 5 that BFD does not have."""
    by_w, maxw = title_font
    txt = ''.join(''.join(
        decode_blob(g, dy, by_w, maxw) or '�' for g, dy, _, _ in line)
        for line in cell_blobs(a, hl[0] + 2, hl[1] - 1, 552, 930))
    m = DD_RE.search(txt)
    if not m:
        problems.append(f"{box}: could not read District/Division from {txt!r}")
        return None, None
    return int(m.group(1)), int(m.group(2))


def parse_card(path, by_w, maxw, title_font=None):
    a = load(path)
    problems = []
    if a.shape[1] != 932:
        return None, [f"{path.name}: not a generated v2.1 card (width {a.shape[1]})"]
    hl, vl = grid(a)
    if len(hl) < 6 or len(vl) != 7:
        return None, [f"{path.name}: table geometry not found ({len(hl)} rules, {len(vl)} columns)"]
    cols = [0] + vl
    district = division = None
    if title_font:
        district, division = parse_district_division(a, hl, title_font, problems, path.stem)
    respond, covering = [], []
    for ri in range(3, len(hl) - 1):
        y0, y1 = hl[ri] + 2, hl[ri + 1] - 1

        def cell(ci):
            return decode_cell(a, y0, y1, cols[ci] + 2, cols[ci + 1] - 1,
                               by_w, maxw, problems, f"{path.stem} row{ri} col{ci}")

        alarm = ''.join(cell(0))
        if not alarm:
            continue
        respond.append({'alarm': alarm, **{n: cell(i + 1) for i, n in enumerate(COLS)}})
        covering.append({'alarm': alarm, **{n: cell(i + 5) for i, n in enumerate(COV)}})
    return {'respond_to_fire': respond, 'covering_assignments': covering,
            'card_district': district, 'card_division': division}, problems


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='C:/Users/Administrator/Desktop/png')
    ap.add_argument('--out', default='running_cards.json')
    ap.add_argument('--prev', default='running_cards.json',
                    help='previous parse, used for location / district / division')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--only', default='')
    args = ap.parse_args()

    by_w, maxw = load_font()
    title_font = None
    if TITLE_FONT.exists():
        t = pickle.load(TITLE_FONT.open('rb'))
        tw = collections.defaultdict(list)
        for (h, w, dy, b), ch in t.items(): tw[w].append((h, dy, b, ch))
        title_font = (tw, max(tw))
    prev = json.loads(Path(args.prev).read_text(encoding='utf-8')) if Path(args.prev).exists() else {}
    bx = Path('boston_boxes.json')
    boxes = {str(b['n']): b for b in json.loads(bx.read_text(encoding='utf-8'))} if bx.exists() else {}

    files = sorted(Path(args.src).glob('*.[pP][nN][gG]'))
    if args.only:
        want = set(args.only.split(','))
        files = [f for f in files if f.stem in want]
    if args.limit:
        files = files[:args.limit]

    out, skipped, flagged = {}, [], []
    for n, f in enumerate(files):
        data, problems = parse_card(f, by_w, maxw, title_font)
        if data is None:
            skipped.append(problems[0])
            continue
        # A card with any glyph we could not read is not half-parsed into the
        # bundle — a replacement character in a due list is worse than no due
        # list. The zone cards that trip this use a different notation
        # (bare comma-separated numbers plus free-text footnotes).
        if any('undecodable' in p for p in problems):
            skipped.append(f"{f.name}: {sum('undecodable' in p for p in problems)} unreadable glyphs")
            continue
        box = f.stem
        old = prev.get(box, {})
        data['box'] = box
        data['location'] = old.get('location') or boxes.get(box, {}).get('l', '')
        data['district'] = data.pop('card_district')
        data['division'] = data.pop('card_division')
        if data['district'] is None:
            data['district'] = old.get('district')
        if data['division'] is None:
            data['division'] = old.get('division')
        out[box] = {k: data[k] for k in ('box', 'location', 'district', 'division',
                                         'respond_to_fire', 'covering_assignments')}
        if problems:
            flagged.append((box, problems))
        if n % 250 == 0:
            print(f"  {n}/{len(files)}", flush=True)

    print(f"\nparsed {len(out)} cards, skipped {len(skipped)}, flagged {len(flagged)}")
    for b, p in flagged[:40]:
        print(f"   {b}: {p[0]}")
    Path('parse_skipped.txt').write_text('\n'.join(skipped), encoding='utf-8')
    Path(args.out).write_text(json.dumps(out, separators=(',', ':')), encoding='utf-8')
    print(f"wrote {args.out}")


if __name__ == '__main__':
    main()
