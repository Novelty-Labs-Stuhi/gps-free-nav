"""Terrain-referenced navigation: error-state EKF on a consumer IMU (TDK ICM-42688-P, $8),
corrected by the echo ranges of a Livox Avia lidar ($1,599) against the prior 3D map.

State (16): position, velocity, attitude error (world frame), accel bias, gyro bias, baro bias.
- IMU at 100 Hz drives the strapdown mechanisation and the covariance.
- Barometer: altitude = z + baro bias (bias is a random walk).
- Echo: for each beam, the map predicts the range from the current pose by ray casting. Three extra
  rays (position nudged along x, y, z) give dr/dp; a locally planar surface then gives
  dr/dtheta = r * (d x dr/dp) for free. Beams that hit an edge (the planar check fails), miss the map,
  or disagree wildly with the prediction are dropped before the update.
"""
import numpy as np

from gpsfree import Algorithm

G = np.array([0.0, 0.0, 9.80665])
NUDGE_M = 1.0          # finite-difference step for dr/dp
MODEL_SIGMA_M = 0.5    # extra range sigma for map resolution / linearisation
GATE_SIGMA = 4.0       # per-beam innovation gate
MIN_BEAMS = 3          # beams needed for an echo update
REJECT_ALPHA = 0.1     # smoothing of the beam-rejection monitor (~1 s at 10 Hz)
REJECT_WARN = 0.35     # above this share of disagreeing beams the radius is inflated
REJECT_LOST = 0.6      # above this the filter declares itself lost
RADIUS_K = 3.0         # the covariance ignores map errors and unmapped clutter: widen it
RADIUS_FLOOR_M = 3.0   # and never claim better than the map resolution


def skew(w):
    return np.array([[0, -w[2], w[1]], [w[2], 0, -w[0]], [-w[1], w[0], 0]])


def level_attitude(acc, yaw):
    """Body-to-world rotation from gravity in one accelerometer sample plus the known heading."""
    up = acc / np.linalg.norm(acc)
    f = np.array([1.0, 0, 0]) - up[0] * up
    f /= np.linalg.norm(f)
    left = np.cross(up, f)
    return np.vstack([np.cos(yaw) * f - np.sin(yaw) * left, np.sin(yaw) * f + np.cos(yaw) * left, up])


def rodrigues(w):
    th = np.linalg.norm(w)
    if th < 1e-12:
        return np.eye(3)
    K = skew(w / th)
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


