"""Procedural benchmark routes (deterministic). Recorded routes from the viewer sit beside them."""
import zlib

import numpy as np
from scipy.interpolate import CubicSpline

from gpsfree.paths import ROUTES
from gpsfree.trajectory import Route, horizontal_distance

PLATFORMS = {
    "drone": {"speed": (5.0, 15.0), "agl": (30.0, 150.0), "length": 3000.0, "segment": 150.0, "max_turn": np.radians(50)},
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


ROUTE_GENERATOR_VERSION = 3


def generate_route(world, platform: str, name: str, seed: int, style: dict | None = None) -> Route:
    """style (drone): speed_mps, length_m, agl_m [lo, hi] override the platform defaults."""
    cfg = dict(PLATFORMS[platform])
    style = style or {}
    cfg["speed"] = style.get("speed_mps", cfg["speed"])
    cfg["length"] = style.get("length_m", cfg["length"])
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
    speed = rng.uniform(*cfg["speed"]) if isinstance(cfg["speed"], tuple) else cfg["speed"]
    t = np.arange(0, arc[-1] / speed, 0.1)
    xy = np.c_[np.interp(t * speed, arc, dense[:, 0]), np.interp(t * speed, arc, dense[:, 1])]

    if platform == "drone":
        top = world.height(xy)
        agl = rng.uniform(*style.get("agl_m", cfg["agl"]))
        # Smooth the cruise altitude over ~400 m windows but never below agl above anything.
        k = int(200 / (speed * 0.1))
        pad = np.pad(top, k, mode="edge")
        clearance = np.array([pad[i:i + 2 * k + 1].max() for i in range(len(top))])
        z = np.convolve(np.pad(clearance, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "valid") + agl
        z = np.maximum(z, top + 20)
    else:
        z = world.height(xy, ground_only=True) + DEVICE_HEIGHT
    vel = np.gradient(xy, t, axis=0)
    yaw = np.unwrap(np.arctan2(vel[:, 1], vel[:, 0]))
    return Route(name, world.id, platform, t, np.c_[xy, z], yaw, source="generated")


def generate_all(world, per_platform: int = 3, platforms=None, oversample: int = 4):
    """Legacy fixed route files in benchmark/routes (not used by the scenario suite). Draws oversample x
    per_platform candidates per platform and keeps per_platform of them spread evenly over terrain ruggedness
    (mean ground slope under the path), so flat and rugged ground are both covered."""
    paths = []
    for platform in platforms or PLATFORMS:
        for old in (ROUTES / world.id).glob(f"{platform}-gen*.json"):
            old.unlink()
        cands = [generate_route(world, platform, "", seed=stable_seed(world.id, platform, k))
                 for k in range(per_platform * oversample)]
        rugged = np.array([ruggedness(world, r) for r in cands])
        keep = np.argsort(rugged)[np.linspace(0, len(cands) - 1, per_platform).round().astype(int)]
        for k, i in enumerate(keep):
            route = cands[i]
            route.name = f"{platform}-gen{k}"
            path = ROUTES / world.id / f"{route.name}.json"
            route.save(path)
            paths.append(path)
    return paths


def ruggedness(world, route) -> float:
    xy = route.position[::10, :2]
    ground = world.height(xy, ground_only=True)
    return float(np.mean(np.abs(np.diff(ground)) / np.maximum(np.linalg.norm(np.diff(xy, axis=0), axis=1), 1e-6)))


def scenario_route(scenario: dict, index: int, world) -> Route:
    """Route `index` of a scenario: generated deterministically once, then cached in data/routes."""
    from gpsfree.paths import DATA
    sid = scenario["id"]
    path = DATA / "routes" / f"v{ROUTE_GENERATOR_VERSION}" / sid / f"r{index:02d}.json"
    if path.exists():
        return Route.load(path)
    route = generate_route(world, scenario["platform"], f"{sid}-r{index:02d}",
                           seed=stable_seed("route", sid, index), style=scenario.get("route"))
    route.save(path)
    return route


def stable_seed(*parts) -> int:
    return zlib.crc32("/".join(map(str, parts)).encode())
