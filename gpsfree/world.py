"""Baked worlds: the TRUE world the sensors measure, and the MAP a drone carries.

truth = terrain + buildings + trees (worlds/bake.py).
map   = what a scenario says a real drone would have: terrain with smooth height error, buildings with
        per-building height error and some missing, never trees (World.map_world)."""
import json
from functools import cached_property

import numpy as np
import trimesh

from gpsfree.paths import WORLDS


class Surface:
    """A mesh with fast batched ray casting (Embree)."""

    def __init__(self, mesh, ground=None):
        self.mesh = mesh
        self._ground = ground if ground is not None else mesh

    @cached_property
    def _rays(self):
        return trimesh.ray.ray_pyembree.RayMeshIntersector(self.mesh)

    @cached_property
    def _ground_rays(self):
        return self._rays if self._ground is self.mesh else trimesh.ray.ray_pyembree.RayMeshIntersector(self._ground)

    def raycast(self, origins, directions, max_range=np.inf, ground_only=False):
        """Distance along each (unit) ray to the first surface; inf where nothing is hit."""
        origins = np.asarray(origins, dtype=np.float64).reshape(-1, 3)
        directions = np.asarray(directions, dtype=np.float64).reshape(-1, 3)
        directions = directions / np.linalg.norm(directions, axis=1, keepdims=True)
        rays = self._ground_rays if ground_only else self._rays
        locs, ray_idx, _ = rays.intersects_location(origins, directions, multiple_hits=False)
        dist = np.full(len(origins), np.inf)
        if len(ray_idx):
            dist[ray_idx] = np.linalg.norm(locs - origins[ray_idx], axis=1)
        dist[dist > max_range] = np.inf
        return dist

    def height(self, xy, ground_only=False):
        """Surface height under each (x, y): top of buildings and trees unless ground_only."""
        xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
        top = self.top + 100
        o = np.c_[xy, np.full(len(xy), top)]
        d = self.raycast(o, np.tile([0, 0, -1.0], (len(xy), 1)), ground_only=ground_only)
        return top - d


class World(Surface):
    """The true world in ENU metres."""

    def __init__(self, world_id: str):
        from gpsfree.worlds.bake import BAKE_VERSION, tree_mesh
        self.id = world_id
        folder = WORLDS / world_id
        meta_path = folder / "meta.json"
        if not meta_path.exists() or json.loads(meta_path.read_text()).get("bake_version") != BAKE_VERSION:
            from gpsfree.cli import fetch_world
            fetch_world(world_id)  # first use: download + bake, cached in data/
        self.meta = json.loads(meta_path.read_text())
        d = np.load(folder / "world.npz")
        self.ground = trimesh.Trimesh(d["ground_v"], d["ground_f"], process=False)
        self.buildings_v, self.buildings_f = d["buildings_v"].astype(np.float64), d["buildings_f"]
        self.buildings_id = d["buildings_id"] if "buildings_id" in d else np.full(len(self.buildings_f), -1)
        self.trees = d["trees"].astype(np.float64) if "trees" in d else np.zeros((0, 5))
        tv, tf = tree_mesh(self.trees)
        parts = [self.ground]
        if len(self.buildings_f):
            parts.append(trimesh.Trimesh(self.buildings_v, self.buildings_f, process=False))
        if len(tf):
            parts.append(trimesh.Trimesh(tv, tf, process=False))
        super().__init__(trimesh.util.concatenate(parts), self.ground)
        self.radius = self.meta["radius"]
        self.top = self.meta["bounds"][1][2]
        self._maps = {}

    def map_world(self, spec: dict | None, seed: int = 0) -> Surface:
        """The scenario's map (cached per spec). spec keys, all optional:
        terrain_error_m / terrain_error_corr_m  smooth random height error on the terrain
        buildings (bool, default true)          include buildings at all
        building_height_error_m                 per-building roof height error (sigma)
        building_missing_frac                   share of buildings absent from the map
        trees (bool, default false)             include the true trees (an idealised map)"""
        spec = spec or {}
        key = (json.dumps(spec, sort_keys=True), seed)
        if key in self._maps:
            return self._maps[key]
        rng = np.random.default_rng(seed)
        gv = self.ground.vertices.copy()
        if spec.get("terrain_error_m"):
            gv[:, 2] += smooth_field(gv[:, :2], spec["terrain_error_m"], spec.get("terrain_error_corr_m", 150.0),
                                     self.meta["bounds"], rng)
        ground = trimesh.Trimesh(gv, self.ground.faces, process=False)
        parts = [ground]
        if spec.get("buildings", True) and len(self.buildings_f):
            ids = np.unique(self.buildings_id)
            keep = rng.random(len(ids)) >= spec.get("building_missing_frac", 0.0)
            dz = dict(zip(ids, rng.normal(0, spec.get("building_height_error_m", 0.0), len(ids))))
            fmask = np.isin(self.buildings_id, ids[keep]) | (self.buildings_id < 0)
            bv = self.buildings_v.copy()
            if spec.get("building_height_error_m"):
                # move each building's roof (its upper vertices) by that building's error
                vid = np.full(len(bv), -1)
                vid[self.buildings_f.ravel()] = np.repeat(self.buildings_id, 3)
                roof = np.zeros(len(bv), bool)
                for b in ids:
                    m = vid == b
                    if m.any():
                        z = bv[m, 2]
                        roof[np.flatnonzero(m)[z > z.min() + 0.5]] = True
                bv[roof, 2] += np.vectorize(lambda b: dz.get(b, 0.0))(vid[roof])
            if fmask.any():
                parts.append(trimesh.Trimesh(bv, self.buildings_f[fmask], process=False))
        if spec.get("trees") and len(self.trees):
            from gpsfree.worlds.bake import tree_mesh
            tv, tf = tree_mesh(self.trees)
            parts.append(trimesh.Trimesh(tv, tf, process=False))
        m = Surface(trimesh.util.concatenate(parts), ground)
        m.id, m.meta, m.radius, m.top = self.id, self.meta, self.radius, self.top
        self._maps[key] = m
        return m


def smooth_field(xy, sigma, corr_m, bounds, rng, cell=None):
    """Gaussian-smoothed random field with standard deviation sigma and correlation length ~corr_m."""
    from scipy.ndimage import gaussian_filter
    cell = cell or max(corr_m / 4, 5.0)
    (x0, y0, _), (x1, y1, _) = bounds
    nx, ny = int((x1 - x0) / cell) + 2, int((y1 - y0) / cell) + 2
    f = gaussian_filter(rng.normal(size=(ny, nx)), corr_m / cell)
    f *= sigma / f.std()
    ix = np.clip(((xy[:, 0] - x0) / cell).astype(int), 0, nx - 1)
    iy = np.clip(((xy[:, 1] - y0) / cell).astype(int), 0, ny - 1)
    return f[iy, ix]
