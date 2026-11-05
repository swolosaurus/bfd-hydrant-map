"""
merge_running_cards.py — assemble running_cards.json from the v2.1 drop.

Three kinds of card end up in the bundle:
  * the 1,799 generated v2.1 cards, re-read pixel-exactly by
    parse_running_cards.py — these replace their v1.0 entries outright;
  * scanned cards whose PNG is byte-identical to the one we already had, whose
    v1.0 parse therefore still describes the card in front of you;
  * scanned cards that are new or were re-issued in this drop. Their layouts
    are one-off (harbour islands, Norfolk County mutual aid, the Logan ASHE
    card) and the template parser does not read them, so they get a stub with
    box and location only. The card image is still shipped and still opens —
    what we will not do is leave a superseded due-list on screen looking
    current.
"""
import hashlib, json, shutil
from pathlib import Path

SRC = Path("C:/Users/Administrator/Desktop/png")
CARDS = Path("running_cards")

# Read off the card headers; these boxes have no entry anywhere else.
NEW_LOCATIONS = {
    '761': "MOON ISLAND", '7611': "LONG ISLAND", '7612': "RAINSFORD'S ISLAND",
    '7613': "GALLOP'S ISLAND", '7614': "GEORGE'S ISLAND", '7615': "LOVELL'S ISLAND",
    '7616': "SPECTACLE ISLAND", '7617': "THOMPSON'S ISLAND", '7618': "PEDDOCK'S ISLAND",
    '762': "BOSTON INNER HARBOR (MYSTIC-TOBIN BRIDGE TO CASTLE ISLAND)",
    '763': "BOSTON OUTER HARBOR (CASTLE ISLAND TO BOSTON LIGHT)",
    '764': "NON-SPECIFIED OUTER ISLANDS",
    '8212': "MUTUAL AID TO BOSTON", '8252': "CANTON", '8253': "NORWOOD",
    '8254': "WESTWOOD",
    '642': "LOGAN SOUTH GATE - AIRCRAFT FIRE/CRASH RESPONSE",
    '646': "LOGAN NORTH GATE - AIRCRAFT FIRE/CRASH RESPONSE",
    '6311': "DEER ISLAND, SEWERAGE TREATMENT PLANT",
    '6422ashe': "LOGAN AIRPORT ACTIVE SHOOTER / HOSTILE EVENT RESPONSE (ASHE)",
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def changed_cards():
    """Boxes whose card image this drop replaced, per git. Hashing the working
    tree does not work once the images have been copied in, and git is the
    only record of what the previous card looked like."""
    import subprocess
    out = subprocess.run(["git", "status", "--porcelain", "--", str(CARDS)],
                         capture_output=True, text=True, check=True).stdout
    changed = set()
    for line in out.splitlines():
        state, _, path = line.partition(" ")
        name = Path(line[3:].strip().strip('"')).stem
        if name:
            changed.add(name)
    return changed


def main():
    parsed = json.loads(Path("running_cards_v21.json").read_text(encoding="utf-8"))
    old = json.loads(Path("running_cards.json").read_text(encoding="utf-8"))
    boxes = {str(b['n']): b for b in json.loads(Path("boston_boxes.json").read_text(encoding="utf-8"))}

    src = {p.stem: p for p in SRC.glob("*.[pP][nN][gG]")}
    changed = changed_cards()
    print(f"cards replaced in this drop (per git): {len(changed)}")
    out, carried, stubs = dict(parsed), [], []

    for box, p in sorted(src.items()):
        if box in out:
            continue
        if box in old and box not in changed:
            out[box] = old[box]; carried.append(box)
        else:
            prev = old.get(box, {})
            out[box] = {
                'box': box,
                'location': NEW_LOCATIONS.get(box) or prev.get('location') or boxes.get(box, {}).get('l', ''),
                'district': prev.get('district'),
                'division': prev.get('division'),
                'respond_to_fire': [],
                'covering_assignments': [],
            }
            stubs.append(box)

    print(f"v2.1 parsed : {len(parsed)}")
    print(f"carried v1.0: {len(carried)}  (scan unchanged in this drop)")
    print(f"stubbed     : {len(stubs)}  {stubs}")
    print(f"total       : {len(out)}")

    missing = [b for b, v in out.items() if not v['location']]
    if missing:
        print(f"WARNING no location for: {missing}")

    Path("running_cards.json").write_text(json.dumps(out, separators=(',', ':')), encoding="utf-8")
    import gzip
    payload = Path("running_cards.json").read_bytes()
    with gzip.open("running_cards.json.gz", "wb", compresslevel=9) as f:
        f.write(payload)
    print(f"wrote running_cards.json ({len(payload):,} B) and .gz "
          f"({Path('running_cards.json.gz').stat().st_size:,} B)")

    n = 0
    for box, p in src.items():
        dst = CARDS / f"{box}.png"
        if not dst.exists() or sha(dst) != sha(p):
            shutil.copyfile(p, dst); n += 1
    print(f"copied {n} card images into {CARDS}/  ({len(list(CARDS.glob('*.png')))} total)")


if __name__ == "__main__":
    main()
