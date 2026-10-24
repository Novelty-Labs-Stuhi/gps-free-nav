"""Calibrate the radius of terrain_pf on TRAINING runs (indices 20-59), never on scored runs.
Finds the multiplier k such that, while the drone is within the 50 m alert limit, the true horizontal error is
within RADIUS_FLOOR_M + k * spread 95% of the time, and writes it to calibration.json. Lost-regime samples are
excluded: a collapsed particle cloud in the wrong place says nothing about its error (that is X4's job)."""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import gpsfree.evaluate as ev

HERE = Path(__file__).parent
EXP = HERE.name


def one(task):
    sid, i = task
    rec = {}
    ev.run_one(EXP, sid, i, ev.load_suite(), save_trajectory=False, hooks={"record": rec, "calibrating": True})
    truth = rec["traj"].sample(rec["score_t"])["p"]
    err = np.linalg.norm(rec["est"][:, :2] - truth[:, :2], axis=1)
    unc = rec["unc"]
    ok = np.isfinite(unc) & (np.arange(len(err)) > 20)
    return (err[ok] - 3.0), (unc[ok] - 3.0)


def main(runs=range(20, 26)):
    tasks = [(sid, i) for sid in ev.suite_scenarios() for i in runs]
    with ProcessPoolExecutor() as pool:
        res = list(pool.map(one, tasks))
    e = np.concatenate([r[0] for r in res])
    s = np.concatenate([r[1] for r in res])
    healthy = e + 3.0 < 50.0  # the radius describes the healthy regime; being lost is X4's lost detector's job
    ratio = e[healthy] / np.maximum(s[healthy], 0.5)
    k = float(np.percentile(ratio, 95))
    out = {"radius_k": round(k, 2), "samples": int(len(ratio)), "lost_share_excluded": round(float(1 - healthy.mean()), 3), "runs": len(tasks), "train_runs": [runs.start, runs.stop - 1]}
    (HERE / "calibration.json").write_text(json.dumps(out, indent=1))
    print(out)


if __name__ == "__main__":
    main()
