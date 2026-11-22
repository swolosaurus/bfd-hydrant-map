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


# Revere is the one town with two useful layers. The Fire Department's field
# map (FieldApps/FD_Hydrant_Map layer 5) has 920 in-service hydrants, make and
# model on all of them, and static pressure on ~390 - but flow on only 188.
# The Water Department's editing layer has fewer hydrants and no hardware data,
# yet carries flow on 232 and the NFPA cap colour in `comments`. They share
# `facilityid`, so we take the FD layer as the base and backfill from WS.

_REVERE_WS_CACHE = None
_REVERE_WS_URL = ("https://gis.revere.org/arcgis/rest/services/"
                  "WS_Hydrants/WS_Hydrant_Edit/MapServer/1/query")

_CAP_COLORS = {"red", "orange", "green", "blue", "yellow", "white", "purple", "black"}


def _flow_num(v):
    """Pull a GPM number out of '604 GPM', '1060' or ''. Returns '' or 'NNN GPM'."""
    s = _clean(v)
    if not s:
        return ""
    digits = ""
    for ch in s:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    return _gpm(digits) if digits else ""


def _cap_color(v):
    """First NFPA colour word in a free-text comment, title-cased."""
    s = _clean(v)
    if not s:
        return ""
    word = ""
    for ch in s:
        if ch.isalpha():
            word += ch
        else:
            break
    return word.title() if word.lower() in _CAP_COLORS else ""


def _revere_ws_lookup():
    """facilityid -> {flow, color} from Revere's water-department layer."""
    global _REVERE_WS_CACHE
    if _REVERE_WS_CACHE is not None:
        return _REVERE_WS_CACHE
    out, offset = {}, 0
    try:
        while True:
            q = urllib.parse.urlencode({
                "where": "1=1",
                "outFields": "facilityid,full_flow,comments",
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": 2000,
                "orderByFields": "OBJECTID",
                "f": "json",
            })
            with urllib.request.urlopen(_REVERE_WS_URL + "?" + q, timeout=60) as r:
                feats = json.loads(r.read().decode("utf-8")).get("features", [])
            if not feats:
                break
            for f in feats:
                a = f.get("attributes") or {}
                fid = _clean(a.get("facilityid"))
                if fid:
                    out[fid] = {"flow": _flow_num(a.get("full_flow")),
                                "color": _cap_color(a.get("comments"))}
            offset += len(feats)
    except Exception as e:                      # non-fatal: FD data still stands
        print(f"  Revere      WS backfill unavailable ({e}) - using FD fields only")
    _REVERE_WS_CACHE = out
    print(f"  Revere      WS backfill loaded {len(out)} records")
    return out


def map_revere(a):
    fid = _clean(a.get("facilityid"))
    ws = _revere_ws_lookup().get(fid, {})
    flow = _flow_num(a.get("full_flow")) or ws.get("flow", "")
    color = ws.get("color", "")
    psi = _clean(a.get("static_pressure"))
    psi = f"{psi} PSI" if psi else ""
    # Fall back to hardware only when there is no operational data. Revere
    # records "Unknown" as a literal model value, which is noise, not detail.
    hw = [x for x in (_clean(a.get("make")), _clean(a.get("model")))
          if x and x.lower() != "unknown"]
    m = _join(flow, color, psi) or _join(*hw)
    return fid, m, "Revere"


def map_brookline(a):
    m = _join(a.get("Manufacturer"), a.get("Model"))
    return _clean(a.get("ID")), m, "Brookline"


def map_newton(a):
    m = _join(_gpm(a.get("flow")), a.get("cap_color"))
    return _clean(a.get("facilityid")), m, "Newton"


def map_milton(a):
    m = _join(a.get("HydrantMake"), a.get("HydrantModel"))
    return _clean(a.get("HYD_ID")), m, "Milton"


