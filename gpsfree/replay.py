"""Export one benchmark run for the replay app (replay/ on the replay-viewer branch).

Writes data/replays/<experiment>/<scenario>__r<NN>/{replay.json, truth.glb, map.glb} in the format that
app documents, and refreshes data/replays/index.json. The truth mesh is what the sensors measured
(terrain, buildings, trees); the map mesh is what the drone carried. replay.json also carries
`uncertainty` (the method's reported 95% radius per sample, "inf" = I don't know, null = no claim)."""
import json

import numpy as np

import gpsfree.evaluate as ev
from gpsfree.paths import DATA
from gpsfree.sensors import echo_directions
from gpsfree.trajectory import path_length
from gpsfree.worlds.bake import _write_glb

REPLAYS = DATA / "replays"
MAX_FACES = 400_000


def _crop(mesh, xy, margin=600.0):
    lo, hi = xy.min(0) - margin, xy.max(0) + margin
    c = mesh.vertices[mesh.faces].mean(1)[:, :2]
    keep = np.all((c >= lo) & (c <= hi), axis=1)
    v, f = mesh.vertices, mesh.faces[keep]
    used, f = np.unique(f, return_inverse=True)
    v, f = v[used], f.reshape(-1, 3)
    cell = 0.5
    while len(f) > MAX_FACES:  # vertex clustering until the browser can take it
        cell *= 2
        q, inv = np.unique(np.round(v / cell), axis=0, return_inverse=True)
        nv = np.zeros((len(q), 3))
        np.add.at(nv, inv.ravel(), v)
        nv /= np.bincount(inv.ravel())[:, None]
        nf = inv.ravel()[f]
        nf = nf[(nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])]
        v, f = nv, np.unique(np.sort(nf, axis=1), axis=0) if len(nf) > MAX_FACES * 4 else nf
    return v, f


def _nullable(a, nd=2):
    return [[None if not np.isfinite(x) else round(float(x), nd) for x in row] for row in a]


def export(experiment: str, scenario: str, run: int = 0) -> str:
    suite = ev.load_suite()
    rec = {}
    metrics = ev.run_one(experiment, scenario, run, suite, save_trajectory=False, hooks={"record": rec})
    traj, route, data, t, est, unc = rec["traj"], rec["route"], rec["data"], rec["score_t"], rec["est"], rec["unc"]
    s = traj.sample(t)
    truth = s["p"]
    run_id = f"{scenario}__r{run:02d}"
    out = REPLAYS / experiment / run_id
    out.mkdir(parents=True, exist_ok=True)

    echo, cfg = data["echo"], rec["sensors"]["echo"]
    dirs_b = echo_directions(cfg["pattern"])
    se = traj.sample(echo["t"])
    est_e = np.stack([np.interp(echo["t"], t, est[:, i]) for i in range(3)], 1)
    dirs_w = np.einsum("tij,bj->tbi", se["rot"].as_matrix(), dirs_b).reshape(-1, 3)
    pred = rec["map"].raycast(np.repeat(est_e, len(dirs_b), axis=0), dirs_w, cfg["max_range_m"]).reshape(len(echo["t"]), -1)

    err = np.linalg.norm(est - truth, axis=1)
    d = path_length(truth)
    loge = np.log10(np.maximum(err, suite["error_floor_m"]))
    m = d >= suite["score_from_m"]
    geo = np.full(len(t), np.nan)
    geo[m] = 10 ** (np.cumsum(loge[m]) / np.arange(1, m.sum() + 1))
    planned = np.stack([np.interp(t, route.t, route.position[:, i]) for i in range(3)], 1)
    step = max(1, len(route.t) // 600)
    rep = {
        "experiment": experiment, "scenario": scenario, "world": rec["scenario"]["world"], "run_id": run_id,
        "scenario_name": rec["scenario"]["name"], "score_m": round(10 ** metrics["score_log10"], 2),
        "t": np.round(t, 2).tolist(),
        "truth_p": np.round(truth, 2).tolist(),
        "truth_q": np.round(s["rot"].as_quat(), 5).tolist(),
        "est_p": np.round(np.nan_to_num(est), 2).tolist(),
        "planned_p": np.round(route.position[::step], 2).tolist(),
        "uncertainty": [None if np.isnan(u) else ("inf" if np.isinf(u) else round(float(u), 2)) for u in unc],
        "echo": {"t": np.round(echo["t"], 2).tolist(), "dirs_body": np.round(dirs_b, 5).tolist(),
                 "max_range": cfg["max_range_m"], "measured": _nullable(echo["ranges"]), "predicted": _nullable(pred)},
        "metrics": {"err": np.round(err, 3).tolist(),
                    "geo_mean_err": [None if np.isnan(g) else round(float(g), 3) for g in geo],
                    "dev_xy": np.round(np.linalg.norm(est[:, :2] - truth[:, :2], axis=1), 3).tolist(),
                    "dev_z": np.round(est[:, 2] - truth[:, 2], 3).tolist(),
                    "dev_plan": np.round(np.linalg.norm(truth - planned, axis=1), 3).tolist()},
    }
    (out / "replay.json").write_text(json.dumps(rep, separators=(",", ":")))
    xy = np.r_[truth[:, :2], np.clip(np.nan_to_num(est[:, :2]), -rec["world"].radius, rec["world"].radius)]
    for name, mesh in (("truth", rec["world"].mesh), ("map", rec["map"].mesh)):
        v, f = _crop(mesh, xy)
        _write_glb(out / f"{name}.glb", {"world": (v, f)}, None)
    _index()
    return f"{experiment}/{run_id}"


def _index():
    items = []
    for p in sorted(REPLAYS.glob("*/*/replay.json")):
        r = json.loads(p.read_text())
        items.append({"id": f"{p.parent.parent.name}/{p.parent.name}", "experiment": r["experiment"],
                      "scenario": r.get("scenario"), "world": r.get("world"), "run_id": r["run_id"]})
    REPLAYS.mkdir(parents=True, exist_ok=True)
    (REPLAYS / "index.json").write_text(json.dumps(items, indent=1))