class Navigator(Algorithm):
    platforms = ("drone",)
    hardware = "icm42688p"
    ranger = "avia"
    MODEL_SIGMA_M = MODEL_SIGMA_M
    GATE_SIGMA = GATE_SIGMA
    MIN_BEAMS = MIN_BEAMS

    def __init__(self, ctx):
        super().__init__(ctx)
        s, imu = ctx.start, ctx.sensors["imu"]
        self.p = s.position.astype(float).copy()
        self.v = s.velocity.astype(float).copy()
        c, sn = np.cos(s.yaw), np.sin(s.yaw)
        self.R = np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1.0]])  # level at the start, known yaw
        self.ba = np.zeros(3)
        self.bg = np.zeros(3)
        self.bb = None  # baro bias, set from the first reading
        self.dirs = np.asarray(ctx.sensors["echo"]["directions"], float)
        self.echo_cfg = ctx.sensors["echo"]
        self.baro_cfg = ctx.sensors["baro"]
        self.imu_dt = 1 / imu["rate_hz"]
        self.acc_sig = imu["acc_noise"]
        self.gyro_sig = imu["gyro_noise"]
        self.acc_bw = max(imu.get("acc_bias_walk", 0.0), 1e-5)
        self.gyro_bw = max(imu.get("gyro_bias_walk", 0.0), 1e-7)
        P = np.zeros(16)
        P[0:2] = max(0.1, ctx.start_sigma_m) ** 2
        P[2] = 0.1 ** 2
        P[3:6] = 0.1 ** 2
        P[6:8] = np.radians(1) ** 2
        P[8] = np.radians(0.5) ** 2
        P[9:12] = max(imu["acc_bias_init"], 1e-4) ** 2
        P[12:15] = max(imu["gyro_bias_init"], 1e-6) ** 2
        P[15] = self.baro_cfg["noise_m"] ** 2
        self.P = np.diag(P)
        self.last_t = None
        self.n_echo_used = 0
        self.reject = 0.0  # running share of usable echo beams that disagree with the map

    # ---------------------------------------------------------------- propagation
    def on_imu(self, t, acc, gyro):
        if self.last_t is None:
            self.last_t = t
            self.R = level_attitude(acc, self.ctx.start.yaw)
            return
        dt = t - self.last_t
        self.last_t = t
        w = gyro - self.bg
        f_w = self.R @ (acc - self.ba)
        a = f_w - G
        self.p += self.v * dt + 0.5 * a * dt * dt
        self.v += a * dt
        self.R = self.R @ rodrigues(w * dt)

        F = np.eye(16)
        F[0:3, 3:6] = np.eye(3) * dt
        F[3:6, 6:9] = -skew(f_w) * dt
        F[3:6, 9:12] = -self.R * dt
        F[6:9, 12:15] = -self.R * dt
        q = np.zeros(16)
        q[3:6] = (self.acc_sig * dt) ** 2
        q[6:9] = (self.gyro_sig * dt) ** 2
        q[9:12] = self.acc_bw ** 2 * dt
        q[12:15] = self.gyro_bw ** 2 * dt
        q[15] = self.baro_cfg["drift_m_per_sqrt_s"] ** 2 * dt
        self.P = F @ self.P @ F.T + np.diag(q)

    # ---------------------------------------------------------------- updates
    def _update(self, H, y, Rm):
        S = H @ self.P @ H.T + Rm
        K = np.linalg.solve(S, H @ self.P).T
        dx = K @ y
        I_KH = np.eye(16) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ Rm @ K.T  # Joseph form
        self.p += dx[0:3]
        self.v += dx[3:6]
        self.R = rodrigues(dx[6:9]) @ self.R
        self.ba += dx[9:12]
        self.bg += dx[12:15]
        self.bb += dx[15]

    def on_baro(self, t, altitude):
        if self.bb is None:
            self.bb = altitude - self.p[2]
            return
        H = np.zeros((1, 16))
        H[0, 2] = 1.0
        H[0, 15] = 1.0
        y = np.array([altitude - (self.p[2] + self.bb)])
        self._update(H, y, np.array([[self.baro_cfg["noise_m"] ** 2]]))

    def on_echo(self, t, ranges):
        if self.bb is None or self.last_t is None:
            return
        cfg = self.echo_cfg
        d = self.dirs @ self.R.T                       # beam directions in the world frame
        n = len(d)
        origins = np.vstack([self.p] + [self.p + NUDGE_M * e for e in np.eye(3)])
        o = np.repeat(origins, n, axis=0)
        r = self.ctx.map.raycast(o, np.tile(d, (4, 1)), np.inf).reshape(4, n)
        r0 = r[0]
        with np.errstate(invalid="ignore"):
            g = (r[1:] - r0).T / NUDGE_M               # dr/dp per beam, (n, 3)
        ok = np.isfinite(ranges) & np.isfinite(r).all(0) & (r0 < cfg["max_range_m"]) & (ranges < cfg["max_range_m"])
        ok &= np.abs(np.einsum("ij,ij->i", g, d) + 1.0) < 0.2   # planar-surface consistency (not an edge)
        if not ok.any():
            return
        g, d_ok, r_ok, z = g[ok], d[ok], r0[ok], ranges[ok]
        H = np.zeros((len(z), 16))
        H[:, 0:3] = g
        H[:, 6:9] = r_ok[:, None] * np.cross(d_ok, g)
        sig = cfg["noise_m"] + cfg["noise_frac"] * z
        Rm_diag = sig ** 2 + self.MODEL_SIGMA_M ** 2
        y = z - r_ok
        s = np.einsum("ij,jk,ik->i", H, self.P, H) + Rm_diag
        keep = y ** 2 < self.GATE_SIGMA ** 2 * s
        self.reject += REJECT_ALPHA * ((1 - keep.mean()) - self.reject)
        if keep.sum() < self.MIN_BEAMS:
            return
        self.n_echo_used += 1
        self._update(H[keep], y[keep], np.diag(Rm_diag[keep]))

    def estimate(self):
        return self.p

    def uncertainty(self):
        """95% horizontal radius from the covariance, inflated when the map stops agreeing with the
        beams and infinite ("I don't know") once most beams disagree: the drone has probably locked
        onto the wrong terrain, or the map is wrong here."""
        r = RADIUS_FLOOR_M + RADIUS_K * 2.45 * np.sqrt(max(np.linalg.eigvalsh(self.P[0:2, 0:2]).max(), 0.0))
        if self.reject > REJECT_LOST:
            return np.inf
        if self.reject > REJECT_WARN:
            r *= 1 + 20 * (self.reject - REJECT_WARN)
        return r
