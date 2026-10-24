"""X5: learn a decision policy by cross-entropy-method policy search (no gradients, no torch).

Each iteration samples POP candidate MLP weight vectors around the current mean, flies every candidate on the SAME
EPISODES training missions (seeds 0-999 only; evaluation uses 1000+), keeps the top ELITE by mean reward and moves
the mean and spread towards them. The policy reads the navigator's belief (radius, P(lost), distance to goal,
margin to the no-fly line, terrain informativeness, battery, height) and picks continue/climb/detour/slow/land.
Starts from 'always continue'. Progress goes to train_log.json, the current best to policy.json, every iteration."""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from gpsfree.closedloop import MLPPolicy, episode
from gpsfree.evaluate import suite_scenarios

HERE = Path(__file__).parent
NAVIGATOR = "terrain_pf_guarded"


def init_mean(rng):
    mu = rng.normal(0, 0.1, MLPPolicy.size())
    mu[-5:] = [1.0, -1.0, -1.0, -1.0, -1.0]  # output bias: start as 'always continue'
    return mu


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--episodes", type=int, default=4)
    ap.add_argument("--elite", type=float, default=0.25)
    ap.add_argument("--jobs", type=int)
    args = ap.parse_args()
    rng = np.random.default_rng(0)
    mu, sigma = init_mean(rng), np.full(MLPPolicy.size(), 0.5)
    scen = suite_scenarios()
    log, best = [], (-np.inf, None)
    with ProcessPoolExecutor(args.jobs) as pool:
        for it in range(args.iters):
            t0 = time.time()
            eps = [(scen[rng.integers(len(scen))], int(rng.integers(0, 1000))) for _ in range(args.episodes)]
            cands = [mu] + [mu + sigma * rng.normal(size=mu.shape) for _ in range(args.pop - 1)]
            tasks = [(sid, seed, NAVIGATOR, c.tolist()) for c in cands for sid, seed in eps]
            res = list(pool.map(episode, tasks, chunksize=1))
            R = np.array([r["reward"] for r in res]).reshape(args.pop, args.episodes).mean(1)
            S = np.array([r["success"] for r in res]).reshape(args.pop, args.episodes).mean(1)
            V = np.array([r["violation"] for r in res]).reshape(args.pop, args.episodes).mean(1)
            order = np.argsort(R)[::-1]
            elite = np.array([cands[i] for i in order[: max(2, int(args.elite * args.pop))]])
            mu = 0.7 * elite.mean(0) + 0.3 * mu
            sigma = np.maximum(0.7 * elite.std(0) + 0.3 * sigma, 0.05)
            if R[order[0]] > best[0]:
                best = (float(R[order[0]]), cands[order[0]])
            log.append({"iter": it, "mean_reward": round(float(R.mean()), 2), "best_reward": round(float(R[order[0]]), 2),
                        "mean_policy_reward": round(float(R[0]), 2), "best_success": round(float(S[order[0]]), 2),
                        "mean_success": round(float(S.mean()), 3), "mean_violation": round(float(V.mean()), 3),
                        "sigma": round(float(sigma.mean()), 3), "wall_s": round(time.time() - t0)})
            print(json.dumps(log[-1]), flush=True)
            (HERE / "train_log.json").write_text(json.dumps({"navigator": NAVIGATOR, "args": vars(args), "log": log}, indent=1))
            (HERE / "policy.json").write_text(json.dumps({"params": mu.tolist(), "best_params": best[1].tolist(),
                                                          "iterations": it + 1, "navigator": NAVIGATOR}))


if __name__ == "__main__":
    main()
