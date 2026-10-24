"""The contract every experiment implements.

Frames: world = ENU meters (x east, y north, z up, z=0 at ground level at the world centre).
Body = FLU (x forward, y left, z up). yaw is CCW from east, radians.
Sensor callbacks arrive in time order; nothing ever exposes ground truth.
"""
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Pose:
    t: float
    position: np.ndarray  # (3,) ENU
    yaw: float
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))


class MapView:
    """The prior map an algorithm may use (geometry only, no ground truth)."""

    def __init__(self, world):
        self._world = world
        self.id = world.id
        self.radius = world.radius
        self.bounds = world.meta["bounds"]

    def raycast(self, origins, directions, max_range=np.inf):
        return self._world.raycast(origins, directions, max_range)

    def height(self, xy, ground_only=False):
        return self._world.height(xy, ground_only)


@dataclass
class Context:
    platform: str          # "drone" | "walker"
    world: str
    map: MapView
    start: Pose            # true start pose (known initial condition)
    sensors: dict          # rates, noise levels, echo beam directions (body frame)


class Algorithm:
    platforms = ("drone", "walker")  # override to restrict which benchmark runs apply
    hardware = None  # name of a benchmark/hardware/<name>.json real-part imu+mag profile; None = suite sensors

    def __init__(self, ctx: Context):
        self.ctx = ctx

    def on_imu(self, t: float, acc: np.ndarray, gyro: np.ndarray):
        """acc: specific force m/s^2 (body), gyro: rad/s (body)."""

    def on_mag(self, t: float, field: np.ndarray):
        """Magnetic field µT (body)."""

    def on_baro(self, t: float, altitude: float):
        """Barometric altitude, m (biased, drifting)."""

    def on_echo(self, t: float, ranges: np.ndarray):
        """Echo ranges, m, one per beam in ctx.sensors['echo']['directions'] (body); inf = no echo."""

    def on_step(self, t: float, length: float):
        """Walker only: a detected step with an estimated stride length, m."""

    def estimate(self) -> np.ndarray:
        """Current position estimate (3,) ENU. Called at the scoring rate."""
        raise NotImplementedError
