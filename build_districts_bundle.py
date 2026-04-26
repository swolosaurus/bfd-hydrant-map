"""
build_districts_bundle.py — fetch BFD fire districts from Boston gisportal,
simplify, gzip into boston_districts.json.gz for offline point-in-polygon
lookup in the PWA.

Run: python build_districts_bundle.py
Output: boston_districts.json (raw, gitignored) + boston_districts.json.gz (shipped)
"""
import gzip
import json
import urllib.parse
import urllib.request

URL = "https://gisportal.boston.gov/arcgis/rest/services/PublicSafety/OpenData/MapServer/3/query"
PARAMS = {
    "where": "1=1",
    "outFields": "DISTRICT",
    "returnGeometry": "true",
    "outSR": "4326",
    "f": "json",
}


def fetch():
    qs = urllib.parse.urlencode(PARAMS)
    with urllib.request.urlopen(f"{URL}?{qs}", timeout=60) as r:
        return json.load(r)


def round_ring(ring, p=5):
    return [[round(x, p), round(y, p)] for x, y in ring]


def main():
    raw = fetch()
    out = []
    for f in raw["features"]:
        district = int(f["attributes"]["DISTRICT"])
        if district == 999:
            # Skip the dummy "999" district (typically out-of-city / harbor)
            continue
        rings = f["geometry"]["rings"]
        rings = [round_ring(r) for r in rings]
        # Bounding box for fast prefilter (minLat, minLng, maxLat, maxLng)
        all_pts = [pt for ring in rings for pt in ring]
        lngs = [p[0] for p in all_pts]
        lats = [p[1] for p in all_pts]
        bbox = [min(lats), min(lngs), max(lats), max(lngs)]
        out.append({"d": district, "b": bbox, "r": rings})

    out.sort(key=lambda x: x["d"])
    payload = json.dumps(out, separators=(",", ":"))
    with open("boston_districts.json", "w") as f:
        f.write(payload)
    with gzip.open("boston_districts.json.gz", "wb", compresslevel=9) as f:
        f.write(payload.encode())

    raw_size = len(payload)
    import os
    gz_size = os.path.getsize("boston_districts.json.gz")
    print(f"Districts: {len(out)}")
    print(f"Raw: {raw_size:,} bytes")
    print(f"Gzipped: {gz_size:,} bytes")


if __name__ == "__main__":
    main()
