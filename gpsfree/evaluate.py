"""Benchmark runner: every scenario x run, stream sensors into the algorithm, score against truth.

A scenario (benchmark/scenarios/<id>.json) fixes a world, how the drone flies (route style), the wind,
how good the drone's map is and whether the start position is wrong. Run i of a scenario always gets
the same route, wind, noise and start offset, so results reproduce bit for bit."""
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
from gpsfree.paths import BENCHMARK, EXPERIMENTS, HARDWARE, RANGERS, RUNS, SCENARIOS
from gpsfree.routes import ROUTE_GENERATOR_VERSION, scenario_route, stable_seed
from gpsfree.sensors import generate, hardware_sensors, sensor_spec
from gpsfree.trajectory import Trajectory, path_length
from gpsfree.world import World

EVENT_ORDER = ["imu", "mag", "baro", "echo", "step"]


def load_suite():
    return json.loads((BENCHMARK / "suite.json").read_text())


def load_scenario(sid: str) -> dict:
    return json.loads((SCENARIOS / f"{sid}.json").read_text())


def suite_scenarios(suite=None):
    return (suite or load_suite())["scenarios"]


def suite_fingerprint():
    """Changes whenever anything that affects a score changes: rules, scenarios, parts, routes, worlds."""
    from gpsfree.worlds import WORLDS
    from gpsfree.worlds.bake import BAKE_VERSION
    from gpsfree.worlds.overture import extract_path
    suite = load_suite()
    h = hashlib.sha256((BENCHMARK / "suite.json").read_bytes())
    h.update(f"routes v{ROUTE_GENERATOR_VERSION} bake v{BAKE_VERSION}".encode())
    worlds = set()
    for sid in suite_scenarios(suite):
        h.update((SCENARIOS / f"{sid}.json").read_bytes())
        worlds.add(load_scenario(sid)["world"])
    for w in sorted(worlds):
        h.update(json.dumps(WORLDS[w], sort_keys=True).encode())
        if extract_path(w).exists():
            h.update(extract_path(w).read_bytes())
    for folder in (HARDWARE, RANGERS):
        for p in sorted(folder.glob("*.json")):
            h.update(p.name.encode())
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
    """Keep at most two worlds in memory per process (tasks arrive grouped by scenario)."""
    if wid not in _worlds:
        while len(_worlds) >= 2:
            _worlds.pop(next(iter(_worlds)))
            import gc
            gc.collect()
        _worlds[wid] = World(wid)
    return _worlds[wid]


def run_seed(sid, index):
    return stable_seed("run", sid, index)


def start_offset(scenario, index):
    """Horizontal offset of the start position the algorithm is told, and the sigma it is told."""
    lo, hi = scenario.get("start_offset_m", [0, 0])
    if hi <= 0:
        return np.zeros(3), 0.0
    rng = np.random.default_rng([run_seed(scenario["id"], index), 2])
    d, a = rng.uniform(lo, hi), rng.uniform(0, 2 * np.pi)
    return np.array([d * np.cos(a), d * np.sin(a), 0.0]), hi / 2


