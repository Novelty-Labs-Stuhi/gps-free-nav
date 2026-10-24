"""Run one experiment on one route and write a replay for the viewer in replay/.

    uv run python replay/export_sample.py ins_compass --route yosemite/drone-gen0 --seed 0

Writes data/replays/<experiment>/<run_id>/{replay.json, truth.glb, map.glb}. The format is
documented in replay/README.md; write_replay() is the part another evaluator can reuse.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gpsfree.algorithm import Context, MapView, Pose  # noqa: E402
from gpsfree.evaluate import EVENT_ORDER, load_algorithm, load_suite  # noqa: E402
from gpsfree.paths import DATA, ROUTES  # noqa: E402
from gpsfree.routes import stable_seed  # noqa: E402
from gpsfree.sensors import generate, hardware_sensors, sensor_spec  # noqa: E402
from gpsfree.trajectory import Route, Trajectory, path_length  # noqa: E402
from gpsfree.world import World  # noqa: E402
from gpsfree.worlds.bake import _write_glb  # noqa: E402

REPLAYS = DATA / "replays"
RATE_HZ = 10
CROP_MARGIN_M = 600     # keep this much terrain around the route
MAX_TRIANGLES = 400_000


def crop_mesh(mesh, lo, hi):
    """Faces whose centroid lies inside the xy box [lo, hi], with unused vertices dropped."""
    c = mesh.triangles_center
    keep = np.all((c[:, :2] >= lo) & (c[:, :2] <= hi), axis=1)
    f = mesh.faces[keep]
    used, inv = np.unique(f, return_inverse=True)
    return mesh.vertices[used], inv.reshape(-1, 3)


def decimate(v, f, max_tri):
    """Crude vertex clustering on a grid until the face count fits; keeps the browser fast."""
    cell = 1.0
    while len(f) > max_tri:
        cell *= 1.5
        key = np.floor(v / cell).astype(np.int64)
        _, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        v2, f2 = v[idx], inv.reshape(-1)[f]
        ok = (f2[:, 0] != f2[:, 1]) & (f2[:, 1] != f2[:, 2]) & (f2[:, 0] != f2[:, 2])
        v, f = v2, f2[ok]
    return v, f


def mesh_for_replay(mesh, path_xy):
    lo, hi = path_xy.min(0) - CROP_MARGIN_M, path_xy.max(0) + CROP_MARGIN_M
    v, f = crop_mesh(mesh, lo, hi)
    return decimate(v, f, MAX_TRIANGLES)


def _r(a, nd=2):
    """Round to a JSON-friendly nested list; non-finite values become null."""
    a = np.round(np.asarray(a, dtype=np.float64), nd)
    o = a.astype(object)
    o[~np.isfinite(a)] = None
    return o.tolist()


def deviation_metrics(t, truth, est, planned_t, planned_p, score_from_m=0.0, floor_m=1.0):
    err = np.linalg.norm(est - truth, axis=1)
    d = path_length(truth)
    loge = np.where(d >= score_from_m, np.log10(np.maximum(err, floor_m)), np.nan)
    n = np.cumsum(np.isfinite(loge))
    geo = np.where(n > 0, 10 ** (np.cumsum(np.nan_to_num(loge)) / np.maximum(n, 1)), np.nan)
    plan_at_t = np.stack([np.interp(t, planned_t, planned_p[:, i]) for i in range(3)], 1)
    return {
        "err": err,
        "geo_mean_err": geo,
        "dev_xy": np.linalg.norm((est - truth)[:, :2], axis=1),
        "dev_z": est[:, 2] - truth[:, 2],
        "dev_plan": np.linalg.norm(truth - plan_at_t, axis=1),
    }


def write_replay(out: Path, *, experiment, scenario, world, run_id, t, truth_p, truth_q, est_p, planned_p,
                 echo, metrics, truth_mesh, map_mesh):
    """Write replay.json + truth.glb + map.glb. Meshes are (vertices ENU, faces) tuples."""
    out.mkdir(parents=True, exist_ok=True)
    doc = {
        "experiment": experiment, "scenario": scenario, "world": world, "run_id": run_id,
        "t": _r(t), "truth_p": _r(truth_p), "truth_q": _r(truth_q, 4), "est_p": _r(est_p), "planned_p": _r(planned_p),
        "echo": {"t": _r(echo["t"]), "dirs_body": _r(echo["dirs_body"], 4), "max_range": float(echo["max_range"]),
                 "measured": _r(echo["measured"], 1), "predicted": _r(echo["predicted"], 1)},
        "metrics": {k: _r(v) for k, v in metrics.items()},
    }
    (out / "replay.json").write_text(json.dumps(doc, separators=(",", ":")))
    _write_glb(out / "truth.glb", {"truth": truth_mesh}, None)
    _write_glb(out / "map.glb", {"map": map_mesh}, None)
    update_index()


def update_index():
    """data/replays/index.json lists every replay folder so the viewer can offer a picker."""
    runs = sorted(p.parent.relative_to(REPLAYS).as_posix() for p in REPLAYS.glob("*/*/replay.json"))
    (REPLAYS / "index.json").write_text(json.dumps(runs, indent=1))


def load_navigator(experiment):
    """An experiment name under experiments/, or a path to any folder holding an algo.py."""
    path = Path(experiment)
    if not (path / "algo.py").exists():
        return experiment, load_algorithm(experiment)
    spec = importlib.util.spec_from_file_location(f"replay_algo_{path.name}", path / "algo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return path.resolve().name, mod.Navigator


def run(experiment, route_path, seed):
    suite = load_suite()
    experiment, algo_cls = load_navigator(experiment)
    route = Route.load(route_path)
    world = World(route.world)
    traj = Trajectory(route)
    rng = np.random.default_rng([seed, stable_seed(route.world, route.name)])
    sensors = hardware_sensors(suite["sensors"], algo_cls.hardware)
    data = generate(traj, world, sensors, rng)
    spec = sensor_spec(sensors)

    s0 = traj.sample(np.array([traj.t0]))
    start = Pose(traj.t0, s0["p"][0], float(s0["yaw"][0]), s0["v"][0])
    map_view = MapView(world)  # today the map is the true world
    algo = algo_cls(Context(route.platform, route.world, map_view, start, spec))
    handlers = {
        "imu": lambda d, i: algo.on_imu(d["t"][i], d["acc"][i], d["gyro"][i]),
        "mag": lambda d, i: algo.on_mag(d["t"][i], d["field"][i]),
        "baro": lambda d, i: algo.on_baro(d["t"][i], float(d["altitude"][i])),
        "echo": lambda d, i: algo.on_echo(d["t"][i], d["ranges"][i]),
        "step": lambda d, i: algo.on_step(d["t"][i], float(d["length"][i])),
    }
    kinds = [k for k in EVENT_ORDER if k in data]
    ts = np.concatenate([data[k]["t"] for k in kinds])
    kind_ix = np.concatenate([np.full(len(data[k]["t"]), j) for j, k in enumerate(kinds)])
    item_ix = np.concatenate([np.arange(len(data[k]["t"])) for k in kinds])
    order = np.lexsort((kind_ix, ts))

    t = np.arange(traj.t0, traj.t1, 1 / RATE_HZ)
    est = np.full((len(t), 3), np.nan)
    k = 0
    for e in order:
        while k < len(t) and t[k] < ts[e]:
            est[k] = algo.estimate()
            k += 1
        kind = kinds[kind_ix[e]]
        handlers[kind](data[kind], item_ix[e])
    while k < len(t):
        est[k] = algo.estimate()
        k += 1

    s = traj.sample(t)
    truth = s["p"]

    # Map-predicted echo ranges from the estimated position. Algorithms report position only, so the
    # beams are rotated by the true attitude.
    echo_t = data["echo"]["t"]
    dirs_b = spec["echo"]["directions"]
    max_range = sensors["echo"]["max_range_m"]
    est_e = np.stack([np.interp(echo_t, t, est[:, i]) for i in range(3)], 1)
    rot_e = traj.sample(echo_t)["rot"].as_matrix()
    dirs_w = np.einsum("tij,bj->tbi", rot_e, dirs_b).reshape(-1, 3)
    predicted = map_view.raycast(np.repeat(est_e, len(dirs_b), axis=0), dirs_w, max_range).reshape(len(echo_t), -1)

    metrics = deviation_metrics(t, truth, est, route.t, route.position, suite["score_from_m"], suite["error_floor_m"])
    v, f = mesh_for_replay(world.mesh, np.r_[truth[:, :2], route.position[:, :2]])
    run_id = f"{route.world}__{route.name}__s{seed}"
    out = REPLAYS / experiment / run_id
    write_replay(
        out, experiment=experiment, scenario="baseline", world=route.world, run_id=run_id,
        t=t, truth_p=truth, truth_q=s["rot"].as_quat(), est_p=est, planned_p=route.position,
        echo={"t": echo_t, "dirs_body": dirs_b, "max_range": max_range,
              "measured": data["echo"]["ranges"], "predicted": predicted},
        metrics=metrics, truth_mesh=(v, f), map_mesh=(v, f),
    )
    print(f"{out}  ({len(t)} poses, {len(f)} triangles, final err {metrics['err'][-1]:.1f} m)")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("experiment", nargs="?", default="ins_compass", help="folder name in experiments/, or a path to a folder with algo.py")
    ap.add_argument("--route", default="yosemite/drone-gen0", help="<world>/<route> under benchmark/routes")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    run(a.experiment, ROUTES / f"{a.route}.json", a.seed)


if __name__ == "__main__":
    main()
