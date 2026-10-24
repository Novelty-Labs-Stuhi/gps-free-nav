"""Closed-loop mission evaluation shared by X5 (rl_policy) and X6 (rule_policy).
Training episodes use seeds 0-999; evaluation uses seeds 1000+ on every suite scenario, so they never overlap."""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from gpsfree.closedloop import episode
from gpsfree.evaluate import suite_scenarios

NAVIGATOR = "terrain_pf_guarded"
EVAL_SEEDS = range(1000, 1005)


def run(policy_spec, seeds=EVAL_SEEDS, scenarios=None, jobs=None):
    tasks = [(sid, s, NAVIGATOR, policy_spec) for sid in (scenarios or suite_scenarios()) for s in seeds]
    with ProcessPoolExecutor(jobs) as pool:
        return list(pool.map(episode, tasks, chunksize=2))


def summarize(res):
    f = lambda k: float(np.mean([r[k] for r in res]))  # noqa: E731
    return {"episodes": len(res), "success": round(f("success"), 3), "violation": round(f("violation"), 3),
            "battery_out": round(f("battery_out"), 3), "silent_wrong_landing": round(f("silent_wrong_landing"), 3),
            "median_landing_err_m": round(float(np.median([r["landed_err_m"] for r in res])), 1),
            "mean_reward": round(f("reward"), 2),
            "actions": {a: int(sum(r["decisions"].count(a) for r in res)) for a in ["continue", "climb", "detour", "slow", "land"]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("policies", nargs="+", help="continue, rule, or a path to a policy.json")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    table = {}
    for p in args.policies:
        spec = json.loads(Path(p).read_text())["params"] if p.endswith(".json") else p
        t = time.time()
        res = run(spec)
        table[Path(p).parent.name if p.endswith(".json") else p] = summarize(res) | {"wall_s": round(time.time() - t)}
        print(p, json.dumps(table[list(table)[-1]]), flush=True)
    if args.out:
        args.out.write_text(json.dumps({"navigator": NAVIGATOR, "eval_seeds": [EVAL_SEEDS.start, EVAL_SEEDS.stop - 1],
                                        "scenarios": suite_scenarios(), "policies": table}, indent=1))


if __name__ == "__main__":
    main()
