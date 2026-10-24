"""With every noise term zeroed, the sensors must be consistent with the ground truth:
strapdown integration and PDR should then track the true path almost exactly."""
import copy

import numpy as np
import pytest

from gpsfree.evaluate import load_suite, route_paths, run_one


def noiseless_suite():
    suite = copy.deepcopy(load_suite())
    for cfg in suite["sensors"].values():
        for k in list(cfg):
            if any(w in k for w in ("noise", "bias", "drift", "hard_iron", "dropout")):
                cfg[k] = 0.0
    return suite


@pytest.mark.parametrize("platform", ["drone", "walker"])
def test_imu_integration_is_consistent(platform):
    path = route_paths(["yosemite"], [platform])[0]
    m = run_one("imu_deadreckoning", str(path), 0, noiseless_suite(), save_trajectory=False)
    assert m["error_at_m"]["500"] < 5.0, m


def test_pdr_is_consistent():
    path = route_paths(["rotterdam"], ["walker"])[0]
    m = run_one("pdr_compass", str(path), 0, noiseless_suite(), save_trajectory=False)
    assert m["error_at_m"]["1000"] < 5.0, m


def test_echo_ranges_hit_ground():
    from gpsfree.sensors import generate
    from gpsfree.trajectory import Route, Trajectory
    from gpsfree.world import World

    route = Route.load(route_paths(["yosemite"], ["drone"])[0])
    traj = Trajectory(route)
    data = generate(traj, World("yosemite"), noiseless_suite()["sensors"], np.random.default_rng(0))
    down = data["echo"]["ranges"][:, -1]  # last beam points straight down
    agl = traj.sample(data["echo"]["t"])["p"][:, 2] - World("yosemite").height(traj.sample(data["echo"]["t"])["p"][:, :2])
    in_range = agl < 180
    finite = np.isfinite(down) & in_range
    assert finite.sum() / in_range.sum() > 0.95
    # body is tilted a little while manoeuvring, so allow a few percent
    assert np.median(np.abs(down[finite] - agl[finite]) / agl[finite]) < 0.03
