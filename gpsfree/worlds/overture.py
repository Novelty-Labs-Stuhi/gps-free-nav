"""Building footprints and forest cover for a world, from Overture Maps.

Overture publishes versioned GeoParquet on public S3, made for automated downloads (the public
Overpass servers refuse them). Buildings are mostly OpenStreetMap-derived (ODbL); land cover comes
from ESA WorldCover (CC BY 4.0). We pin RELEASE so a world always rebuilds identically, and keep a
compact extract in benchmark/worlds/<id>.json.gz, which is committed so CI never downloads it."""
import gzip
import json
import math

from gpsfree.paths import BENCHMARK

RELEASE = "2026-09-23.0"
EXTRACTS = BENCHMARK / "worlds"


def extract_path(world_id):
    return EXTRACTS / f"{world_id}.json.gz"


def bbox(cfg, margin=1.1):
    """(west, south, east, north) degrees around the world centre."""
    dlat = math.degrees(cfg["radius"] * margin / 6378137.0)
    dlon = dlat / math.cos(math.radians(cfg["lat"]))
    return cfg["lon"] - dlon, cfg["lat"] - dlat, cfg["lon"] + dlon, cfg["lat"] + dlat


def _rows(kind, box, columns):
    from overturemaps import core
    reader = core.record_batch_reader(kind, box, RELEASE, stac=True)
    if reader is None:
        return []
    out = []
    for batch in reader:
        d = batch.to_pydict()
        for i in range(batch.num_rows):
            out.append({c: d[c][i] for c in columns if c in d})
    return out


def _r6(coords):
    return [[round(x, 6), round(y, 6)] for x, y in coords]


def fetch_layers(world_id, cfg):
    """Download (once) and return {buildings: [[ring, height|None, class|None]], forests: [[shell, *holes]]}."""
    path = extract_path(world_id)
    if path.exists():
        return json.loads(gzip.decompress(path.read_bytes()))
    import shapely
    from shapely.geometry import box as sbox
    box = bbox(cfg)
    area = sbox(*box)
    out = {"release": RELEASE, "bbox": box, "buildings": [], "forests": []}
    if "buildings" in cfg["layers"]:
        for r in _rows("building", box, ["geometry", "height", "num_floors", "class"]):
            g = shapely.from_wkb(r["geometry"])
            h = r.get("height") or (3.0 * r["num_floors"] + 1.0 if r.get("num_floors") else None)
            for p in getattr(g, "geoms", [g]):
                if p.geom_type == "Polygon":
                    out["buildings"].append([_r6(p.exterior.coords), round(h, 1) if h else None, r.get("class")])
    if "forest" in cfg["layers"]:
        for r in _rows("land_cover", box, ["geometry", "subtype", "cartography"]):
            carto = r.get("cartography") or {}
            if r.get("subtype") != "forest" or (carto.get("max_zoom") or 99) < 13:
                continue  # keep only the most detailed generalisation level
            g = shapely.from_wkb(r["geometry"]).intersection(area)
            for p in getattr(g, "geoms", [g]):
                if p.geom_type == "Polygon" and not p.is_empty:
                    out["forests"].append([_r6(p.exterior.coords)] + [_r6(i.coords) for i in p.interiors])
    EXTRACTS.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(out, separators=(",", ":")).encode(), mtime=0))
    return out
