"""Terrain matching with a particle filter. The prior map is turned into a height grid (the map tensor). Each echo
frame is a small point cloud: beam ranges rotated into the world by the INS attitude. Every particle slides that
cloud to its own position and heading, and is weighted by how well the cloud lies on the terrain (vertical residual
to the grid). Between frames the particles move with the INS acceleration (USE_ACCEL) or at constant velocity.
Height comes from the barometer. Particle state: x, y, vx, vy and a yaw offset to the INS heading."""
import numpy as np

from gpsfree.evaluate import load_algorithm

N = 1000
GRID_M = 10.0
SIGMA_M = 4.0  # vertical residual: range noise + grid interpolation on steep ground
CLIP = 3.0  # residuals beyond CLIP sigma count as outliers
INFO_BEAMS = 10  # a frame counts as at most this many independent beams (neighbouring points are correlated)

_grids = {}


def height_grid(m):
    if m.id not in _grids:
        (x0, y0, _), (x1, y1, _) = m.bounds
        X, Y = np.meshgrid(np.arange(x0, x1, GRID_M), np.arange(y0, y1, GRID_M))
        _grids[m.id] = (x0, y0, m.height(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape))
    return _grids[m.id]


class Navigator(load_algorithm("imu_deadreckoning")):
    USE_ACCEL = True  # False: particles move at constant velocity, the accelerometer only gives tilt
    TILT_TAU_S = None  # pull the attitude's tilt towards gravity with this time constant (None = gyro only)
    Q_V = 0.2  # velocity random walk, m/s/sqrt(s)
    Q_YAW = 0.002  # heading random walk, rad/sqrt(s)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.rng = np.random.default_rng(0)
        self.grid = height_grid(ctx.map)
        self.dirs = ctx.sensors["echo"]["directions"]
        self.temper = min(1.0, INFO_BEAMS / len(self.dirs))
        s = ctx.start
        self.pxy = s.position[:2] + self.rng.normal(0, 1.0, (N, 2))
        self.pv = np.tile(s.velocity[:2], (N, 1))
        self.psi = np.zeros(N)
        self.w = np.full(N, 1 / N)
        self.t_prop = s.t
        self.dv = np.zeros(2)  # world acceleration integrated since t_prop (shared by all particles)
        self.dp = np.zeros(2)

    def on_imu(self, t, acc, gyro):
        t_prev = self.last_t
        super().on_imu(t, acc, gyro)
        if t_prev is None:
            return
        dt = t - t_prev
        if self.TILT_TAU_S:
            g = self.R @ acc
            axis = np.cross(g / np.linalg.norm(g), [0, 0, 1.0])
            th = np.linalg.norm(axis)
            if th > 1e-9:
                k = axis / th
                K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
                e = np.arcsin(min(th, 1.0)) * dt / self.TILT_TAU_S
                self.R = (np.eye(3) + np.sin(e) * K + (1 - np.cos(e)) * K @ K) @ self.R
        if self.USE_ACCEL:
            a = self.last_a[:2]
            self.dp += self.dv * dt + 0.5 * a * dt * dt
            self.dv += a * dt

    def _propagate(self, t):
        T = t - self.t_prop
        c, s = np.cos(self.psi), np.sin(self.psi)
        rot = lambda d: np.c_[c * d[0] - s * d[1], s * d[0] + c * d[1]]
        self.pxy += self.pv * T + rot(self.dp)
        self.pv += rot(self.dv) + self.rng.normal(0, self.Q_V * np.sqrt(T), (N, 2))
        self.psi += self.rng.normal(0, self.Q_YAW * np.sqrt(T), N)
        self.t_prop, self.dv, self.dp = t, np.zeros(2), np.zeros(2)

    def _terrain(self, x, y):
        x0, y0, H = self.grid
        u, v = (x - x0) / GRID_M, (y - y0) / GRID_M
        j = np.clip(np.floor(u).astype(int), 0, H.shape[1] - 2)
        i = np.clip(np.floor(v).astype(int), 0, H.shape[0] - 2)
        fu, fv = np.clip(u - j, 0, 1), np.clip(v - i, 0, 1)
        return (H[i, j] * (1 - fu) * (1 - fv) + H[i, j + 1] * fu * (1 - fv)
                + H[i + 1, j] * (1 - fu) * fv + H[i + 1, j + 1] * fu * fv)

    def on_echo(self, t, ranges):
        if self.R is None:
            return
        self._propagate(t)
        ok = np.isfinite(ranges)
        if not ok.any():
            return
        rel = (self.dirs[ok] * ranges[ok, None]) @ self.R.T  # beam endpoints relative to the body, world axes
        c, s = np.cos(self.psi)[:, None], np.sin(self.psi)[:, None]
        x = self.pxy[:, :1] + c * rel[:, 0] - s * rel[:, 1]
        y = self.pxy[:, 1:] + s * rel[:, 0] + c * rel[:, 1]
        r = (self.p[2] + rel[:, 2]) - self._terrain(x, y)
        ll = -0.5 * np.minimum((r / SIGMA_M) ** 2, CLIP ** 2).sum(1) * self.temper
        logw = np.log(self.w + 1e-300) + ll
        w = np.exp(logw - logw.max())
        self.w = w / w.sum()
        if 1 / np.sum(self.w ** 2) < N / 2:
            self._resample()

    def _resample(self):
        idx = np.searchsorted(np.cumsum(self.w), (self.rng.random() + np.arange(N)) / N).clip(0, N - 1)
        self.pxy = self.pxy[idx] + self.rng.normal(0, 0.5, (N, 2))
        self.pv = self.pv[idx] + self.rng.normal(0, 0.05, (N, 2))
        self.psi = self.psi[idx] + self.rng.normal(0, 0.002, N)
        self.w = np.full(N, 1 / N)

    def estimate(self):
        lag = (self.last_t or self.t_prop) - self.t_prop
        xy = self.w @ (self.pxy + self.pv * lag) + self.dp
        return np.r_[xy, self.p[2]]
