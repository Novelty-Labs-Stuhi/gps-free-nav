"""Benchmark runner: every route x seed, stream sensors into the algorithm, score against truth."""
import hashlib
import importlib.util
import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from gpsfree.algorithm import Algorithm, Context, MapView, Pose
from gpsfree.paths import BENCHMARK, EXPERIMENTS, HARDWARE, ROUTES, RUNS
from gpsfree.routes import stable_seed
from gpsfree.sensors import generate, hardware_sensors, sensor_spec
from gpsfree.trajectory import Route, Trajectory, path_length
from gpsfree.world import World

EVENT_ORDER = ["imu", "mag", "baro", "echo", "step"]


def load_suite():
    return json.loads((BENCHMARK / "suite.json").read_text())


def route_paths(worlds=None, platforms=None):
    """Routes in the suite; explicit worlds/platforms override the suite's selection."""
    suite = load_suite()
    worlds, platforms = worlds or suite.get("worlds"), platforms or suite.get("platforms")
    paths = sorted(ROUTES.glob("*/*.json"))
    return [p for p in paths
            if (not worlds or p.parent.name in worlds)
            and (not platforms or p.stem.split("-")[0] in platforms)]


def suite_groups(platforms=None):
    """world/platform groups the suite scores, optionally only for the given platforms."""
    suite = load_suite()
    return [f"{w}/{p}" for w in suite["worlds"] for p in suite["platforms"] if not platforms or p in platforms]


def group_fingerprint(group: str, hardware=None) -> str:
    """What one world/platform result depends on: scoring and sensor config, that group's routes and the hardware
    profiles the experiment uses. Adding a world, routes elsewhere or other hardware profiles leaves it unchanged."""
    world, platform = group.split("/")
    rules = {k: v for k, v in load_suite().items() if k not in ("worlds", "platforms")}
    h = hashlib.sha256(json.dumps(rules, sort_keys=True).encode())
    for p in route_paths([world], [platform]):
        h.update(p.relative_to(ROUTES).as_posix().encode())
        h.update(p.read_bytes())
    for name in [hardware] if isinstance(hardware, str) else hardware or []:
        h.update((HARDWARE / f"{name}.json").read_bytes())
    return h.hexdigest()[:12]


def is_stale(result: dict, group: str) -> bool:
    return result.get("fingerprints", {}).get(group) != group_fingerprint(group, result.get("hardware"))


def load_algorithm(experiment: str) -> type[Algorithm]:
    path = EXPERIMENTS / experiment / "algo.py"
    spec = importlib.util.spec_from_file_location(f"experiments.{experiment}.algo", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Navigator


_worlds: dict[str, World] = {}


def _world(wid):
    if wid not in _worlds:
        _worlds[wid] = World(wid)
    return _worlds[wid]


def run_one(experiment: str, route_path: str, seed: int, suite: dict, save_trajectory=True):
    algo_cls = load_algorithm(experiment)
    route = Route.load(route_path)
    if route.platform not in algo_cls.platforms:
        return None
    world = _world(route.world)
    traj = Trajectory(route)
    rng = np.random.default_rng([seed, stable_seed(route.world, route.name)])
    sensors = hardware_sensors(suite["sensors"], algo_cls.hardware)
    data = generate(traj, world, sensors, rng)

    s0 = traj.sample(np.array([traj.t0]))
    start = Pose(traj.t0, s0["p"][0], float(s0["yaw"][0]), s0["v"][0])
    algo = algo_cls(Context(route.platform, route.world, MapView(world), start, sensor_spec(sensors)))
    handlers = {
        "imu": lambda d, i: algo.on_imu(d["t"][i], d["acc"][i], d["gyro"][i]),
        "mag": lambda d, i: algo.on_mag(d["t"][i], d["field"][i]),
        "baro": lambda d, i: algo.on_baro(d["t"][i], float(d["altitude"][i])),
        "echo": lambda d, i: algo.on_echo(d["t"][i], d["ranges"][i]),
        "step": lambda d, i: algo.on_step(d["t"][i], float(d["length"][i])),
    }

    # Merge all sensor streams into one time-ordered event list.
    kinds = [k for k in EVENT_ORDER if k in data]
    ts = np.concatenate([data[k]["t"] for k in kinds])
    kind_ix = np.concatenate([np.full(len(data[k]["t"]), j) for j, k in enumerate(kinds)])
    item_ix = np.concatenate([np.arange(len(data[k]["t"])) for k in kinds])
    order = np.lexsort((kind_ix, ts))

    score_t = np.arange(traj.t0, traj.t1, 1 / suite["score_rate_hz"])
    est = np.full((len(score_t), 3), np.nan)
    k = 0
    t_wall = time.perf_counter()
    for e in order:
        while k < len(score_t) and score_t[k] < ts[e]:
            est[k] = algo.estimate()
            k += 1
        kind = kinds[kind_ix[e]]
        handlers[kind](data[kind], item_ix[e])
    while k < len(score_t):
        est[k] = algo.estimate()
        k += 1
    wall = time.perf_counter() - t_wall

    truth = traj.sample(score_t)["p"]
    metrics = score(score_t, truth, est, suite)
    metrics.update(route=route.name, world=route.world, platform=route.platform, seed=seed,
                   duration_s=round(float(score_t[-1] - score_t[0]), 1), realtime_factor=round(float((score_t[-1] - score_t[0]) / wall), 1))
    if save_trajectory:
        out = RUNS / experiment / f"{route.world}__{route.name}__s{seed}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"t": np.round(score_t, 2).tolist(), "truth": np.round(truth, 2).tolist(),
                                   "estimate": np.round(np.nan_to_num(est, nan=0.0), 2).tolist(), **metrics}))
    return metrics


