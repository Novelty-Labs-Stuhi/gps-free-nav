"""Turn raw downloads into one world: data/worlds/<id>/{world.npz, world.glb, meta.json[, texture.jpg]}.

world.npz (ENU, used by the Python sim) and world.glb (glTF Y-up, used by the viewer)
hold the same two meshes: "ground" and "buildings".
"""
import json
import math
import struct
from pathlib import Path

import meshoptimizer
import numpy as np
from PIL import Image

from gpsfree.geo import ecef_to_enu_matrix

Image.MAX_IMAGE_PIXELS = None


# ---------------------------------------------------------------- city (3DBAG)
def _read_glb(path: Path):
    d = path.read_bytes()
    n = struct.unpack("<I", d[12:16])[0]
    gltf = json.loads(d[20:20 + n])
    bin_off = 20 + n + 8
    return gltf, d[bin_off:]


def _buffer_view(gltf, binary, idx):
    bv = gltf["bufferViews"][idx]
    ext = bv.get("extensions", {}).get("EXT_meshopt_compression")
    if ext is None:
        off = bv.get("byteOffset", 0)
        return binary[off:off + bv["byteLength"]], bv.get("byteStride")
    src = binary[ext["byteOffset"]:ext["byteOffset"] + ext["byteLength"]]
    if ext.get("filter", "NONE") != "NONE":
        raise NotImplementedError(f"meshopt filter {ext['filter']}")
    count, stride = ext["count"], ext["byteStride"]
    if ext["mode"] == "ATTRIBUTES":
        out = meshoptimizer.decode_vertex_buffer(count, stride, src)
    elif ext["mode"] == "TRIANGLES":
        out = meshoptimizer.decode_index_buffer(count, stride, src)
    else:
        out = meshoptimizer.decode_index_sequence(count, stride, src)
    return np.asarray(out).tobytes(), stride


_DTYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _accessor(gltf, binary, idx):
    acc = gltf["accessors"][idx]
    raw, stride = _buffer_view(gltf, binary, acc["bufferView"])
    dt = np.dtype(_DTYPES[acc["componentType"]])
    nc = _NCOMP[acc["type"]]
    stride = stride or dt.itemsize * nc
    off = acc.get("byteOffset", 0)
    buf = np.frombuffer(raw, dtype=np.uint8)
    rows = np.lib.stride_tricks.as_strided(buf[off:], shape=(acc["count"], nc * dt.itemsize), strides=(stride, 1))
    arr = np.ascontiguousarray(rows).view(dt).reshape(acc["count"], nc).astype(np.float64)
    if acc.get("normalized"):
        arr = np.maximum(arr / np.iinfo(dt).max, -1.0)
    return arr


def _city_tile(path: Path, to_enu: np.ndarray):
    gltf, binary = _read_glb(path)
    verts, faces, n = [], [], 0

    def visit(node_idx, parent):
        node = gltf["nodes"][node_idx]
        m = np.array(node["matrix"]).reshape(4, 4).T if "matrix" in node else np.eye(4)
        m = parent @ m
        if "mesh" in node:
            for prim in gltf["meshes"][node["mesh"]]["primitives"]:
                nonlocal n
                p = _accessor(gltf, binary, prim["attributes"]["POSITION"])
                p = (m @ np.c_[p, np.ones(len(p))].T).T[:, :3]
                p = np.c_[p[:, 0], -p[:, 2], p[:, 1]]  # glTF Y-up -> ECEF Z-up (3D Tiles convention)
                p = (to_enu @ np.c_[p, np.ones(len(p))].T).T[:, :3]
                idx = _accessor(gltf, binary, prim["indices"]).astype(np.int64).reshape(-1, 3)
                verts.append(p)
                faces.append(idx + n)
                n += len(p)
        for c in node.get("children", []):
            visit(c, m)

    for root in gltf["scenes"][gltf.get("scene", 0)]["nodes"]:
        visit(root, np.eye(4))
    return np.concatenate(verts), np.concatenate(faces)