def run_one(experiment: str, scenario, index: int, suite: dict, save_trajectory=True, hooks=None):
    """One run. scenario: id or dict. hooks (studies, replays): route, sensor_world, map, start_offset, algo_cls,
    record (a dict that receives the simulated streams, estimate and uncertainty)."""
    hooks = hooks or {}
    sc = load_scenario(scenario) if isinstance(scenario, str) else scenario
    algo_cls = hooks.get("algo_cls") or load_algorithm(experiment)
    if sc["platform"] not in algo_cls.platforms:
        return None
    world = _world(sc["world"])
    route = hooks.get("route") or scenario_route(sc, index, world)
    seed = run_seed(sc["id"], index)
    traj = Trajectory(route, wind=sc.get("wind"), seed=seed)
    sensors = hardware_sensors(suite["sensors"], algo_cls.hardware, algo_cls.ranger or suite["default_ranger"])
    data = generate(traj, hooks.get("sensor_world", world), sensors, np.random.default_rng([seed, 1]))

    s0 = traj.sample(np.array([traj.t0]))
    offset, sigma = start_offset(sc, index)
    if "start_offset" in hooks:
        offset, sigma = np.asarray(hooks["start_offset"], float), float(np.linalg.norm(hooks["start_offset"])) / 2
    start = Pose(traj.t0, s0["p"][0] + offset, float(s0["yaw"][0]), s0["v"][0])
    mp = hooks.get("map") or world.map_world(sc.get("map"), seed=stable_seed("map", sc["id"]))
    algo = algo_cls(Context(sc["platform"], sc["world"], MapView(mp), start, sensor_spec(sensors), sigma, sc["id"]))
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
    unc = np.full(len(score_t), np.nan)

    def sample(k):
        est[k] = algo.estimate()
        u = algo.uncertainty()
        unc[k] = np.nan if u is None else float(u)

    k = 0
    t_wall = time.perf_counter()
    for e in order:
        while k < len(score_t) and score_t[k] < ts[e]:
            sample(k)
            k += 1
        kind = kinds[kind_ix[e]]
        handlers[kind](data[kind], item_ix[e])
    while k < len(score_t):
        sample(k)
        k += 1
    wall = time.perf_counter() - t_wall

    truth = traj.sample(score_t)["p"]
    metrics = score(score_t, truth, est, suite, unc)
    if "record" in hooks:  # replay export: hand back everything that was simulated
        hooks["record"].update(traj=traj, route=route, data=data, sensors=sensors, score_t=score_t, est=est,
                               unc=unc, map=mp, world=world, scenario=sc, algo=algo)
    metrics.update(scenario=sc["id"], run=index, world=sc["world"], platform=sc["platform"],
                   start_offset_m=round(float(np.linalg.norm(offset)), 1),
                   duration_s=round(float(score_t[-1] - score_t[0]), 1),
                   realtime_factor=round(float((score_t[-1] - score_t[0]) / max(wall, 1e-9)), 1))
    if save_trajectory:
        out = RUNS / experiment / f"{sc['id']}__r{index:02d}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        planned = np.c_[[np.interp(score_t, route.t, route.position[:, i]) for i in range(3)]].T
        out.write_text(json.dumps({"t": np.round(score_t, 2).tolist(), "truth": np.round(truth, 2).tolist(),
                                   "estimate": np.round(np.nan_to_num(est, nan=0.0), 2).tolist(),
                                   "planned": np.round(planned, 2).tolist(),
                                   "uncertainty": [None if not np.isfinite(u) and np.isnan(u) else (round(float(u), 2) if np.isfinite(u) else "inf") for u in unc],
                                   **metrics}))
    return metrics