def map_everett(a):
    # assessflow is categorical (High / Normal / Low), not GPM.
    # A non-Operable status is surfaced as a warning - a hard-to-turn hydrant
    # is still worth knowing about, but the crew should know before pulling up.
    bits = []
    flow = _clean(a.get("assessflow"))
    if flow and flow.lower() not in ("none",):
        bits.append(f"{flow} flow")
    status = _clean(a.get("opstatus"))
    if status and status.lower() not in ("operable", "unknown"):
        bits.append(status)
    if not bits:
        bits.append(_join(a.get("hydmfg"), a.get("hydmodel")))
    ident = _clean(a.get("hydrant_id")) or _clean(a.get("point_id"))
    return ident, " - ".join(b for b in bits if b), "Everett"


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
        # Fire Department field map - more hydrants and richer attributes than
        # the water-department layer; see map_revere for the WS backfill.
        "url": "https://gis.revere.org/arcgis/rest/services/FieldApps/FD_Hydrant_Map/MapServer/5/query",
        "out_fields": "facilityid,full_flow,static_pressure,make,model,lifecyclestatus",
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
    {
        # Consultant-published 2020 water-system shapefile (AGOL user
        # John.Ahern_INE), NOT an official city service - Everett publishes
        # nothing itself. Verified in-town coords. Treat as fragile.
        # NOTE: this layer's OID field is FID, not OBJECTID.
        "name": "Everett",
        "url": "https://services3.arcgis.com/16nyMR1mdhEaLG41/arcgis/rest/services/Everett_Water2020_shp/FeatureServer/4/query",
        "out_fields": "hydrant_id,point_id,street_nam,hydmfg,hydmodel,assessflow,opstatus",
        "where": "1=1",
        "order_by": "FID",
        "skip_if": lambda a: _clean(a.get("opstatus")).lower() == "inoperable",
        "page_size": 2000,
        "map": map_everett,
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
        "orderByFields": src.get("order_by", "OBJECTID"),
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


def write_bundle(hydrants, t0):
    out_path = Path(__file__).parent / "boston_hydrants.json"
    print(f"\nWriting {len(hydrants)} hydrants to {out_path.name}...")
    with out_path.open("w") as fh:
        json.dump(hydrants, fh, separators=(",", ":"))
    gz_path = out_path.with_suffix(".json.gz")
    with out_path.open("rb") as srcf, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        dst.writelines(srcf)
    print(f"  raw:  {out_path.stat().st_size/1024:7.1f} KB")
    print(f"  gzip: {gz_path.stat().st_size/1024:7.1f} KB")
    print(f"  done in {int(time.time()-t0)}s")


def merge_one(name):
    """Refresh a single town in place, leaving the other towns alone.

    Municipal endpoints go down - Somerville and Brookline were both
    unreachable on 2026-10-22. A full rebuild refuses to write a partial
    bundle, which is correct, but it means one dead host blocks adding a
    new town. This re-fetches just `name` and splices it into the bundle.

        python build_hydrants_bundle.py --only Everett
    """
    t0 = time.time()
    src = next((x for x in SOURCES if x["name"].lower() == name.lower()), None)
    if not src:
        print(f"Unknown source {name!r}. Known: {[x['name'] for x in SOURCES]}")
        return 1
    out_path = Path(__file__).parent / "boston_hydrants.json"
    if not out_path.exists():
        print("No existing bundle to merge into - run a full build first.")
        return 1
    with out_path.open() as fh:
        existing = json.load(fh)

    fresh = fetch_source(src)
    if not fresh:
        print(f"{name}: fetched 0 records - refusing to merge.")
        return 1

    towns = {src["name"]}
    if src["name"] == "Dedham":
        towns.add("Westwood")          # Dedham's layer carries both
    kept = [h for h in existing if h.get("s") not in towns]
    dropped = len(existing) - len(kept)
    label = "/".join(sorted(towns))
    print(f"\n  existing {len(existing)} - dropped {dropped} old {label} + added {len(fresh)} = {len(kept)+len(fresh)}")
    write_bundle(kept + fresh, t0)
    return 0


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--only":
        return merge_one(sys.argv[2])
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

    write_bundle(all_hydrants, t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
