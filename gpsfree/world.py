import json
from functools import cached_property

import numpy as np
import trimesh

from gpsfree.paths import WORLDS


class World:
    """Baked world geometry in ENU meters with fast batched raycasting (Embree)."""

    def __init__(self, world_id: str):
        self.id = world_id
        folder = WORLDS / world_id
        if not (folder / "world.npz").exists():
            from gpsfree.cli import fetch_world
            fetch_world(world_id)  # first use: download + bake (~1 min), cached in data/
        self.meta = json.loads((folder / "meta.json").read_text())
        d = np.load(folder / "world.npz")
        self.ground = trimesh.Trimesh(d["ground_v"], d["ground_f"], process=False)
        self.buildings = trimesh.Trimesh(d["buildings_v"], d["buildings_f"], process=False) if len(d["buildings_f"]) else None
        self.mesh = trimesh.util.concatenate([m for m in (self.ground, self.buildings) if m is not None])
        self.radius = self.meta["radius"]

    @cached_property
    def _rays(self):
        return trimesh.ray.ray_pyembree.RayMeshIntersector(self.mesh)

    @cached_property
    def _ground_rays(self):
        return trimesh.ray.ray_pyembree.RayMeshIntersector(self.ground)

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
        """Surface height under each (x, y): top of buildings unless ground_only."""
        xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
        top = self.meta["bounds"][1][2] + 100
        o = np.c_[xy, np.full(len(xy), top)]
        d = self.raycast(o, np.tile([0, 0, -1.0], (len(xy), 1)), ground_only=ground_only)
        return top - d
