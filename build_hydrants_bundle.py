"""
Download every fire hydrant in Boston, save as a compact gzipped bundle
(`boston_hydrants.json.gz`) for the BFD Hydrant Map PWA to load once and
cache forever.

Output format: a flat array of objects, each:
    { "i": FACILITY_ID, "m": HYDRANT_MODEL, "s": SERVICE_AREA, "y": lat, "x": lng }

Run whenever Boston refreshes the hydrant dataset:
    python build_hydrants_bundle.py
Then commit `boston_hydrants.json.gz` and bump HYDRANT_BUNDLE_VER in index.html.
"""
import gzip
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://gisportal.boston.gov/arcgis/rest/services/PublicSafety/OpenData/MapServer/0/query"
PAGE_SIZE = 2000


def fetch_count() -> int:
    url = f"{BASE}?where=1%3D1&returnCountOnly=true&f=json"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)["count"]


def fetch_page(offset: int) -> list:
    params = {
        "where": "1=1",
        "outFields": "FACILITY_I,HYDRANT_MO,SERVICE_AR",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "6",
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
    print(f"Total hydrants: {total}")

    out = []
    offset = 0
    t0 = time.time()
    while offset < total:
        page = fetch_page(offset)
        if not page:
            break
        for f in page:
            geom = f.get("geometry") or {}
            x = geom.get("x")
            y = geom.get("y")
            if x is None or y is None:
                continue
            attrs = f.get("attributes") or {}
            out.append(
                {
                    "i": attrs.get("FACILITY_I") or "",
                    "m": attrs.get("HYDRANT_MO") or "",
                    "s": attrs.get("SERVICE_AR") or "",
                    "y": round(y, 6),
                    "x": round(x, 6),
                }
            )
        offset += len(page)
        elapsed = time.time() - t0
        rate = offset / elapsed if elapsed else 0
        eta = (total - offset) / rate if rate else 0
        print(f"  {offset:>6}/{total}  ({rate:.0f}/s, ETA {int(eta):>3}s)", flush=True)

    out_path = Path(__file__).parent / "boston_hydrants.json"
    print(f"\nWriting {len(out)} hydrants to {out_path.name}...")
    with out_path.open("w") as fh:
        json.dump(out, fh, separators=(",", ":"))
    raw_size = out_path.stat().st_size
    gz_path = out_path.with_suffix(".json.gz")
    with out_path.open("rb") as src, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        dst.writelines(src)
    gz_size = gz_path.stat().st_size

    print(f"  raw:  {raw_size/1024:7.1f} KB  ({out_path.name})")
    print(f"  gzip: {gz_size /1024:7.1f} KB  ({gz_path.name})")
    print(f"  done in {int(time.time()-t0)}s")


if __name__ == "__main__":
    sys.exit(main())
