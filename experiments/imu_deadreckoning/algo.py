"""Baseline: strapdown IMU integration (gyro -> attitude, accel -> velocity -> position).
Height from the barometer. Drifts without bound; everything should beat it."""
import numpy as np

from gpsfree import Algorithm

G = np.array([0.0, 0.0, 9.80665])


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
        # roll/pitch from gravity, yaw from the known start pose
        z = acc / np.linalg.norm(acc)
        x = np.array([np.cos(self.ctx.start.yaw), np.sin(self.ctx.start.yaw), 0.0])
        y = np.cross(z, x)
        y /= np.linalg.norm(y)
        self.R = np.column_stack([np.cross(y, z), y, z])

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
