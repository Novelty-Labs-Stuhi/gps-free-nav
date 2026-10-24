"""Procedural benchmark routes (deterministic). Recorded routes from the viewer sit beside them."""
import zlib

import numpy as np
from scipy.interpolate import CubicSpline

from gpsfree.paths import ROUTES
from gpsfree.trajectory import Route, horizontal_distance

PLATFORMS = {
    "drone": {"speed": 10.0, "length": 3000.0, "segment": 150.0, "max_turn": np.radians(50)},
    "walker": {"speed": 1.4, "length": 1200.0, "segment": 15.0, "max_turn": np.radians(70)},
}
DEVICE_HEIGHT = 1.2  # walker carries the sensors at hand height


def _walker_ok(world, a, b):
    seg = b[:2] - a[:2]
    length = np.linalg.norm(seg)
    g = world.height([a[:2], b[:2]], ground_only=True)
    top = world.height([b[:2]])
    if top[0] - g[1] > 0.5 or abs(g[1] - g[0]) / length > 0.25:
        return False  # on a building, or too steep
    origin = np.r_[a[:2], g[0] + DEVICE_HEIGHT]
    return world.raycast([origin], [np.r_[seg / length, 0]], length + 2)[0] == np.inf


def generate_route(world, platform: str, name: str, seed: int) -> Route:
    cfg = PLATFORMS[platform]
    rng = np.random.default_rng(seed)
    limit = world.radius * 0.8
    for _attempt in range(50):
        p = rng.uniform(-0.3, 0.3, 2) * world.radius
        if platform == "walker" and not _walker_ok(world, np.r_[p, 0], np.r_[p + 1, 0]):
            continue
        heading = rng.uniform(0, 2 * np.pi)
        pts = [p.copy()]
        stuck = 0
        while len(pts) * cfg["segment"] < cfg["length"] and stuck < 200:
            turn = rng.uniform(-cfg["max_turn"], cfg["max_turn"])
            if np.linalg.norm(p) > limit:  # steer back towards the centre
                to_c = np.arctan2(-p[1], -p[0])
                turn = np.angle(np.exp(1j * (to_c - heading))) * 0.5
            h = heading + turn
            q = p + cfg["segment"] * np.array([np.cos(h), np.sin(h)])
            if platform == "walker" and not _walker_ok(world, np.r_[p, 0], np.r_[q, 0]):
                heading += rng.uniform(-np.pi, np.pi)
                stuck += 1
                continue
            p, heading = q, h
            pts.append(p.copy())
        if len(pts) * cfg["segment"] >= cfg["length"]:
            break
    pts = np.array(pts)

    # Constant-speed resampling of a smooth curve through the waypoints.
    chord = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    curve = CubicSpline(chord, pts)
    dense = curve(np.linspace(0, chord[-1], int(chord[-1] / 0.5)))
    arc = horizontal_distance(np.c_[dense, np.zeros(len(dense))])
    t = np.arange(0, arc[-1] / cfg["speed"], 0.1)
    xy = np.c_[np.interp(t * cfg["speed"], arc, dense[:, 0]), np.interp(t * cfg["speed"], arc, dense[:, 1])]

    if platform == "drone":
        top = world.height(xy)
        agl = rng.uniform(40, 100)
        # Smooth the cruise altitude over ~20 s windows but never below agl above anything.
        k = 200
        pad = np.pad(top, k, mode="edge")
        clearance = np.array([pad[i:i + 2 * k + 1].max() for i in range(len(top))])
        z = np.convolve(np.pad(clearance, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "valid") + agl
        z = np.maximum(z, top + 20)
    else:
        z = world.height(xy, ground_only=True) + DEVICE_HEIGHT
    vel = np.gradient(xy, t, axis=0)
    yaw = np.unwrap(np.arctan2(vel[:, 1], vel[:, 0]))
    return Route(name, world.id, platform, t, np.c_[xy, z], yaw, source="generated")


def generate_all(world, per_platform: int = 3):
    paths = []
    for platform in PLATFORMS:
        for k in range(per_platform):
            name = f"{platform}-gen{k}"
            route = generate_route(world, platform, name, seed=stable_seed(world.id, platform, k))
            path = ROUTES / world.id / f"{name}.json"
            route.save(path)
            paths.append(path)
    return paths


def stable_seed(*parts) -> int:
    return zlib.crc32("/".join(map(str, parts)).encode())
