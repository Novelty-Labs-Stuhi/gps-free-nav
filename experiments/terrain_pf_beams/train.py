"""X3: learn how lidar beams disagree with the drone's map, from TRAINING runs 20-29 of every scenario.

At the TRUE pose and attitude, each beam endpoint's height minus the map height under it (same 10 m grid the filter
uses) is one residual. Unmapped trees and roofs stop beams early, so the endpoint sits ABOVE the map: a one-sided
tail. Fit by EM: (1 - pi) * Normal(mu, sigma) + pi * Exponential(lam) on r > 0. Writes beam_model.json."""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import gpsfree.evaluate as ev
from gpsfree.algorithm import MapView

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "terrain_pf"))
RUNS = range(20, 30)


def residuals(task):
    sid, i = task
    from algo import height_grid  # terrain_pf's grid, so training sees exactly what the filter sees
    rec = {}
    ev.run_one("terrain_pf", sid, i, ev.load_suite(), save_trajectory=False, hooks={"record": rec})
    echo, dirs = rec["data"]["echo"], rec["sensors"]
    from gpsfree.sensors import echo_directions
    d_b = echo_directions(dirs["echo"]["pattern"])
    x0, y0, H = height_grid(MapView(rec["map"]))
    k = slice(None, None, 5)
    s = rec["traj"].sample(echo["t"][k])
    R = echo["ranges"][k]
    ends = s["p"][:, None, :] + np.einsum("tij,bj->tbi", s["rot"].as_matrix(), d_b) * R[..., None]
    ok = np.isfinite(R)
    e = ends[ok]
    u, v = (e[:, 0] - x0) / 10.0, (e[:, 1] - y0) / 10.0
    j = np.clip(np.floor(u).astype(int), 0, H.shape[1] - 2)
    ii = np.clip(np.floor(v).astype(int), 0, H.shape[0] - 2)
    fu, fv = np.clip(u - j, 0, 1), np.clip(v - ii, 0, 1)
    g = (H[ii, j] * (1 - fu) * (1 - fv) + H[ii, j + 1] * fu * (1 - fv) + H[ii + 1, j] * (1 - fu) * fv + H[ii + 1, j + 1] * fu * fv)
    return sid, (e[:, 2] - g).astype(np.float32)


def em(r, iters=200):
    mu, sig, pi, lam = 0.0, 2.0, 0.2, 0.1
    pos = r > 0
    for _ in range(iters):
        n = (1 - pi) * np.exp(-0.5 * ((r - mu) / sig) ** 2) / (np.sqrt(2 * np.pi) * sig)
        x = np.where(pos, pi * lam * np.exp(-lam * np.maximum(r, 0)), 0.0)
        g = x / (n + x + 1e-300)
        w = 1 - g
        mu = float((w * r).sum() / w.sum())
        sig = float(np.sqrt((w * (r - mu) ** 2).sum() / w.sum()))
        pi = float(g.mean())
        lam = float(g.sum() / max((g * np.maximum(r, 0)).sum(), 1e-9))
    return {"mu": round(mu, 3), "sigma": round(sig, 3), "pi": round(pi, 4), "lam": round(lam, 4)}


def main():
    tasks = [(sid, i) for sid in ev.suite_scenarios() for i in RUNS]
    with ProcessPoolExecutor(6) as pool:
        out = list(pool.map(residuals, tasks))
    r = np.concatenate([o[1] for o in out])
    r = r[np.abs(r) < 200]
    model = em(r.astype(float))
    per = {sid: em(np.concatenate([o[1] for o in out if o[0] == sid]).astype(float)) for sid in ev.suite_scenarios()}
    res = {"global": model, "per_scenario": per, "samples": int(len(r)), "train_runs": [RUNS.start, RUNS.stop - 1],
           "quantiles": {q: round(float(np.quantile(r, q)), 2) for q in (0.01, 0.1, 0.5, 0.9, 0.99)}}
    (HERE / "beam_model.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("global", "samples", "quantiles")}, indent=1))


if __name__ == "__main__":
    main()
