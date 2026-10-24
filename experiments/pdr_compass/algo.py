"""Baseline (walker): pedestrian dead reckoning. Each step moves stride length along
the magnetometer heading; heading offset calibrated once at the known start."""
import numpy as np

from gpsfree import Algorithm


class Navigator(Algorithm):
    platforms = ("walker",)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.p = ctx.start.position.astype(float).copy()
        self.yaw = ctx.start.yaw
        self.yaw_offset = None
        self.baro0 = None

    def on_mag(self, t, field):
        # device held level: body field (x, y) = |B_h| (sin yaw, cos yaw) for a north-pointing field
        yaw_mag = np.arctan2(field[0], field[1])
        if self.yaw_offset is None:
            self.yaw_offset = self.ctx.start.yaw - yaw_mag
        self.yaw = yaw_mag + self.yaw_offset

    def on_step(self, t, length):
        self.p[0] += length * np.cos(self.yaw)
        self.p[1] += length * np.sin(self.yaw)

    def on_baro(self, t, altitude):
        if self.baro0 is None:
            self.baro0 = altitude - self.ctx.start.position[2]
        self.p[2] = altitude - self.baro0

    def estimate(self):
        return self.p
