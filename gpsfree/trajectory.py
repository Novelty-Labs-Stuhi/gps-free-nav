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


SMOOTH_LAM = 0.01      # fixed smoothing; matches scipy's per-route GCV choice to ~1 cm at a fraction of the cost
DRAG_PER_M = 0.01      # quadratic drag of a small multirotor: 1 m/s^2 at 10 m/s airspeed (~6 deg tilt)
GUST_TAU_S = 3.0       # gust correlation time
PATH_OMEGA, PATH_ZETA = 1.2, 0.8  # how stiffly the autopilot holds its planned path against gusts


class Wind:
    """Constant wind plus first-order Gauss-Markov gusts (3 axes, vertical at half strength)."""

    def __init__(self, cfg: dict | None, t0: float, t1: float, rng: np.random.Generator):
        self.t = np.arange(t0 - 1, t1 + 1, 0.1)
        if not cfg:
            self.mean, self.g = np.zeros(3), np.zeros((len(self.t), 3))
            return
        spd, ang = rng.uniform(*cfg["mean_mps"]), rng.uniform(0, 2 * np.pi)
        self.mean = np.array([spd * np.cos(ang), spd * np.sin(ang), 0.0])
        a = np.exp(-0.1 / GUST_TAU_S)
        w = rng.normal(0, 1, (len(self.t), 3)) * cfg["gust_mps"] * np.sqrt(1 - a * a) * np.array([1, 1, 0.5])
        g = np.zeros_like(w)
        g[0] = w[0] / np.sqrt(1 - a * a)
        for k in range(1, len(w)):
            g[k] = a * g[k - 1] + w[k]
        self.g = g

    def __call__(self, t):
        t = np.asarray(t, float)
        return self.mean + np.stack([np.interp(t, self.t, self.g[:, i]) for i in range(3)], -1)

    def path_offset(self, t, drag_gain=2 * DRAG_PER_M * 10):
        """Displacement of the flown path from the plan: a damped autopilot driven by gust force."""
        x, v = np.zeros(3), np.zeros(3)
        out = np.zeros((len(self.t), 3))
        for k in range(1, len(self.t)):
            f = drag_gain * self.g[k] - 2 * PATH_ZETA * PATH_OMEGA * v - PATH_OMEGA ** 2 * x
            v = v + f * 0.1
            x = x + v * 0.1
            out[k] = x
        return np.stack([np.interp(t, self.t, out[:, i]) for i in range(3)], -1)


class Trajectory:
    """Smoothing splines through a route; sample() gives consistent p, v, a, attitude, body rates.
    With wind, the flown path is the planned route plus the gust response, and the multirotor
    tilts against drag on its airspeed. `planned` keeps the route as commanded."""

    def __init__(self, route: Route, wind: dict | None = None, seed: int = 0):
        self.route = route
        t = route.t
        self.planned = route.position
        self.wind = Wind(wind, float(t[0]), float(t[-1]), np.random.default_rng(seed))
        pos = route.position + (self.wind.path_offset(t) if wind else 0.0)
        self._pos = [make_smoothing_spline(t, pos[:, i], lam=SMOOTH_LAM) for i in range(3)]
        self._yaw = make_smoothing_spline(t, np.unwrap(route.yaw), lam=SMOOTH_LAM)
        self.t0, self.t1 = float(t[0]), float(t[-1])

    def sample(self, t):
        t = np.asarray(t, dtype=np.float64)
        p = np.stack([s(t) for s in self._pos], 1)
        v = np.stack([s.derivative(1)(t) for s in self._pos], 1)
        a = np.stack([s.derivative(2)(t) for s in self._pos], 1)
        yaw = self._yaw(t)
        air = v - self.wind(t)
        if self.route.platform == "drone":
            drag = -DRAG_PER_M * np.linalg.norm(air, axis=1, keepdims=True) * air
            rot = _multirotor_attitude(a - drag, yaw)
        else:
            rot = Rotation.from_euler("z", yaw[:, None])
        return {"t": t, "p": p, "v": v, "a": a, "yaw": yaw, "rot": rot, "airspeed": np.linalg.norm(air, axis=1)}

    def body_rates(self, rot: Rotation, dt: float):
        """Body angular velocity at each sample (central difference of attitude)."""
        d = (rot[:-2].inv() * rot[2:]).as_rotvec() / (2 * dt)
        return np.vstack([d[:1], d, d[-1:]])


def _multirotor_attitude(a, yaw):
    """A multirotor tilts so its thrust (body z) points along a - g, where a is the acceleration the
    thrust must supply (the true acceleration minus drag)."""
    thrust = a + np.array([0, 0, G])
    zb = thrust / np.linalg.norm(thrust, axis=1, keepdims=True)
    xc = np.c_[np.cos(yaw), np.sin(yaw), np.zeros_like(yaw)]
    yb = np.cross(zb, xc)
    yb /= np.linalg.norm(yb, axis=1, keepdims=True)
    xb = np.cross(yb, zb)
    return Rotation.from_matrix(np.stack([xb, yb, zb], axis=2))


def horizontal_distance(p):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1))]


def path_length(p):
    """Cumulative 3D arc length: climbs and descents count as distance travelled."""
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
