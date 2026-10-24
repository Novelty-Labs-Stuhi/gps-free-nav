"""Sanity checks on the simulator and the suite.

With every noise term zeroed and no wind, the sensors must be consistent with the ground truth:
strapdown integration should then track the true path almost exactly. Routes, maps, wind and the
wrong-start offsets must behave as the scenario files say."""
import copy

import numpy as np

from gpsfree.evaluate import _world, load_scenario, load_suite, run_one, start_offset, suite_scenarios
from gpsfree.routes import generate_route, scenario_route, stable_seed
from gpsfree.sensors import generate, hardware_sensors
from gpsfree.trajectory import Trajectory


def noiseless_suite():
    suite = copy.deepcopy(load_suite())
    for cfg in suite["sensors"].values():
        for k in list(cfg):
            if any(w in k for w in ("noise", "bias", "drift", "hard_iron", "dropout", "airspeed")):
                cfg[k] = 0.0
    return suite


def calm(sid):
    sc = copy.deepcopy(load_scenario(sid))
    sc["wind"] = None
    sc["start_offset_m"] = [0, 0]
    return sc


def test_imu_integration_is_consistent():
    m = run_one("imu_deadreckoning", calm("alpine"), 0, noiseless_suite(), save_trajectory=False)
    assert m["mae_m"]["250-500"] < 5.0, m


def test_routes_are_deterministic():
    sc = load_scenario("alpine")
    w = _world(sc["world"])
    a = generate_route(w, "drone", "x", seed=stable_seed("route", "alpine", 3), style=sc["route"])
    b = generate_route(w, "drone", "x", seed=stable_seed("route", "alpine", 3), style=sc["route"])
    assert np.array_equal(a.position, b.position)
    cached = scenario_route(sc, 3, w)
    assert np.allclose(cached.position, a.position, atol=0.01)


def test_map_differs_only_as_specified():
    rng = np.random.default_rng(0)
    xy = rng.uniform(-1500, 1500, (3000, 2))
    bare = _world("yosemite")
    assert np.allclose(bare.map_world({}).height(xy), bare.height(xy), atol=1e-3)  # no trees, no error: identical
    tam = _world("tampere")
    truth, plain = tam.height(xy), tam.map_world({}).height(xy)
    assert np.all(truth >= plain - 1e-3)       # the map only ever lacks things (trees), never adds them
    assert np.mean(truth > plain + 2) > 0.02   # and there are unmapped trees to lack
    noisy = tam.map_world({"terrain_error_m": 2.0}).height(xy, ground_only=True)
    err = noisy - tam.height(xy, ground_only=True)
    assert 1.0 < err.std() < 3.0


def test_wind_moves_the_drone_but_keeps_it_near_its_plan():
    sc = load_scenario("fells")  # strong gusty wind
    w = _world(sc["world"])
    route = scenario_route(sc, 0, w)
    windy, still = Trajectory(route, wind=sc["wind"], seed=1), Trajectory(route)
    t = np.arange(windy.t0, windy.t1, 0.5)
    dev = np.linalg.norm(windy.sample(t)["p"] - still.sample(t)["p"], axis=1)
    assert 0.05 < dev.max() < 15, dev.max()
    cfg = hardware_sensors(noiseless_suite()["sensors"], None, "tf03")
    a = generate(windy, w, cfg, np.random.default_rng(0))["imu"]["acc"]
    b = generate(still, w, cfg, np.random.default_rng(0))["imu"]["acc"]
    assert np.abs(a - b).mean() > 0.05  # drag tilt and gusts show up in the accelerometer


def test_wrong_start_offsets_stay_in_range():
    for sid in suite_scenarios():
        sc = load_scenario(sid)
        lo, hi = sc["start_offset_m"]
        for i in range(load_suite()["runs_per_scenario"]):
            off, sigma = start_offset(sc, i)
            d = np.linalg.norm(off)
            assert (d == 0 and sigma == 0) if hi == 0 else (lo - 1e-9 <= d <= hi + 1e-9 and sigma == hi / 2)


def test_down_ranger_sees_the_ground():
    sc = calm("alpine")
    w = _world(sc["world"])
    traj = Trajectory(scenario_route(sc, 0, w))
    data = generate(traj, w, hardware_sensors(noiseless_suite()["sensors"], None, "tf03"), np.random.default_rng(0))
    down = data["echo"]["ranges"][:, -1]
    p = traj.sample(data["echo"]["t"])["p"]
    agl = p[:, 2] - w.height(p[:, :2])
    ok = np.isfinite(down) & (agl < 90)
    assert ok.sum() > 0.5 * (agl < 90).sum()
    assert np.median(np.abs(down[ok] - agl[ok]) / agl[ok]) < 0.05