def _fill_grid(h: np.ndarray):
    """Fill NaN cells by repeatedly averaging known 4-neighbours."""
    h = h.copy()
    for _ in range(5000):
        missing = np.isnan(h)
        if not missing.any():
            break
        p = np.pad(h, 1, constant_values=np.nan)
        nb = np.stack([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
        cnt = (~np.isnan(nb)).sum(0)
        avg = np.where(cnt > 0, np.nansum(nb, 0) / np.maximum(cnt, 1), np.nan)
        h[missing] = avg[missing]
    return h


def _grid_mesh(xs, ys, h):
    """Regular grid (rows = y, cols = x) -> vertices, triangles."""
    gx, gy = np.meshgrid(xs, ys)
    v = np.c_[gx.ravel(), gy.ravel(), h.ravel()]
    nx = len(xs)
    r, c = np.meshgrid(np.arange(len(ys) - 1), np.arange(nx - 1), indexing="ij")
    a = (r * nx + c).ravel()
    f = np.r_[np.c_[a, a + 1, a + nx + 1], np.c_[a, a + nx + 1, a + nx]]
    return v, f


def bake_city(cfg, out: Path, raw: dict, cell=20.0):
    to_enu = ecef_to_enu_matrix(cfg["lat"], cfg["lon"])
    parts = [_city_tile(out / "tiles" / t, to_enu) for t in raw["tiles"]]
    off = np.cumsum([0] + [len(v) for v, _ in parts[:-1]])
    bv = np.concatenate([v for v, _ in parts])
    bf = np.concatenate([f + o for (_, f), o in zip(parts, off)])

    # 3DBAG has no terrain: put ground through the lowest floor faces in each cell.
    tri = bv[bf]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    down = nrm[:, 2] / (np.linalg.norm(nrm, axis=1) + 1e-12) < -0.9
    floor_pts = tri[down].reshape(-1, 3)
    half = cfg["radius"] * 1.2
    xs = np.arange(-half, half + cell, cell)
    col = np.clip(np.round((floor_pts[:, 0] + half) / cell).astype(int), 0, len(xs) - 1)
    row = np.clip(np.round((floor_pts[:, 1] + half) / cell).astype(int), 0, len(xs) - 1)
    h = np.full((len(xs), len(xs)), np.inf)
    np.minimum.at(h, (row, col), floor_pts[:, 2])
    h[np.isinf(h)] = np.nan
    h = _fill_grid(h) - 0.05
    gv, gf = _grid_mesh(xs, xs, h)

    z0 = h[len(xs) // 2, len(xs) // 2]
    gv[:, 2] -= z0
    bv[:, 2] -= z0
    return {"ground": (gv, gf, None), "buildings": (bv, bf)}


# ------------------------------------------------------------------- terrain
def _mercator_px(lat, lon, z):
    n = 2 ** z * 256
    return (lon + 180) / 360 * n, (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n


def _mosaic(folder: Path, r, ext):
    cols, rows = r["x1"] - r["x0"] + 1, r["y1"] - r["y0"] + 1
    img = Image.new("RGB", (cols * 256, rows * 256))
    for x in range(r["x0"], r["x1"] + 1):
        for y in range(r["y0"], r["y1"] + 1):
            img.paste(Image.open(folder / f"{x}_{y}.{ext}").convert("RGB"), ((x - r["x0"]) * 256, (y - r["y0"]) * 256))
    return img


def bake_terrain(cfg, out: Path, raw: dict, step=15.0):
    elev, img = raw["elev"], raw.get("img")
    step = cfg.get("step_m", step)
    e = np.asarray(_mosaic(out / "elev", elev, "png"), dtype=np.float64)
    hmap = e[..., 0] * 256 + e[..., 1] + e[..., 2] / 256 - 32768

    def sample(px, py):
        px = np.clip(px - 0.5, 0, hmap.shape[1] - 1.001)
        py = np.clip(py - 0.5, 0, hmap.shape[0] - 1.001)
        x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
        tx, ty = px - x0, py - y0
        return ((hmap[y0, x0] * (1 - tx) + hmap[y0, x0 + 1] * tx) * (1 - ty)
                + (hmap[y0 + 1, x0] * (1 - tx) + hmap[y0 + 1, x0 + 1] * tx) * ty)

    xs = np.arange(-cfg["radius"], cfg["radius"] + step, step)
    gx, gy = np.meshgrid(xs, xs)
    m_per_deg = math.pi * 6378137.0 / 180
    lat = cfg["lat"] + gy / m_per_deg
    lon = cfg["lon"] + gx / (m_per_deg * math.cos(math.radians(cfg["lat"])))
    ex, ey = _mercator_px(lat, lon, elev["z"])
    h = sample(ex - elev["x0"] * 256, ey - elev["y0"] * 256)
    cx, cy = _mercator_px(np.array(cfg["lat"]), np.array(cfg["lon"]), elev["z"])
    h0 = float(sample(cx - elev["x0"] * 256, cy - elev["y0"] * 256))
    if cfg.get("despike_m"):  # zoom-15 tiles have void pixels: pits far below the local median are refilled
        from scipy.ndimage import median_filter
        bad = h < median_filter(h, size=9) - cfg["despike_m"]
        if bad.any():
            h = _fill_grid(np.where(bad, np.nan, h))
    if cfg.get("sea_level"):
        h, h0 = np.maximum(h, 0.0), max(h0, 0.0)
    h -= h0
    gv, gf = _grid_mesh(xs, xs, h)

    uv = np.zeros((gv.shape[0], 2))
    if img:
        tex = _mosaic(out / "img", img, "jpg")
        ix, iy = _mercator_px(lat, lon, img["z"])
        uv = np.c_[((ix - img["x0"] * 256) / tex.width).ravel(), ((iy - img["y0"] * 256) / tex.height).ravel()]
        tex.save(out / "texture.jpg", quality=85)
    return {"ground": (gv, gf, uv), "buildings": (np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)), "grid": (xs, h)}


# --------------------------------------------------------------------- output
def _write_glb(path: Path, meshes: dict, texture: str | None):
    """Minimal GLB writer: one node per mesh, ENU -> glTF Y-up (x, z, -y)."""
    blobs, views, accessors, gl_meshes, nodes = [], [], [], [], []
    offset = 0

    def add(arr, target, comp, typ, minmax=False):
        nonlocal offset
        data = arr.tobytes()
        pad = (-len(data)) % 4
        blobs.append(data + b"\0" * pad)
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        offset += len(data) + pad
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": len(arr), "type": typ}
        if minmax:
            acc["min"], acc["max"] = arr.min(0).tolist(), arr.max(0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    for name, mesh in meshes.items():
        v, f = mesh[0], mesh[1]
        if len(f) == 0:
            continue
        uv = mesh[2] if len(mesh) > 2 else None
        p = np.c_[v[:, 0], v[:, 2], -v[:, 1]].astype(np.float32)
        attrs = {"POSITION": add(p, 34962, 5126, "VEC3", minmax=True)}
        if uv is not None:
            attrs["TEXCOORD_0"] = add(uv.astype(np.float32), 34962, 5126, "VEC2")
        prim = {"attributes": attrs, "indices": add(f.astype(np.uint32).ravel(), 34963, 5125, "SCALAR")}
        if uv is not None and texture:
            prim["material"] = 0
        gl_meshes.append({"name": name, "primitives": [prim]})
        nodes.append({"name": name, "mesh": len(gl_meshes) - 1})

    gltf = {
        "asset": {"version": "2.0", "generator": "gpsfree"},
        "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes, "meshes": gl_meshes, "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": offset}],
    }
    if texture:
        gltf["images"] = [{"uri": texture}]
        gltf["textures"] = [{"source": 0}]
        gltf["materials"] = [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0, "roughnessFactor": 1}}]
    js = json.dumps(gltf).encode()
    js += b" " * ((-len(js)) % 4)
    body = b"".join(blobs)
    glb = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(body))
    glb += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(body), 0x004E4942) + body
    path.write_bytes(glb)


