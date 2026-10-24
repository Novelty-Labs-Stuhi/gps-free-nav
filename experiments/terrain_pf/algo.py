"""X1 terrain_pf: terrain matching with a particle filter, ported from Arsenii Chistiakov's ins_echo
(branch echo-lidar, commit 0b417f9) to the 12-scenario suite.

The prior map becomes a height grid. Each lidar frame is a small point cloud (beam ranges rotated into the
world by the INS attitude). Every particle slides that cloud to its own position and heading and is weighted by
how well the points lie on the terrain (vertical residual to the grid), tempered so one frame counts as at most
INFO_BEAMS independent beams. Particles move with the INS acceleration between frames; height comes from the
barometer. Particle state: x, y, vx, vy and a yaw offset to the INS heading.

Changes for the new suite: particles start spread over the told start uncertainty (spoofed handover), the RNG is
seeded per run, and the filter reports how sure it is: the 95% radius of its particles, or "lost" when no
particle fits the terrain any more. Hooks for the follow-up experiments: MAP_OFFSET (X2), _loglik (X3),
diagnostics (X4)."""
import json
import zlib
from pathlib import Path

import numpy as np

from gpsfree.evaluate import load_algorithm

GRID_M = 10.0
def height_grid(m):
    """Height grid of the drone's map, cached on the map object itself so it is freed with the map."""
    surface = getattr(m, "_world", m)
    if getattr(surface, "_pf_grid", None) is None:
        (x0, y0, _), (x1, y1, _) = m.bounds
        X, Y = np.meshgrid(np.arange(x0, x1, GRID_M), np.arange(y0, y1, GRID_M))
        H = m.height(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape)
        H[~np.isfinite(H)] = np.nanmin(np.where(np.isfinite(H), H, np.nan))  # map edges: no surface hit
        surface._pf_grid = (x0, y0, H)
    return surface._pf_grid


