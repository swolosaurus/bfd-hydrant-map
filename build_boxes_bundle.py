"""
build_boxes_bundle.py — fetch every BFD fire alarm box from Boston gisportal,
gzip into boston_boxes.json.gz so the PWA can find the nearest box to any
incident lat/lng entirely offline.

Run: python build_boxes_bundle.py
Output: boston_boxes.json (raw, gitignored) + boston_boxes.json.gz (shipped)
"""
import gzip
import json
import urllib.parse
import urllib.request

URL = "https://gisportal.boston.gov/arcgis/rest/services/PublicSafety/OpenData/MapServer/1/query"
PAGE = 2000


def fetch_page(offset):
    qs = urllib.parse.urlencode({
        "where": "1=1",
        "outFields": "BOX,LOCATION,DISTRICT",
        "outSR": "4326",
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": PAGE,
        "orderByFields": "OBJECTID",
    })
    with urllib.request.urlopen(f"{URL}?{qs}", timeout=60) as r:
        return json.load(r)


def main():
    out = []
    offset = 0
    while True:
        page = fetch_page(offset)
        feats = page.get("features", [])
        if not feats:
            break
        for f in feats:
            box = f["attributes"].get("BOX")
            if not box:
                continue
            geom = f.get("geometry") or {}
            x, y = geom.get("x"), geom.get("y")
            if x is None or y is None:
                continue
            out.append({
                "n": str(box),
                "y": round(y, 6),
                "x": round(x, 6),
                "l": (f["attributes"].get("LOCATION") or "").strip(),
                "d": (f["attributes"].get("DISTRICT") or "").strip(),
            })
        if not page.get("exceededTransferLimit"):
            break
        offset += PAGE

    payload = json.dumps(out, separators=(",", ":"))
    with open("boston_boxes.json", "w") as f:
        f.write(payload)
    with gzip.open("boston_boxes.json.gz", "wb", compresslevel=9) as f:
        f.write(payload.encode())

    import os
    print(f"Boxes: {len(out)}")
    print(f"Raw: {len(payload):,} bytes")
    print(f"Gzipped: {os.path.getsize('boston_boxes.json.gz'):,} bytes")


if __name__ == "__main__":
    main()
