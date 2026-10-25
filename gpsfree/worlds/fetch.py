"""Download raw world data into data/worlds/<id>/ (skips files already present)."""
import json
import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from gpsfree.geo import ecef

BAG3D = "https://3dbag.fsn1.your-objectstorage.com/v20250903/cesium3dtiles/lod22/"
ELEV_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
IMG_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ELEV_ZOOM, IMG_ZOOM = 14, 16


def _get(url, dst: Path | None = None):
    req = urllib.request.Request(url, headers={"User-Agent": "gpsfree-sim/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if dst is None:
        return data
    tmp = dst.with_suffix(dst.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dst)


def _download_all(jobs):
    jobs = [(u, d) for u, d in jobs if not d.exists()]
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda j: _get(*j), jobs))


def fetch_city(cfg, out: Path):
    center = ecef(cfg["lat"], cfg["lon"], 45)
    leaves = []

    def walk(node):
        box = node["boundingVolume"]["box"]
        half_diag = sum(math.hypot(*box[i:i + 3]) for i in (3, 6, 9))
        if math.dist(box[:3], center) > half_diag + cfg["radius"]:
            return
        uri = node.get("content", {}).get("uri")
        children = node.get("children", [])
        if uri and uri.endswith(".json"):
            walk(json.loads(_get(BAG3D + uri))["root"])
        elif uri and not children:
            leaves.append(uri)
        for c in children:
            walk(c)

    walk(json.loads(_get(BAG3D + "tileset.json"))["root"])
    (out / "tiles").mkdir(parents=True, exist_ok=True)
    _download_all([(BAG3D + u, out / "tiles" / u.replace("/", "_")) for u in leaves])
    return {"tiles": sorted(u.replace("/", "_") for u in leaves)}


def tile_xy(lat, lon, z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def tile_range(cfg, z):
    dlat = math.degrees(cfg["radius"] / 6378137.0)
    dlon = dlat / math.cos(math.radians(cfg["lat"]))
    x0, y0 = tile_xy(cfg["lat"] + dlat, cfg["lon"] - dlon, z)
    x1, y1 = tile_xy(cfg["lat"] - dlat, cfg["lon"] + dlon, z)
    return {"z": z, "x0": int(x0), "y0": int(y0), "x1": int(x1), "y1": int(y1)}


def fetch_terrain(cfg, out: Path):
    elev = tile_range(cfg, cfg.get("elev_zoom", ELEV_ZOOM))
    img = tile_range(cfg, IMG_ZOOM) if cfg.get("imagery", True) else None
    jobs = []
    for kind, r, url, ext in (("elev", elev, ELEV_URL, "png"), ("img", img, IMG_URL, "jpg")):
        if r is None:
            continue
        (out / kind).mkdir(parents=True, exist_ok=True)
        for x in range(r["x0"], r["x1"] + 1):
            for y in range(r["y0"], r["y1"] + 1):
                jobs.append((url.format(z=r["z"], x=x, y=y), out / kind / f"{x}_{y}.{ext}"))
    _download_all(jobs)
    return {"elev": elev, "img": img}
