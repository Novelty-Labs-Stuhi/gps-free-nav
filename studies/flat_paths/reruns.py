"""Fly one strip of one world many times (different noise seeds) on the straight route and on the planned route;
save every flown path and estimate. Usage: reruns.py OUT WORLD STRIP_INDEX SEEDS EXPERIMENT [--jobs 3]"""
import json, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import flatstudy as F
from gpsfree.evaluate import _world, load_suite, run_one
from gpsfree.trajectory import horizontal_distance
out, wid, idx, K, exp = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 3
F.A = F.argparse.Namespace(out=out, experiment=exp)


def routes():
    world = _world(wid); sc = F.scenario(wid)
    pl = F.Planner(*F.recog_map(sc, out))
    start, goal = F.strip(wid, idx)
    straight = F.to_route(world, np.array([start, goal]), "s")
    W, planned = pl.plan(world, start, goal, "p", horizontal_distance(straight.position)[-1])
    return sc, start, goal, {"straight": straight, "plan": planned}


def one(args):
    kind, seed = args
    sc, start, goal, R = routes()
    rec = {}
    m = run_one(exp, sc, seed, load_suite(), save_trajectory=False, hooks={"route": R[kind], "record": rec})
    k = 10
    return {"kind": kind, "seed": seed, "score_log10": m["score_log10"], "lost": m["lost"], "lost_at_m": m["lost_at_m"],
            "len": round(float(horizontal_distance(R[kind].position)[-1])),
            "truth": np.round(rec["traj"].sample(rec["score_t"][::k])["p"], 1).tolist(), "est": np.round(np.nan_to_num(rec["est"][::k]), 1).tolist()}


if __name__ == "__main__":
    sc, start, goal, R = routes()
    with ProcessPoolExecutor(jobs) as pool:
        runs = list(pool.map(one, [(k, s) for k in ("straight", "plan") for s in range(K)]))
    json.dump({"world": wid, "strip": idx, "experiment": exp, "start": start.tolist(), "goal": goal.tolist(), "runs": runs},
              open(f"{out}/{wid}_strip{idx}_{exp}_reruns.json", "w"))
    for r in runs:
        print(f"{r['kind']:8s} seed {r['seed']}  {10**r['score_log10']:8.0f} m  lost at {r['lost_at_m']/1000:5.1f} km")