BAKE_VERSION = 2


def _ground_sampler(xs, h):
    """Bilinear height on the baked terrain grid (rows = y, cols = x, both = xs)."""
    step = xs[1] - xs[0]

    def f(x, y):
        fx = np.clip((np.asarray(x) - xs[0]) / step, 0, len(xs) - 1.001)
        fy = np.clip((np.asarray(y) - xs[0]) / step, 0, len(xs) - 1.001)
        x0, y0 = fx.astype(int), fy.astype(int)
        tx, ty = fx - x0, fy - y0
        return ((h[y0, x0] * (1 - tx) + h[y0, x0 + 1] * tx) * (1 - ty) + (h[y0 + 1, x0] * (1 - tx) + h[y0 + 1, x0 + 1] * tx) * ty)
    return f


def _to_enu(cfg):
    m_per_deg = math.pi * 6378137.0 / 180
    c = math.cos(math.radians(cfg["lat"]))
    return lambda ll: np.c_[(np.asarray(ll)[:, 0] - cfg["lon"]) * m_per_deg * c, (np.asarray(ll)[:, 1] - cfg["lat"]) * m_per_deg]


def _osm_buildings(cfg, osm, ground, rng):
    """Extrude OSM footprints: earcut roof + walls, base sunk 1 m under the lowest corner.
    Heights: OSM tag, else a seeded guess by building type. Returns verts, faces, per-face building id."""
    import mapbox_earcut as earcut
    from shapely.geometry import Polygon
    enu, half = _to_enu(cfg), cfg["radius"] * 1.05
    V, F, ids, n = [], [], [], 0
    guess = {"house": (5, 8), "detached": (5, 8), "garage": (2.5, 3.5), "shed": (2.5, 3.5), "apartments": (12, 30),
             "commercial": (8, 20), "industrial": (6, 14), "retail": (5, 12), "church": (12, 30)}
    for bid, (ring, height, kind) in enumerate(osm["buildings"]):
        xy = enu(ring)[:-1]
        if len(xy) < 3 or np.abs(xy).max() > half:
            continue
        poly = Polygon(xy)
        if not poly.is_valid or poly.area < 4:
            continue
        if not poly.exterior.is_ccw:
            xy = xy[::-1]
        lo, hi = guess.get(kind, (4, 12))
        hgt = height if height and 1 < height < 400 else rng.uniform(lo, hi)
        g = ground(xy[:, 0], xy[:, 1])
        base, top = g.min() - 1.0, g.max() + hgt
        tri = earcut.triangulate_float64(xy, np.array([len(xy)], dtype=np.uint32)).reshape(-1, 3)
        k = len(xy)
        verts = np.r_[np.c_[xy, np.full(k, base)], np.c_[xy, np.full(k, top)]]
        i = np.arange(k)
        j = (i + 1) % k
        walls = np.r_[np.c_[i, j, j + k], np.c_[i, j + k, i + k]]
        faces = np.r_[tri + k, walls]
        V.append(verts)
        F.append(faces + n)
        ids.append(np.full(len(faces), bid))
        n += len(verts)
    if not V:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), np.zeros(0, dtype=np.int64)
    return np.concatenate(V), np.concatenate(F), np.concatenate(ids)


