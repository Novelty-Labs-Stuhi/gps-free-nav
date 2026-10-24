"""Baseline: strapdown IMU integration (gyro -> attitude, accel -> velocity -> position).
Height from the barometer. Drifts without bound; everything should beat it."""
import numpy as np

from gpsfree import Algorithm

G = np.array([0.0, 0.0, 9.80665])


def level_attitude(acc, yaw):
    """Body-to-world rotation from one accelerometer sample (gravity gives roll/pitch, valid when the
    drone is not accelerating) and the known heading of the body's forward axis."""
    up = acc / np.linalg.norm(acc)                      # world up, in body coordinates
    f = np.array([1.0, 0, 0]) - up[0] * up              # body forward, levelled
    f /= np.linalg.norm(f)
    left = np.cross(up, f)
    east = np.cos(yaw) * f - np.sin(yaw) * left
    north = np.sin(yaw) * f + np.cos(yaw) * left
    return np.vstack([east, north, up])


def rodrigues(w):
    th = np.linalg.norm(w)
    if th < 1e-12:
        return np.eye(3)
    k = w / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K


class Navigator(Algorithm):
    def __init__(self, ctx):
        super().__init__(ctx)
        s = ctx.start
        self.p = s.position.astype(float).copy()
        self.v = s.velocity.astype(float).copy()
        self.R = None
        self.last_t = None
        self.last_gyro = None
        self.last_a = None
        self.baro0 = None

    def _init_attitude(self, acc):
        self.R = level_attitude(acc, self.ctx.start.yaw)

    def on_imu(self, t, acc, gyro):
        if self.R is None:
            self._init_attitude(acc)
            self.last_t, self.last_gyro, self.last_a = t, gyro, self.R @ acc - G
            return
        dt = t - self.last_t
        self.R = self.R @ rodrigues(0.5 * (gyro + self.last_gyro) * dt)  # trapezoidal
        a = self.R @ acc - G
        v_new = self.v + 0.5 * (a + self.last_a) * dt
        self.p += 0.5 * (self.v + v_new) * dt
        self.v = v_new
        self.last_t, self.last_gyro, self.last_a = t, gyro, a

    def on_baro(self, t, altitude):
        if self.baro0 is None:
            self.baro0 = altitude - self.ctx.start.position[2]
        self.p[2] = altitude - self.baro0

    def estimate(self):
        return self.p
