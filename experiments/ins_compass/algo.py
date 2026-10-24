"""Strapdown INS (imu_deadreckoning) + magnetometer yaw: a complementary filter pulls the heading
towards the compass with time constant TAU_S. The compass is zeroed against the known start heading,
which cancels the hard-iron offset at that heading. Tilt still comes from the gyro alone."""
import numpy as np

from gpsfree.evaluate import load_algorithm

TAU_S = 2.0


class Navigator(load_algorithm("imu_deadreckoning")):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.yaw_ref = None
        self.mag_dt = 1 / ctx.sensors["mag"]["rate_hz"]

    def on_mag(self, t, field):
        if self.R is None:
            return
        bw = self.R @ field
        yaw = np.arctan2(bw[1], bw[0])
        if self.yaw_ref is None:
            self.yaw_ref = yaw
            return
        e = -np.angle(np.exp(1j * (yaw - self.yaw_ref))) * self.mag_dt / TAU_S
        c, s = np.cos(e), np.sin(e)
        self.R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]) @ self.R
