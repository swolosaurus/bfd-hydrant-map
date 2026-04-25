"""
Download every building footprint in Boston, simplify, write as a compact
JSON bundle (`boston_buildings.json`) for the BFD Hydrant Map PWA to load
once and cache forever.

Output format: a flat array of objects, each:
    { "b": [minLat, minLng, maxLat, maxLng], "r": [[[x,y],...]] }
The "b" bbox is precomputed for fast spatial filtering on the client.

Run whenever Boston updates the dataset (~yearly):
    python build_buildings_bundle.py
Then commit `boston_buildings.json` to the repo and bump BUNDLE_VER in index.html.
"""
import gzip
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://gis.bostonplans.org/hosting/rest/services/Boston_Buildings/FeatureServer/9/query"
PAGE_SIZE = 2000


def fetch_count() -> int:
    url = f"{BASE}?where=1%3D1&returnCountOnly=true&f=json"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)["count"]


def fetch_page(offset: int) -> list:
    params = {
        "where": "1=1",
        "outFields": "OBJECTID",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "5",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "orderByFields": "OBJECTID",
        "f": "json",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.load(r).get("features", [])
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Page {offset} failed after retries: {last_err}")


def main() -> None:
    total = fetch_count()
    print(f"Total buildings: {total}")

    out_features = []
    offset = 0
    t0 = time.time()
    while offset < total:
        page = fetch_page(offset)
        if not page:
            break
        for f in page:
            rings = f.get("geometry", {}).get("rings")
            if not rings or not rings[0]:
                continue
            min_lat = min_lng = float("inf")
            max_lat = max_lng = float("-inf")
            for ring in rings:
                for x, y in ring:
                    if y < min_lat:
                        min_lat = y
                    if y > max_lat:
                        max_lat = y
                    if x < min_lng:
                        min_lng = x
                    if x > max_lng:
                        max_lng = x
            out_features.append(
                {
                    "b": [
                        round(min_lat, 5),
                        round(min_lng, 5),
                        round(max_lat, 5),
                        round(max_lng, 5),
                    ],
                    "r": rings,
                }
            )
        offset += len(page)
        elapsed = time.time() - t0
        rate = offset / elapsed if elapsed else 0
        eta = (total - offset) / rate if rate else 0
        print(
            f"  {offset:>6}/{total}  ({rate:.0f}/s, ETA {int(eta):>4}s)",
            flush=True,
        )

    out_path = Path(__file__).parent / "boston_buildings.json"
    print(f"\nWriting {len(out_features)} features to {out_path.name}...")
    with out_path.open("w") as fh:
        json.dump(out_features, fh, separators=(",", ":"))

    raw_size = out_path.stat().st_size
    gz_path = out_path.with_suffix(".json.gz")
    with out_path.open("rb") as src, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        dst.writelines(src)
    gz_size = gz_path.stat().st_size

    print(f"  raw:  {raw_size/1024/1024:6.2f} MB  ({out_path.name})")
    print(f"  gzip: {gz_size /1024/1024:6.2f} MB  ({gz_path.name})")
    print(f"  done in {int(time.time()-t0)}s")


if __name__ == "__main__":
    sys.exit(main())