def score(t, truth, est, suite, unc=None):
    """Error is 3D distance to truth; distance travelled d is the 3D arc length of the true path.
    Score: mean of log10(error) over d >= score_from_m, i.e. the geometric-mean error along the route.
    Integrity (only if the method reports an uncertainty radius; horizontal error vs that radius):
      misleading_frac  share of samples where the true error lies outside the reported 95% radius
      warned_at_m      distance at which the radius first exceeded the alert limit (lost_threshold_m)
      hmi_frac         share of samples with hazardously misleading information: error above the alert
                       limit while the reported radius is within it (the aviation integrity failure)
      silent_failure   the run had any such sample"""
    diff = est - truth
    err = np.linalg.norm(diff, axis=1)
    err[~np.isfinite(err)] = np.inf
    d = path_length(truth)
    m = d >= suite["score_from_m"]
    loge = np.log10(np.clip(err[m], suite["error_floor_m"], suite["error_cap_m"]))
    out = {"distance_m": round(float(d[-1]), 1), "score_log10": round(float(np.mean(loge)), 3), "mae_m": {}}
    edges = suite["mae_bands_m"] + [np.inf]
    for lo, hi in zip(edges[:-1], edges[1:]):
        band = err[(d >= lo) & (d < hi)]
        out["mae_m"][f"{lo}+" if hi == np.inf else f"{lo}-{hi}"] = round(float(band.mean()), 2) if len(band) else None
    lost = np.flatnonzero(err > suite["lost_threshold_m"])
    out["lost_at_m"] = round(float(d[lost[0]] if len(lost) else d[-1]), 1)
    out["lost"] = bool(len(lost))
    out["growth_k"] = round(float(np.polyfit(np.log10(d[m]), loge, 1)[0]), 2) if np.all(np.isfinite(loge)) else None
    out["max_error_m"] = round(float(np.nanmax(np.where(np.isfinite(err), err, np.nan))), 1) if np.isfinite(err).any() else None
    unc = np.full(len(t), np.nan) if unc is None else np.asarray(unc, float)
    claimed = ~np.isnan(unc)
    out["integrity"] = bool(claimed[m].mean() > 0.5) if m.any() else False
    if out["integrity"]:
        exy = np.linalg.norm(diff[:, :2], axis=1)
        mm = m & claimed
        out["misleading_frac"] = round(float(np.mean(exy[mm] > unc[mm])), 4)
        al = suite["lost_threshold_m"]  # alert limit
        warn = np.flatnonzero(claimed & (unc > al))
        out["warned_at_m"] = round(float(d[warn[0]]), 1) if len(warn) else None
        # hazardously misleading information: truly off by more than the alert limit while claiming to be within it
        hmi = mm & (exy > al) & (unc <= al)
        out["hmi_frac"] = round(float(hmi[m].mean()), 4)
        # false alarm: says it is lost (radius over the alert limit) while actually within it
        out["false_alarm_frac"] = round(float((mm & (exy <= al) & (unc > al))[m].mean()), 4)
        out["silent_failure"] = bool(hmi.any())
        out["median_radius_m"] = round(float(np.nanmedian(np.where(np.isfinite(unc[mm]), unc[mm], np.nan))), 2) if np.isfinite(unc[mm]).any() else None
    out["xy_rmse_m"] = round(float(np.sqrt(np.nanmean(np.sum(diff[:, :2] ** 2, axis=1)))), 2)
    out["z_rmse_m"] = round(float(np.sqrt(np.nanmean(diff[:, 2] ** 2))), 2)
    return out


def summarize(runs, suite):
    """Per scenario: medians over its runs, the 90th-percentile run and the share of runs ever off by
    more than lost_threshold_m. Overall: geometric mean of the scenario scores (each scenario weighs
    the same, whatever its error scale), plus the worst scenario."""
    groups = {}
    for r in runs:
        groups.setdefault(r["scenario"], []).append(r)
    summary = {}
    for key in [s for s in suite_scenarios(suite) if s in groups] + sorted(set(groups) - set(suite_scenarios(suite))):
        rs = groups[key]
        sc = np.array([r["score_log10"] for r in rs])
        score = float(np.median(sc))
        s = {"runs": len(rs), "score_log10": round(score, 3), "score_m": round(10 ** score, 2),
             "p90_score_m": round(float(10 ** np.percentile(sc, 90)), 2),
             "lost_frac": round(float(np.mean([r["lost"] for r in rs])), 3), "mae_m": {}}
        for band in rs[0]["mae_m"]:
            vals = [r["mae_m"][band] for r in rs if r["mae_m"].get(band) is not None]
            s["mae_m"][band] = round(float(np.median(vals)), 2) if vals else None
        s["lost_at_m"] = round(float(np.median([r["lost_at_m"] for r in rs])), 1)
        ks = [r["growth_k"] for r in rs if r["growth_k"] is not None]
        s["growth_k"] = round(float(np.median(ks)), 2) if ks else None
        s["min_realtime_factor"] = min(r["realtime_factor"] for r in rs)
        integ = [r for r in rs if r.get("integrity")]
        if integ:
            s["misleading_frac"] = round(float(np.mean([r["misleading_frac"] for r in integ])), 4)
            s["silent_failure_frac"] = round(float(np.mean([r["silent_failure"] for r in integ])), 3)
            s["warned_frac"] = round(float(np.mean([r["warned_at_m"] is not None for r in integ])), 3)
            s["false_alarm_frac"] = round(float(np.mean([r.get("false_alarm_frac", 0.0) for r in integ])), 4)
        summary[key] = s
    if summary:
        logs = [s["score_log10"] for s in summary.values()]
        worst = max(summary, key=lambda k: summary[k]["score_log10"])
        summary["overall"] = {"scenarios": len(summary), "runs": len(runs), "score_log10": round(float(np.mean(logs)), 3),
                              "score_m": round(float(10 ** np.mean(logs)), 2),
                              "worst_scenario": worst, "worst_score_m": summary[worst]["score_m"],
                              "lost_frac": round(float(np.mean([r["lost"] for r in runs])), 3)}
        integ = [r for r in runs if r.get("integrity")]
        if integ:
            summary["overall"]["misleading_frac"] = round(float(np.mean([r["misleading_frac"] for r in integ])), 4)
            summary["overall"]["silent_failure_frac"] = round(float(np.mean([r["silent_failure"] for r in integ])), 3)
            summary["overall"]["false_alarm_frac"] = round(float(np.mean([r.get("false_alarm_frac", 0.0) for r in integ])), 4)
    return summary


