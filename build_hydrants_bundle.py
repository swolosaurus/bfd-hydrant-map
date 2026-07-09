"""
Download every fire hydrant in Boston + inner mutual-aid towns, save as one
compact gzipped bundle (`boston_hydrants.json.gz`) for the Hydrant Map PWA.

Output format: a flat array of objects, each:
    { "i": id, "m": model/details, "s": service-area-or-town, "y": lat, "x": lng }

Boston keeps its original field mapping (FACILITY_I / HYDRANT_MO / SERVICE_AR)
for zero regression. Mutual-aid towns put the TOWN NAME in "s" so the app's
hydrant rows show which system the hydrant belongs to, and pack the most
fire-useful attributes (flow GPM, color, make/model) into "m".

Endpoints verified 2026-07-10. Towns with NO public queryable data as of then:
Everett, Winthrop, Watertown, Quincy (all viewer-only GIS).

Run:  python build_hydrants_bundle.py
Then commit `boston_hydrants.json.gz` and bump HYDRANT_BUNDLE_VER in index.html.
"""
import gzip
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def _clean(v):
    """None-safe strip; returns '' for null-ish values."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("null", "none", "n/a", "0", "0.0") else s


def _gpm(v):
    """Format a flow value as 'NNNN GPM' or ''. """
    try:
        n = float(v)
        return f"{n:.0f} GPM" if n > 0 else ""
    except (TypeError, ValueError):
        return ""


def _join(*parts):
    return " ".join(p for p in (_clean(x) for x in parts) if p)


# ── Per-town attribute → {i, m} mappers ─────────────────────────────
# Each takes the raw attributes dict; lat/lng handled generically.

def map_boston(a):
    return a.get("FACILITY_I") or "", a.get("HYDRANT_MO") or "", a.get("SERVICE_AR") or ""


def map_cambridge(a):
    m = _join(_gpm(a.get("HYDRANT_GPM")), a.get("HYDRANT_COLOR"))
    return _clean(a.get("HYDRANT_ID")), m, "Cambridge"


def map_somerville(a):
    return _clean(a.get("Name")), _clean(a.get("PopupInfo")), "Somerville"


def map_chelsea(a):
    d = a.get("diameter")
    m = f'{d}" barrel' if d not in (None, 0, "0") else ""
    return _clean(a.get("assetid")), m, "Chelsea"


def map_revere(a):
    m = _join(_gpm(a.get("full_flow")), a.get("comments"))
    return _clean(a.get("facilityid")), m, "Revere"


def map_brookline(a):
    m = _join(a.get("Manufacturer"), a.get("Model"))
    return _clean(a.get("ID")), m, "Brookline"


def map_newton(a):
    m = _join(_gpm(a.get("flow")), a.get("cap_color"))
    return _clean(a.get("facilityid")), m, "Newton"


def map_milton(a):
    m = _join(a.get("HydrantMake"), a.get("HydrantModel"))
    return _clean(a.get("HYD_ID")), m, "Milton"


def map_dedham(a):
    m = _gpm(a.get("Avail_FireFlow"))
    town = _clean(a.get("MUNICIPALITY")) or "Dedham"
    return _clean(a.get("HydID")), m, town


# ── Source registry ──────────────────────────────────────────────────
# where: server-side filter (active-only where the field semantics are clear)
# skip_if: post-fetch predicate on attributes → True means drop the record
SOURCES = [
    {
        "name": "Boston",
        "url": "https://gisportal.boston.gov/arcgis/rest/services/PublicSafety/OpenData/MapServer/0/query",
        "out_fields": "FACILITY_I,HYDRANT_MO,SERVICE_AR",
        "where": "1=1",
        "page_size": 2000,
        "map": map_boston,
    },
    {
        "name": "Cambridge",
        "url": "https://services1.arcgis.com/WnzC35krSYGuYov4/arcgis/rest/services/Hydrants/FeatureServer/0/query",
        "out_fields": "HYDRANT_ID,HYDRANT_GPM,HYDRANT_COLOR,LIFECYCLESTATUS",
        "where": "1=1",
        "skip_if": lambda a: _clean(a.get("LIFECYCLESTATUS")).upper() not in ("", "ACT"),
        "page_size": 2000,
        "map": map_cambridge,
    },
    {
        "name": "Somerville",
        "url": "https://maps.somervillema.gov/arcgis/rest/services/Fire/MapServer/0/query",
        # this old 10.4 server 400s on named field lists — must use *
        "out_fields": "*",
        "where": "1=1",
        "page_size": 1000,
        "map": map_somerville,
    },
    {
        "name": "Chelsea",
        "url": "https://services9.arcgis.com/diuwWhOq89A0FdTw/arcgis/rest/services/Public_Facing_Water_Distribution_System_View/FeatureServer/501007/query",
        "out_fields": "assetid,diameter,lifecyclestatus",
        "where": "1=1",
        # lifecyclestatus 8 = In Service; keep unknown/null too, drop known-inactive
        "skip_if": lambda a: a.get("lifecyclestatus") not in (None, 8),
        "page_size": 2000,
        "map": map_chelsea,
    },
    {
        "name": "Revere",
        "url": "https://gis.revere.org/arcgis/rest/services/WS_Hydrants/WS_Hydrant_Edit/MapServer/1/query",
        "out_fields": "facilityid,comments,full_flow,lifecyclestatus",
        "where": "1=1",
        "skip_if": lambda a: _clean(a.get("lifecyclestatus")).upper() not in ("", "IS"),
        "page_size": 2000,
        "map": map_revere,
    },
    {
        "name": "Brookline",
        "url": "https://gisweb.brooklinema.gov/arcgis/rest/services/FireDepartment/MapServer/0/query",
        "out_fields": "ID,Manufacturer,Model,Inactive",
        "where": "1=1",
        "skip_if": lambda a: a.get("Inactive") not in (None, 0),
        "page_size": 1000,
        "map": map_brookline,
    },
    {
        "name": "Newton",
        # NOTE: esriGeometryMultipoint layer — geometry arrives as {"points": [[lng, lat]]}
        # operable values in the wild: "1" (2092), "Yes" (8), "0" (217), " " (403).
        # Drop only the known-inoperable "0"; keep unknowns.
        "url": "https://gisweb.newtonma.gov/server/rest/services/Data/MapServer/10/query",
        "out_fields": "facilityid,flow,cap_color,operable,Latitude,Longitude",
        "where": "1=1",
        # raw compare — _clean() maps "0" to "", which would defeat this filter
        "skip_if": lambda a: str(a.get("operable") or "").strip() == "0",
        "page_size": 2000,
        "map": map_newton,
    },
    {
        "name": "Milton",
        "url": "https://services9.arcgis.com/pDdkGgvmXNtQGbjV/arcgis/rest/services/MyMapService/FeatureServer/1/query",
        "out_fields": "HYD_ID,HydrantMake,HydrantModel",
        "where": "1=1",
        "page_size": 1000,
        "map": map_milton,
    },
    {
        "name": "Dedham",
        "url": "https://services1.arcgis.com/me41C4ZTLmDO2rPK/arcgis/rest/services/Hydrants/FeatureServer/0/query",
        "out_fields": "HydID,Avail_FireFlow,MUNICIPALITY",
        "where": "1=1",
        "page_size": 1000,
        "map": map_dedham,
    },
]

# Greater-Boston sanity window — any record outside this box is a data error
LAT_MIN, LAT_MAX = 42.10, 42.55
LNG_MIN, LNG_MAX = -71.40, -70.85


def fetch_json(url, timeout=120, retries=4):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hydrant-map-bundler"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{url[:100]}... failed after {retries} tries: {last_err}")


def fetch_count(src):
    q = urllib.parse.urlencode({"where": src["where"], "returnCountOnly": "true", "f": "json"})
    return fetch_json(f"{src['url']}?{q}")["count"]


def fetch_page(src, offset):
    params = {
        "where": src["where"],
        "outFields": src["out_fields"],
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "6",
        "resultOffset": offset,
        "resultRecordCount": src["page_size"],
        "orderByFields": "OBJECTID",
        "f": "json",
    }
    data = fetch_json(f"{src['url']}?{urllib.parse.urlencode(params)}")
    if "error" in data:
        raise RuntimeError(f"{src['name']} query error: {data['error']}")
    return data.get("features", [])


def extract_latlng(feature):
    """Handle point, multipoint, and attribute-based coordinates."""
    geom = feature.get("geometry") or {}
    attrs = feature.get("attributes") or {}
    x, y = geom.get("x"), geom.get("y")
    if x is None or y is None:
        pts = geom.get("points")
        if pts and len(pts) > 0 and len(pts[0]) >= 2:
            x, y = pts[0][0], pts[0][1]
    if x is None or y is None:
        # Newton fallback: Latitude/Longitude attribute fields
        try:
            y = float(attrs.get("Latitude"))
            x = float(attrs.get("Longitude"))
        except (TypeError, ValueError):
            return None, None
    return y, x


def fetch_source(src):
    total = fetch_count(src)
    out, skipped_inactive, skipped_geo = [], 0, 0
    offset = 0
    skip_if = src.get("skip_if")
    while offset < total:
        page = fetch_page(src, offset)
        if not page:
            break
        for f in page:
            attrs = f.get("attributes") or {}
            if skip_if and skip_if(attrs):
                skipped_inactive += 1
                continue
            lat, lng = extract_latlng(f)
            if lat is None or not (LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX):
                skipped_geo += 1
                continue
            i, m, s = src["map"](attrs)
            out.append({"i": i or "", "m": m or "", "s": s or "", "y": round(lat, 6), "x": round(lng, 6)})
        offset += len(page)
    print(f"  {src['name']:<11} kept {len(out):>6}  (raw {total}, inactive-skipped {skipped_inactive}, geo-skipped {skipped_geo})")
    return out


def main():
    t0 = time.time()
    all_hydrants = []
    failures = []
    for src in SOURCES:
        try:
            all_hydrants.extend(fetch_source(src))
        except Exception as e:
            failures.append((src["name"], str(e)[:200]))
            print(f"  {src['name']:<11} FAILED: {e}")

    if failures:
        print(f"\n⚠️  {len(failures)} source(s) failed — bundle NOT written (partial data is worse than stale data).")
        for name, err in failures:
            print(f"   {name}: {err}")
        return 1

    out_path = Path(__file__).parent / "boston_hydrants.json"
    print(f"\nWriting {len(all_hydrants)} hydrants to {out_path.name}...")
    with out_path.open("w") as fh:
        json.dump(all_hydrants, fh, separators=(",", ":"))
    gz_path = out_path.with_suffix(".json.gz")
    with out_path.open("rb") as srcf, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        dst.writelines(srcf)

    print(f"  raw:  {out_path.stat().st_size/1024:7.1f} KB")
    print(f"  gzip: {gz_path.stat().st_size/1024:7.1f} KB")
    print(f"  done in {int(time.time()-t0)}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