def score(t, truth, est, suite):
    """Error is 3D distance to truth; distance travelled d is the 3D arc length of the true path.
    Score: mean of log10(error) over d >= score_from_m, i.e. the geometric-mean error along the route."""
    diff = est - truth
    err = np.linalg.norm(diff, axis=1)
    err[~np.isfinite(err)] = np.inf
    d = path_length(truth)
    m = d >= suite["score_from_m"]
    loge = np.log10(np.maximum(err[m], suite["error_floor_m"]))
    out = {"distance_m": round(float(d[-1]), 1), "score_log10": round(float(np.mean(loge)), 3), "mae_m": {}}
    edges = suite["mae_bands_m"] + [np.inf]
    for lo, hi in zip(edges[:-1], edges[1:]):
        band = err[(d >= lo) & (d < hi)]
        out["mae_m"][f"{lo}+" if hi == np.inf else f"{lo}-{hi}"] = round(float(band.mean()), 2) if len(band) else None
    lost = np.flatnonzero(err > suite["lost_threshold_m"])
    out["lost_at_m"] = round(float(d[lost[0]] if len(lost) else d[-1]), 1)
    out["growth_k"] = round(float(np.polyfit(np.log10(d[m]), loge, 1)[0]), 2) if np.all(np.isfinite(loge)) else None
    out["xy_rmse_m"] = round(float(np.sqrt(np.nanmean(np.sum(diff[:, :2] ** 2, axis=1)))), 2)
    out["z_rmse_m"] = round(float(np.sqrt(np.nanmean(diff[:, 2] ** 2))), 2)
    return out


def summarize(runs, suite):
    """Medians over routes x seeds per world/platform group."""
    groups = {}
    for r in runs:
        groups.setdefault(f"{r['world']}/{r['platform']}", []).append(r)
    summary = {}
    for key, rs in sorted(groups.items()):
        score = float(np.median([r["score_log10"] for r in rs]))
        s = {"runs": len(rs), "score_log10": round(score, 3), "score_m": round(10 ** score, 1), "mae_m": {}}
        for band in rs[0]["mae_m"]:
            vals = [r["mae_m"][band] for r in rs if r["mae_m"].get(band) is not None]
            s["mae_m"][band] = round(float(np.median(vals)), 2) if vals else None
        s["lost_at_m"] = round(float(np.median([r["lost_at_m"] for r in rs])), 1)
        ks = [r["growth_k"] for r in rs if r["growth_k"] is not None]
        s["growth_k"] = round(float(np.median(ks)), 2) if ks else None
        s["min_realtime_factor"] = min(r["realtime_factor"] for r in rs)
        summary[key] = s
    return summary


def evaluate(experiment: str, worlds=None, platforms=None, jobs=None):
    suite = load_suite()
    tasks = [(experiment, str(p), seed, suite) for p in route_paths(worlds, platforms) for seed in suite["seeds"]]
    jobs = jobs or min(len(tasks), os.cpu_count() or 1)
    t0 = time.time()
    if jobs > 1:
        with ProcessPoolExecutor(jobs) as pool:
            runs = list(pool.map(run_one, *zip(*tasks)))
    else:
        runs = [run_one(*t) for t in tasks]
    runs = [r for r in runs if r is not None]
    summary = summarize(runs, suite)
    hardware = load_algorithm(experiment).hardware
    return {
        "experiment": experiment,
        "author": _git_user(),
        "hardware": hardware,
        "fingerprints": {g: group_fingerprint(g, hardware) for g in summary},
        "partial": bool(worlds or platforms),
        "elapsed_s": round(time.time() - t0, 1),
        "summary": summary,
        "runs": runs,
    }


def results_path(experiment: str) -> Path:
    return EXPERIMENTS / experiment / "results.json"


def compare(old: dict, new: dict, tol_log10=0.01):
    """Groups whose committed result is missing, stale or doesn't reproduce (used by CI to verify results)."""
    problems = []
    for g, s in new["summary"].items():
        o = old.get("summary", {}).get(g)
        if o is None:
            problems.append(f"{g}: missing from committed results")
        elif old.get("fingerprints", {}).get(g) != new["fingerprints"][g]:
            problems.append(f"{g}: committed results are for older rules/routes/hardware, re-run `gpsfree eval`")
        elif o.get("runs") != s["runs"] or abs(o.get("score_log10", np.inf) - s["score_log10"]) > tol_log10:
            problems.append(f"{g}: committed {o.get('score_log10')} ({o.get('runs')} runs) "
                            f"vs reproduced {s['score_log10']} ({s['runs']} runs)")
    return problems


def _git_user():
    try:
        return subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, check=False).stdout.strip() or None
    except OSError:
        return None
