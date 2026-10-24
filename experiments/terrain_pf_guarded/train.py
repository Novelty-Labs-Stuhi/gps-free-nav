"""Train the lost detector on TRAINING runs 20-39 of every scenario (never the scored runs 0-19).

Label: 1 when the true horizontal error exceeds the 50 m alert limit. Model: L2 logistic regression in numpy on
standardised features. Reports leave-one-scenario-out AUC and picks the threshold that catches 95% of lost samples
in training. Writes lost_model.json."""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import gpsfree.evaluate as ev

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import features  # noqa: E402

RUNS = range(20, 40)
ALERT_M = 50.0


class Recorder(ev.load_algorithm("terrain_pf")):
    def uncertainty(self):
        self.__dict__.setdefault("feats", []).append(features.vector(self.diagnostics()))
        return super().uncertainty()


def one(task):
    sid, i = task
    rec = {}
    ev.run_one("terrain_pf", sid, i, ev.load_suite(), save_trajectory=False, hooks={"record": rec, "algo_cls": Recorder})
    truth = rec["traj"].sample(rec["score_t"])["p"]
    err = np.linalg.norm(rec["est"][:, :2] - truth[:, :2], axis=1)
    X = np.array(rec["algo"].feats)
    return sid, X[::5], (err[::5] > ALERT_M).astype(float)


def fit(X, y, l2=1e-2, iters=400, lr=0.5):
    w, b = np.zeros(X.shape[1]), 0.0
    pos = max(y.mean(), 1e-3)
    sw = np.where(y > 0, 0.5 / pos, 0.5 / (1 - pos))  # balance the classes
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = (p - y) * sw
        w -= lr * (X.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return w, b


def auc(score, y):
    order = np.argsort(score)
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    npos, nneg = y.sum(), len(y) - y.sum()
    return float((ranks[y > 0].sum() - npos * (npos + 1) / 2) / max(npos * nneg, 1))


def main():
    tasks = [(sid, i) for sid in ev.suite_scenarios() for i in RUNS]
    with ProcessPoolExecutor() as pool:
        data = list(pool.map(one, tasks))
    X = np.concatenate([d[1] for d in data])
    y = np.concatenate([d[2] for d in data])
    sids = np.concatenate([[d[0]] * len(d[2]) for d in data])
    mean, std = X.mean(0), X.std(0) + 1e-9
    Z = (X - mean) / std
    loso = {}
    for s in ev.suite_scenarios():
        tr, te = sids != s, sids == s
        if 0 < y[te].sum() < te.sum():
            w, b = fit(Z[tr], y[tr])
            loso[s] = round(auc(Z[te] @ w + b, y[te]), 3)
    w, b = fit(Z, y)
    p = 1 / (1 + np.exp(-(Z @ w + b)))
    thr = float(np.quantile(p[y > 0], 0.05))  # catch 95% of lost samples
    out = {"features": features.NAMES, "mean": mean.tolist(), "std": std.tolist(), "w": w.round(4).tolist(),
           "b": round(float(b), 4), "threshold": round(thr, 4), "train_runs": [RUNS.start, RUNS.stop - 1],
           "samples": int(len(y)), "lost_share": round(float(y.mean()), 3), "auc_train": round(auc(p, y), 3),
           "auc_leave_one_scenario_out": loso,
           "false_alarm_train": round(float(np.mean(p[y == 0] > thr)), 3)}
    (HERE / "lost_model.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("samples", "lost_share", "auc_train", "threshold", "false_alarm_train", "auc_leave_one_scenario_out")}, indent=1))
    print("weights:", dict(zip(features.NAMES, out["w"])))


if __name__ == "__main__":
    main()