MAX_TREES = 250_000


def _osm_trees(cfg, osm, ground, rng):
    """Tree list (x, y, ground z, height, crown radius) from forest polygons plus seeded scattered trees.
    Forest density follows the world's canopy cover."""
    from shapely import contains_xy
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    t = cfg.get("trees")
    if not t:
        return np.zeros((0, 5))
    enu, R = _to_enu(cfg), cfg["radius"]
    area_box = box(-R, -R, R, R)
    r_mean = float(np.mean(t["crown_r_m"]))
    pts = []
    polys = []
    for rings in osm["forests"]:
        p = Polygon(enu(rings[0]), [enu(h) for h in rings[1:]])
        if not p.is_valid:
            p = p.buffer(0)
        if not p.is_empty:
            polys.append(p.intersection(area_box))
    if polys:
        forest = unary_union(polys)
        n = int(t["forest_cover"] * forest.area / (np.pi * r_mean ** 2))
        if n:
            x0, y0, x1, y1 = forest.bounds
            cand = rng.uniform([x0, y0], [x1, y1], (int(n * (x1 - x0) * (y1 - y0) / max(forest.area, 1) * 1.2) + 10, 2))
            inside = cand[contains_xy(forest, cand[:, 0], cand[:, 1])]
            pts.append(inside[:n])
    n_sc = int(t.get("scatter_per_ha", 0) * (2 * R) ** 2 / 1e4)
    if n_sc:
        pts.append(rng.uniform(-R, R, (n_sc, 2)))
    xy = np.concatenate(pts) if pts else np.zeros((0, 2))
    xy = xy[(np.abs(xy) < R).all(1)]
    if len(xy) > MAX_TREES:
        xy = xy[rng.choice(len(xy), MAX_TREES, replace=False)]
    h = rng.uniform(*t["height_m"], len(xy))
    r = rng.uniform(*t["crown_r_m"], len(xy))
    return np.c_[xy, ground(xy[:, 0], xy[:, 1]), h, r]


