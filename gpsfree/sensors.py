"""Noisy sensor streams generated offline from a trajectory (deterministic per seed)."""
import json

import numpy as np

from gpsfree.paths import HARDWARE

from gpsfree.trajectory import G, Trajectory, horizontal_distance


def echo_directions(pattern: dict) -> np.ndarray:
    """Beam unit vectors in the body frame (FLU)."""
    dirs = []
    for el in np.radians(pattern["elevations_deg"]):
        for az in np.linspace(0, 2 * np.pi, pattern["azimuths"], endpoint=False):
            dirs.append([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    if pattern.get("down"):
        dirs.append([0, 0, -1])
    return np.array(dirs)


def generate(traj: Trajectory, world, cfg: dict, rng: np.random.Generator) -> dict:
    out = {}

    # IMU: specific force and body rates, with white noise + random-walk bias.
    c = cfg["imu"]
    dt = 1 / c["rate_hz"]
    t = np.arange(traj.t0, traj.t1, dt)
    s = traj.sample(t)
    f_world = s["a"] + np.array([0, 0, G])
    acc = s["rot"].inv().apply(f_world)
    gyro = traj.body_rates(s["rot"], dt)
    n = len(t)
    acc_bias = rng.normal(0, c["acc_bias_init"], 3) + np.cumsum(rng.normal(0, c["acc_bias_walk"] * np.sqrt(dt), (n, 3)), 0)
    gyro_bias = rng.normal(0, c["gyro_bias_init"], 3) + np.cumsum(rng.normal(0, c["gyro_bias_walk"] * np.sqrt(dt), (n, 3)), 0)
    out["imu"] = {
        "t": t,
        "acc": acc + acc_bias + rng.normal(0, c["acc_noise"], (n, 3)),
        "gyro": gyro + gyro_bias + rng.normal(0, c["gyro_noise"], (n, 3)),
    }

    # Magnetometer: earth field rotated into body, plus a hard-iron offset.
    if "mag" not in cfg:
        return out
    c = cfg["mag"]
    t = np.arange(traj.t0, traj.t1, 1 / c["rate_hz"])
    s = traj.sample(t)
    hard_iron = rng.normal(0, c["hard_iron_ut"], 3)
    out["mag"] = {"t": t, "field": s["rot"].inv().apply(np.array(c["field_enu_ut"])) + hard_iron + rng.normal(0, c["noise_ut"], (len(t), 3))}

    # Barometer: altitude with drifting bias.
    if "baro" not in cfg:
        return out
    c = cfg["baro"]
    bdt = 1 / c["rate_hz"]
    t = np.arange(traj.t0, traj.t1, bdt)
    z = traj.sample(t)["p"][:, 2]
    drift = np.cumsum(rng.normal(0, c["drift_m_per_sqrt_s"] * np.sqrt(bdt), len(t)))
    out["baro"] = {"t": t, "altitude": z + drift + rng.normal(0, c["noise_m"], len(t))}

    # Echo: ranges along a fixed fan of body-frame beams, raycast against the world.
    c = cfg["echo"]
    t = np.arange(traj.t0, traj.t1, 1 / c["rate_hz"])
    s = traj.sample(t)
    dirs_b = echo_directions(c["pattern"])
    nb = len(dirs_b)
    dirs_w = np.einsum("tij,bj->tbi", s["rot"].as_matrix(), dirs_b).reshape(-1, 3)
    origins = np.repeat(s["p"], nb, axis=0)
    rng_true = world.raycast(origins, dirs_w, c["max_range_m"]).reshape(len(t), nb)
    noisy = rng_true + rng.normal(0, 1, rng_true.shape) * (c["noise_m"] + c["noise_frac"] * np.nan_to_num(rng_true, posinf=0))
    noisy[rng.random(noisy.shape) < c["dropout"]] = np.inf
    out["echo"] = {"t": t, "ranges": noisy}

    # Steps (walker): one event per true stride, reported length is noisy.
    if traj.route.platform == "walker":
        c = cfg["step"]
        tt = np.arange(traj.t0, traj.t1, 0.05)
        dist = horizontal_distance(traj.sample(tt)["p"])
        marks = np.arange(c["stride_m"], dist[-1], c["stride_m"])
        out["step"] = {"t": np.interp(marks, dist, tt), "length": c["stride_m"] * (1 + rng.normal(0, c["stride_noise_frac"], len(marks)))}
    return out


def hardware_sensors(base: dict, name: str | None) -> dict:
    """Suite sensor config with imu/mag replaced by a real-part profile (benchmark/hardware/<name>.json).
    Profiles hold datasheet numbers in datasheet units: white noise sigma = noise density * sqrt(rate),
    constant per-run bias ~ N(0, in-run bias stability, else tempco * delta_temp_c), no bias walk."""
    if name is None:
        return base
    hw = json.loads((HARDWARE / f"{name}.json").read_text())
    i, m = hw["imu"], hw["mag"]
    ug, dph = 1e-6 * G, np.radians(1) / 3600
    acc_nd = i["acc_nd_ug_rthz"] * ug if "acc_nd_ug_rthz" in i else i["acc_vrw_mps_rth"] / 60
    gyro_nd = np.radians(i["gyro_nd_dps_rthz"] if "gyro_nd_dps_rthz" in i else i["gyro_arw_deg_rth"] / 60)
    acc_b = i.get("acc_bias_ug", i.get("acc_tempco_ug_per_c", 0) * i.get("delta_temp_c", 0))
    gyro_b = i.get("gyro_bias_dph", i.get("gyro_tempco_dph_per_c", 0) * i.get("delta_temp_c", 0))
    root = np.sqrt(i["rate_hz"])
    return base | {
        "imu": {"rate_hz": i["rate_hz"], "acc_noise": acc_nd * root, "acc_bias_init": acc_b * ug, "acc_bias_walk": 0.0,
                "gyro_noise": gyro_nd * root, "gyro_bias_init": gyro_b * dph, "gyro_bias_walk": 0.0},
        "mag": {"rate_hz": m["rate_hz"], "noise_ut": m["noise_ut"], "hard_iron_ut": m["residual_hard_iron_ut"],
                "field_enu_ut": base["mag"]["field_enu_ut"]},
    }


def sensor_spec(cfg: dict) -> dict:
    """What an algorithm is told about its sensors (config + echo beam geometry)."""
    spec = {k: dict(v) for k, v in cfg.items()}
    spec["echo"]["directions"] = echo_directions(cfg["echo"]["pattern"])
    return spec