class Navigator(load_algorithm("imu_deadreckoning")):
    platforms = ("drone",)
    hardware = "adis16470"   # the $8 ICM-42688-P drifts too far in tilt without a lidar-corrected attitude
    ranger = "avia"
    N = 500
    SIGMA_M = 4.0          # vertical residual: range noise + grid interpolation on steep ground
    CLIP = 3.0             # residuals beyond CLIP sigma count as outliers (trees, roofs, map errors)
    INFO_BEAMS = 10        # temperature: a frame counts as at most this many independent beams
    USE_ACCEL = True
    TILT_TAU_S = None      # pulling tilt towards gravity hurts: manoeuvres and drag make the specific force non-vertical
    Q_V = 0.2              # velocity random walk, m/s/sqrt(s)
    Q_YAW = 0.002          # heading random walk, rad/sqrt(s)
    MAP_OFFSET = False     # X2: estimate a shared local map height offset
    RADIUS_FLOOR_M = 3.0
    RADIUS_K = 1.0         # radius = floor + k * particle spread; k calibrated on training runs (calibration.json)
    CALIBRATION = Path(__file__).with_name("calibration.json")
    LOST_FIT = 4.0         # best particle's mean squared residual (in sigma^2) above this ...
    LOST_AFTER_S = 2.0     # ... for this long = "I don't know where I am"

    def __init__(self, ctx):
        super().__init__(ctx)
        seed = zlib.crc32(f"{ctx.scenario}/{ctx.start.t:.3f}/{np.round(ctx.start.position, 1)}".encode())
        self.rng = np.random.default_rng(seed)
        self.grid = height_grid(ctx.map)
        (bx0, by0, _), (bx1, by1, _) = ctx.map.bounds
        self.bounds = (np.array([bx0, by0]), np.array([bx1, by1]))
        self.dirs = ctx.sensors["echo"]["directions"]
        self.temper = min(1.0, self.INFO_BEAMS / len(self.dirs))
        s, n = ctx.start, self.N
        self.pxy = s.position[:2] + self.rng.normal(0, max(1.0, ctx.start_sigma_m), (n, 2))
        self.pv = np.tile(s.velocity[:2], (n, 1))
        self.psi = np.zeros(n)
        self.w = np.full(n, 1 / n)
        self.t_prop = s.t
        self.dv, self.dp = np.zeros(2), np.zeros(2)
        self.offset = 0.0
        self.fit = 0.0
        self.bad_since = None
        cal = self.CALIBRATION
        self.k = json.loads(cal.read_text())["radius_k"] if cal.exists() else self.RADIUS_K
        self.diag = {"ess": 1.0, "outliers": 0.0, "med_res": 0.0, "info": 0.0, "noreturn": 0.0}

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
        rot = lambda d: np.c_[c * d[0] - s * d[1], s * d[0] + c * d[1]]  # noqa: E731
        self.pxy += self.pv * T + rot(self.dp)
        self.pv += rot(self.dv) + self.rng.normal(0, self.Q_V * np.sqrt(T), (self.N, 2))
        self.psi += self.rng.normal(0, self.Q_YAW * np.sqrt(T), self.N)
        self.t_prop, self.dv, self.dp = t, np.zeros(2), np.zeros(2)
        lo, hi = self.bounds
        out = np.any((self.pxy < lo) | (self.pxy > hi), axis=1)
        if out.any():  # a position outside the map means nothing: put the particle back in, stopped
            self.pxy[out] = np.clip(self.pxy[out], lo, hi)
            self.pv[out] *= 0.0

    def _terrain(self, x, y):
        x0, y0, H = self.grid
        u, v = (x - x0) / GRID_M, (y - y0) / GRID_M
        j = np.clip(np.floor(u).astype(int), 0, H.shape[1] - 2)
        i = np.clip(np.floor(v).astype(int), 0, H.shape[0] - 2)
        fu, fv = np.clip(u - j, 0, 1), np.clip(v - i, 0, 1)
        return (H[i, j] * (1 - fu) * (1 - fv) + H[i, j + 1] * fu * (1 - fv)
                + H[i + 1, j] * (1 - fu) * fv + H[i + 1, j + 1] * fu * fv)

    def _loglik(self, r):
        """Per-particle log-likelihood of the vertical residuals r (particles x beams), before tempering."""
        return -0.5 * np.minimum((r / self.SIGMA_M) ** 2, self.CLIP ** 2).sum(1)

    def on_echo(self, t, ranges):
        if self.R is None:
            return
        self._propagate(t)
        ok = np.isfinite(ranges)
        self.diag["noreturn"] = 1 - ok.mean()
        if not ok.any():
            return
        rel = (self.dirs[ok] * ranges[ok, None]) @ self.R.T  # beam endpoints relative to the body, world axes
        c, s = np.cos(self.psi)[:, None], np.sin(self.psi)[:, None]
        x = self.pxy[:, :1] + c * rel[:, 0] - s * rel[:, 1]
        y = self.pxy[:, 1:] + s * rel[:, 0] + c * rel[:, 1]
        r = (self.p[2] + rel[:, 2]) - self._terrain(x, y)
        if self.MAP_OFFSET:
            med = float(self.w @ np.median(r, axis=1))
            self.offset += 0.2 * (med - self.offset)
            r = r - self.offset
        ll = self._loglik(r)
        msq = np.minimum((r / self.SIGMA_M) ** 2, self.CLIP ** 2).mean(1)
        self.fit = float(msq.min())
        best = int(np.argmax(self.w))
        self.diag.update(outliers=float(np.mean(np.abs(r[best]) > self.CLIP * self.SIGMA_M)),
                         med_res=float(np.median(np.abs(r[best]))),
                         info=float(np.std(self._terrain(x[best], y[best]))))
        if self.fit > self.LOST_FIT:
            self.bad_since = t if self.bad_since is None else self.bad_since
        else:
            self.bad_since = None
        self.t_echo = t
        logw = np.log(self.w + 1e-300) + ll * self.temper
        w = np.exp(logw - logw.max())
        self.w = w / w.sum()
        ess = 1 / np.sum(self.w ** 2)
        self.diag["ess"] = ess / self.N
        if ess < self.N / 2:
            self._resample()

    def _resample(self):
        n = self.N
        idx = np.searchsorted(np.cumsum(self.w), (self.rng.random() + np.arange(n)) / n).clip(0, n - 1)
        self.pxy = self.pxy[idx] + self.rng.normal(0, 0.5, (n, 2))
        self.pv = self.pv[idx] + self.rng.normal(0, 0.05, (n, 2))
        self.psi = self.psi[idx] + self.rng.normal(0, 0.002, n)
        self.w = np.full(n, 1 / n)

    def estimate(self):
        lag = (self.last_t or self.t_prop) - self.t_prop
        xy = self.w @ (self.pxy + self.pv * lag) + self.dp
        return np.r_[xy, self.p[2]]

    def spread(self):
        """95% horizontal radius of the particle cloud around its weighted mean."""
        m = self.w @ self.pxy
        d = self.pxy - m
        cov = (self.w[:, None] * d).T @ d
        return float(np.sqrt(5.99 * max(np.linalg.eigvalsh(cov).max(), 0.0)))

    def diagnostics(self):
        return dict(self.diag, spread=self.spread(), fit=self.fit, start_sigma=self.ctx.start_sigma_m,
                    t=(self.last_t or 0.0) - self.ctx.start.t)

    def uncertainty(self):
        if self.bad_since is not None and getattr(self, "t_echo", 0) - self.bad_since >= self.LOST_AFTER_S:
            return np.inf
        return self.RADIUS_FLOOR_M + self.k * self.spread()