def tree_mesh(trees):
    """Square pyramids: crown from 25% of the height to the top (4 faces per tree, open base)."""
    if len(trees) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    x, y, g, h, r = trees.T
    zb, zt = g + 0.25 * h, g + h
    ring = np.stack([np.c_[x + r, y, zb], np.c_[x, y + r, zb], np.c_[x - r, y, zb], np.c_[x, y - r, zb], np.c_[x, y, zt]], 1)
    k = np.arange(len(trees))[:, None, None] * 5
    faces = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])[None] + k
    return ring.reshape(-1, 3), faces.reshape(-1, 3)


def bake(world_id: str, cfg: dict, out: Path, raw: dict):
    meshes = (bake_city if cfg["kind"] == "city" else bake_terrain)(cfg, out, raw)
    gv, gf = meshes["ground"][:2]
    bv, bf = meshes["buildings"]
    bid = np.full(len(bf), -1)
    trees = np.zeros((0, 5))
    if cfg.get("layers"):
        from gpsfree.worlds.overture import fetch_layers
        osm = fetch_layers(world_id, cfg)
        ground = _ground_sampler(*meshes["grid"])
        rng = np.random.default_rng(zlib_seed(world_id))
        bv, bf, bid = _osm_buildings(cfg, osm, ground, rng)
        trees = _osm_trees(cfg, osm, ground, rng)
        meshes["buildings"] = (bv, bf)
    tv, tf = tree_mesh(trees)
    meshes["trees"] = (tv, tf)
    np.savez_compressed(out / "world.npz", ground_v=gv.astype(np.float32), ground_f=gf.astype(np.int32),
                        buildings_v=bv.astype(np.float32), buildings_f=bf.astype(np.int32), buildings_id=bid.astype(np.int32),
                        trees=trees.astype(np.float32))
    meshes.pop("grid", None)
    texture = "texture.jpg" if (out / "texture.jpg").exists() else None
    _write_glb(out / "world.glb", meshes, texture)
    allv = np.r_[gv, bv, tv]
    meta = {"id": world_id, **cfg, "raw": raw, "bake_version": BAKE_VERSION,
            "bounds": [allv.min(0).tolist(), allv.max(0).tolist()],
            "triangles": int(len(gf) + len(bf) + len(tf)), "buildings": int(len(set(bid.tolist())) - (1 if -1 in bid else 0)),
            "trees": int(len(trees))}
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def zlib_seed(*parts):
    import zlib
    return zlib.crc32("/".join(map(str, parts)).encode())