def tasks_for(experiment, suite, scenarios=None, runs=None):
    n = runs or suite["runs_per_scenario"]
    return [(experiment, sid, i, suite) for sid in (scenarios or suite_scenarios(suite)) for i in range(n)]


def evaluate(experiment: str, scenarios=None, runs=None, jobs=None):
    suite = load_suite()
    tasks = tasks_for(experiment, suite, scenarios, runs)
    jobs = jobs or min(len(tasks), os.cpu_count() or 1)
    t0 = time.time()
    if jobs > 1:
        # tasks are ordered by scenario; chunks of 5 keep workers balanced while reusing loaded worlds
        with ProcessPoolExecutor(jobs) as pool:
            out = list(pool.map(run_one, *zip(*tasks), chunksize=5))
    else:
        out = [run_one(*t) for t in tasks]
    out = [r for r in out if r is not None]
    algo = load_algorithm(experiment)
    prev = results_path(experiment)
    author = json.loads(prev.read_text()).get("author") if prev.exists() else None  # re-runs keep the author
    return {
        "experiment": experiment,
        "author": author or _git_user(),
        "hardware": algo.hardware,
        "ranger": algo.ranger or suite["default_ranger"],
        "suite": suite_fingerprint(),
        "partial": bool(scenarios or (runs and runs != suite["runs_per_scenario"])),
        "elapsed_s": round(time.time() - t0, 1),
        "summary": summarize(out, suite),
        "runs": out,
    }


def results_path(experiment: str) -> Path:
    return EXPERIMENTS / experiment / "results.json"


def compare(old: dict, new: dict, tol_log10=0.02):
    """Scores that differ beyond tolerance (used by CI to verify committed results)."""
    problems = []
    if old.get("suite") != new.get("suite"):
        problems.append(f"suite changed: committed {old.get('suite')} vs current {new.get('suite')}")
    for key, s in new["summary"].items():
        o = old.get("summary", {}).get(key)
        if o is None:
            problems.append(f"{key}: missing from committed results")
        elif o.get("runs") != s["runs"] or abs(o.get("score_log10", np.inf) - s["score_log10"]) > tol_log10:
            problems.append(f"{key}: committed {o.get('score_log10')} ({o.get('runs')} runs) "
                            f"vs reproduced {s['score_log10']} ({s['runs']} runs)")
    return problems


def _git_user():
    try:
        return subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, check=False).stdout.strip() or None
    except OSError:
        return None
