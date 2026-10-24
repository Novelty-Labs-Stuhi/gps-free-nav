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
from gpsfree.paths import BENCHMARK, EXPERIMENTS, ROUTES, RUNS
from gpsfree.routes import stable_seed
from gpsfree.sensors import generate, sensor_spec
from gpsfree.trajectory import Route, Trajectory, horizontal_distance
from gpsfree.world import World

EVENT_ORDER = ["imu", "mag", "baro", "echo", "step"]


def load_suite():
    return json.loads((BENCHMARK / "suite.json").read_text())


def route_paths(worlds=None, platforms=None):
    paths = sorted(ROUTES.glob("*/*.json"))
    return [p for p in paths
            if (not worlds or p.parent.name in worlds)
            and (not platforms or p.stem.split("-")[0] in platforms)]


def suite_fingerprint():
    h = hashlib.sha256((BENCHMARK / "suite.json").read_bytes())
    for p in route_paths():
        h.update(p.relative_to(ROUTES).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


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
    data = generate(traj, world, suite["sensors"], rng)

    s0 = traj.sample(np.array([traj.t0]))
    start = Pose(traj.t0, s0["p"][0], float(s0["yaw"][0]), s0["v"][0])
    algo = algo_cls(Context(route.platform, route.world, MapView(world), start, sensor_spec(suite["sensors"])))
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
    err = np.linalg.norm(est[:, :2] - truth[:, :2], axis=1)
    err[~np.isfinite(err)] = np.inf
    dist = horizontal_distance(truth)
    out = {"distance_m": round(float(dist[-1]), 1), "error_at_m": {}}
    for d in suite["checkpoints_m"]:
        i = np.searchsorted(dist, d)
        out["error_at_m"][str(d)] = round(float(err[i]), 2) if i < len(err) else None
    out["final_error_m"] = round(float(err[-1]), 2)
    out["drift_pct"] = round(float(100 * err[-1] / max(dist[-1], 1)), 2)
    out["z_rmse_m"] = round(float(np.sqrt(np.nanmean((est[:, 2] - truth[:, 2]) ** 2))), 2)
    return out


def summarize(runs, suite):
    groups = {}
    for r in runs:
        groups.setdefault(f"{r['world']}/{r['platform']}", []).append(r)
    summary = {}
    for key, rs in sorted(groups.items()):
        s = {"runs": len(rs)}
        for d in suite["checkpoints_m"]:
            vals = [r["error_at_m"][str(d)] for r in rs if r["error_at_m"][str(d)] is not None]
            s[f"median_err_{d}m"] = round(float(np.median(vals)), 2) if vals else None
        head = [r["error_at_m"][str(suite["headline_m"])] for r in rs]
        head = [np.inf if v is None else v for v in head]
        s["fail_rate"] = round(float(np.mean([v > suite["fail_threshold_m"] for v in head])), 2)
        s["median_drift_pct"] = round(float(np.median([r["drift_pct"] for r in rs])), 2)
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
    return {
        "experiment": experiment,
        "author": _git_user(),
        "suite": suite_fingerprint(),
        "partial": bool(worlds or platforms),
        "elapsed_s": round(time.time() - t0, 1),
        "summary": summarize(runs, suite),
        "runs": runs,
    }


def results_path(experiment: str) -> Path:
    return EXPERIMENTS / experiment / "results.json"


def compare(old: dict, new: dict, abs_tol=0.5, rel_tol=0.02):
    """Headline numbers that differ beyond tolerance (used by CI to verify committed results)."""
    problems = []
    if old.get("suite") != new.get("suite"):
        problems.append(f"suite changed: committed {old.get('suite')} vs current {new.get('suite')}")
    for key, s in new["summary"].items():
        o = old.get("summary", {}).get(key)
        if o is None:
            problems.append(f"{key}: missing from committed results")
            continue
        for metric, v in s.items():
            if metric.startswith("min_realtime"):
                continue
            ov = o.get(metric)
            if v is None or ov is None:
                if v != ov:
                    problems.append(f"{key} {metric}: {ov} vs {v}")
            elif abs(v - ov) > max(abs_tol, rel_tol * abs(ov)):
                problems.append(f"{key} {metric}: committed {ov} vs reproduced {v}")
    return problems


def _git_user():
    try:
        return subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, check=False).stdout.strip() or None
    except OSError:
        return None
