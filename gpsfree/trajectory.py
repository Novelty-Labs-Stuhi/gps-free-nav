"""Ground-truth motion: a route file -> smooth, differentiable 6-DoF trajectory."""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import make_smoothing_spline
from scipy.spatial.transform import Rotation

G = 9.80665


@dataclass
class Route:
    name: str
    world: str
    platform: str          # "drone" | "walker"
    t: np.ndarray          # (T,)
    position: np.ndarray   # (T, 3) ENU
    yaw: np.ndarray        # (T,) CCW from east
    source: str = "generated"

    @classmethod
    def load(cls, path: Path):
        d = json.loads(Path(path).read_text())
        return cls(d["name"], d["world"], d["platform"], np.array(d["t"]), np.array(d["position"]), np.array(d["yaw"]), d.get("source", "recorded"))

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "name": self.name, "world": self.world, "platform": self.platform, "source": self.source,
            "t": np.round(self.t, 3).tolist(), "position": np.round(self.position, 2).tolist(), "yaw": np.round(self.yaw, 4).tolist(),
        }))


class Trajectory:
    """Smoothing splines through a route; sample() gives consistent p, v, a, attitude, body rates."""

    def __init__(self, route: Route):
        self.route = route
        t = route.t
        self._pos = [make_smoothing_spline(t, route.position[:, i]) for i in range(3)]
        self._yaw = make_smoothing_spline(t, np.unwrap(route.yaw))
        self.t0, self.t1 = float(t[0]), float(t[-1])

    def sample(self, t):
        t = np.asarray(t, dtype=np.float64)
        p = np.stack([s(t) for s in self._pos], 1)
        v = np.stack([s.derivative(1)(t) for s in self._pos], 1)
        a = np.stack([s.derivative(2)(t) for s in self._pos], 1)
        yaw = self._yaw(t)
        if self.route.platform == "drone":
            rot = _multirotor_attitude(a, yaw)
        else:
            rot = Rotation.from_euler("z", yaw[:, None])
        return {"t": t, "p": p, "v": v, "a": a, "yaw": yaw, "rot": rot}

    def body_rates(self, rot: Rotation, dt: float):
        """Body angular velocity at each sample (central difference of attitude)."""
        d = (rot[:-2].inv() * rot[2:]).as_rotvec() / (2 * dt)
        return np.vstack([d[:1], d, d[-1:]])


def _multirotor_attitude(a, yaw):
    """A multirotor tilts so its thrust (body z) points along a - g."""
    thrust = a + np.array([0, 0, G])
    zb = thrust / np.linalg.norm(thrust, axis=1, keepdims=True)
    xc = np.c_[np.cos(yaw), np.sin(yaw), np.zeros_like(yaw)]
    yb = np.cross(zb, xc)
    yb /= np.linalg.norm(yb, axis=1, keepdims=True)
    xb = np.cross(yb, zb)
    return Rotation.from_matrix(np.stack([xb, yb, zb], axis=2))


def horizontal_distance(p):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))]
