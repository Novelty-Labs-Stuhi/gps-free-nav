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
    """The prior map an algorithm may use: the scenario's map, which can differ from the true world
    (terrain height errors, missing or wrong buildings, no trees). Geometry only, no ground truth."""

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
    start_sigma_m: float = 0.0  # how far off the start position may be (1 sigma, horizontal); 0 = exact
    scenario: str = ""


class Algorithm:
    platforms = ("drone", "walker")  # override to restrict which benchmark runs apply
    hardware = None  # name of a benchmark/hardware/<name>.json real-part imu+mag profile; None = suite sensors
    ranger = None    # name of a benchmark/rangers/<name>.json echo sensor; None = the suite's default ranger

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

    def uncertainty(self) -> float | None:
        """How far off the estimate may be: a horizontal radius (m) the true position should lie inside
        95% of the time. Called right after estimate(). Return np.inf for "I don't know where I am".
        None (the default) makes no integrity claim: the leaderboard then cannot say whether the method
        knows when it is wrong."""
        return None
