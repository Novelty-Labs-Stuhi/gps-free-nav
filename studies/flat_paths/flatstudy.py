"""Flat-world strip study. Per world, N random straight strips >= 10 km across the map; each flown as-is (straight)
and as a path planned over the echo recognisability of the drone's map between the same endpoints (<= 1.3x longer).
Scored by the real scorer with the given navigator; every flown path (true route + navigator estimate) is saved.
Usage: flatstudy.py OUT_DIR EXPERIMENT [--runs 4] [--jobs 9] [--recog-jobs 6] [worlds...]"""
import argparse, heapq, json, os, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from scipy.interpolate import CubicSpline
from gpsfree.evaluate import _world, load_suite, run_one
from gpsfree.paths import WORLDS as WORLDS_DIR
from gpsfree.routes import stable_seed
from gpsfree.sensors import echo_directions
from gpsfree.trajectory import Route, horizontal_distance
from gpsfree.worlds import FLAT_IDS

CELL, RMIN, RMAX, SIGMA, MAX_RATIO = 50.0, 100.0, 500.0, 4.0, 1.3
SPEED, AGL = 10.0, 70.0
STRIP_M = (10000.0, 11000.0)
STEPS = [(di, dj, np.hypot(di, dj) * CELL) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj]
A = None


def scenario(wid):
    return {"id": f"flat_{wid}", "name": wid, "world": wid, "platform": "drone",
            "route": {"speed_mps": SPEED, "length_m": 15000, "agl_m": [40, 100]},
            "map": {"terrain_error_m": 2.0, "terrain_error_corr_m": 300}, "wind": {"mean_mps": [4, 7], "gust_mps": 1.5},
            "start_offset_m": [0, 0]}


def strip(wid, i):
    """Random straight strip: bearing uniform, length 10-11 km, centred near the map centre."""
    rng = np.random.default_rng(stable_seed("strip", wid, i))
    th, L = rng.uniform(0, 2 * np.pi), rng.uniform(*STRIP_M)
    c = rng.uniform(-400, 400, 2)
    u = np.array([np.cos(th), np.sin(th)])
    return c - u * L / 2, c + u * L / 2


def recog_map(sc, out):
    """Avia frame at every 50 m cell of the drone's MAP; score = min RMS frame difference to cells 100-500 m away / SIGMA."""
    path = f"{out}/{sc['world']}_recog.npz"
    if os.path.exists(path):
        d = np.load(path); return d["score"], d["xs"], d["ys"]
    w = _world(sc["world"])
    mp = w.map_world(sc["map"], seed=stable_seed("map", sc["id"]))
    pat = json.load(open("benchmark/rangers/avia.json"))
    dirs = echo_directions(pat["pattern"])
    (x0, y0, _), (x1, y1, _) = mp.meta["bounds"]
    xs, ys = np.arange(x0 + CELL / 2, x1, CELL), np.arange(y0 + CELL / 2, y1, CELL)
    gx, gy = np.meshgrid(xs, ys); xy = np.c_[gx.ravel(), gy.ravel()]
    z = mp.height(xy, ground_only=True) + AGL
    F = np.full((len(xy), len(dirs)), np.nan)
    for a in range(0, len(xy), 20000):
        o = np.repeat(np.c_[xy[a:a + 20000], z[a:a + 20000]], len(dirs), axis=0)
        r = mp.raycast(o, np.tile(dirs, (len(xy[a:a + 20000]), 1)), pat["max_range_m"]).reshape(-1, len(dirs))
        F[a:a + 20000] = np.where(np.isfinite(r), r * dirs[None, :, 2], -pat["max_range_m"])
    F = F.reshape(len(ys), len(xs), len(dirs))
    best = np.full(F.shape[:2], np.inf); k = int(RMAX / CELL)
    for di in range(-k, k + 1):
        for dj in range(-k, k + 1):
            r = np.hypot(di, dj) * CELL
            if not (RMIN <= r <= RMAX): continue
            rms = np.sqrt(np.mean((F - np.roll(np.roll(F, di, 0), dj, 1)) ** 2, axis=2)) / SIGMA
            if di > 0: rms[:di] = np.inf
            if di < 0: rms[di:] = np.inf
            if dj > 0: rms[:, :dj] = np.inf
            if dj < 0: rms[:, dj:] = np.inf
            best = np.minimum(best, rms)
    best[~np.isfinite(best)] = 0
    np.savez(path, score=best, xs=xs, ys=ys)
    return best, xs, ys


class Planner:
    def __init__(self, score, xs, ys):
        self.reward, self.xs, self.ys = np.minimum(score, 1.0), xs, ys

    def cell(self, p):
        return (int(np.clip(round((p[1] - self.ys[0]) / CELL), 0, len(self.ys) - 1)),
                int(np.clip(round((p[0] - self.xs[0]) / CELL), 0, len(self.xs) - 1)))

    def dijkstra(self, a, b, W):
        R, ny, nx = self.reward, len(self.ys), len(self.xs)
        dist = {a: 0.0}; prev = {}; pq = [(0.0, a)]
        while pq:
            c, u = heapq.heappop(pq)
            if u == b: break
            if c > dist.get(u, np.inf): continue
            for di, dj, L in STEPS:
                v = (u[0] + di, u[1] + dj)
                if not (0 <= v[0] < ny and 0 <= v[1] < nx): continue
                nc = c + L * (1 + W * (1 - R[v]))
                if nc < dist.get(v, np.inf):
                    dist[v] = nc; prev[v] = u; heapq.heappush(pq, (nc, v))
        path = [b]
        while path[-1] != a: path.append(prev[path[-1]])
        return np.array([[self.xs[j], self.ys[i]] for i, j in path[::-1]])

    def route_reward(self, r):
        return float(self.reward[tuple(np.array([self.cell(p) for p in r.position[::10]]).T)].mean())

    def plan(self, world, start, goal, name, L0, weights=(8, 4, 2, 1, 0.5, 0.25)):
        """Cheapest grid path (cost/m = 1 + W (1 - recognisability)), W loosened until <= MAX_RATIO x the straight length."""
        a, b = self.cell(start), self.cell(goal)
        for W in weights:
            grid = self.dijkstra(a, b, W)
            grid[0], grid[-1] = start, goal
            arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(grid, axis=0), axis=1))]
            s = np.arange(0, arc[-1], 150)
            wp = np.vstack([np.c_[np.interp(s, arc, grid[:, 0]), np.interp(s, arc, grid[:, 1])], grid[-1]])
            r = to_route(world, wp, name)
            if horizontal_distance(r.position)[-1] <= MAX_RATIO * L0:
                return W, r
        return 0, to_route(world, np.array([start, goal]), name)


def to_route(world, pts, name, speed=SPEED, agl=AGL):
    """Waypoints -> constant-speed route with the generator's smoothing and terrain-following altitude."""
    chord = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    dense = CubicSpline(chord, pts)(np.linspace(0, chord[-1], int(chord[-1] / 0.5))) if len(pts) > 2 else \
        pts[0] + np.linspace(0, 1, int(chord[-1] / 0.5))[:, None] * (pts[1] - pts[0])
    arc = horizontal_distance(np.c_[dense, np.zeros(len(dense))])
    t = np.arange(0, arc[-1] / speed, 0.1)
    xy = np.c_[np.interp(t * speed, arc, dense[:, 0]), np.interp(t * speed, arc, dense[:, 1])]
    top = world.height(xy)
    k = int(200 / (speed * 0.1))
    pad = np.pad(top, k, mode="edge")
    clearance = np.array([pad[i:i + 2 * k + 1].max() for i in range(len(top))])
    z = np.maximum(np.convolve(np.pad(clearance, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "valid") + agl, top + 20)
    vel = np.gradient(xy, t, axis=0)
    return Route(name, world.id, "drone", t, np.c_[xy, z], np.unwrap(np.arctan2(vel[:, 1], vel[:, 0])), source="planned")


def task(args):
    try:
        return _task(args)
    except Exception as e:
        import traceback
        print(f"    task {args[0]} r{args[1]:02d} FAILED: {e!r}", flush=True); traceback.print_exc()
        return {"world": args[0], "run": args[1], "error": repr(e)}


def _task(args):
    wid, i = args
    import gpsfree.evaluate as ev
    if wid not in ev._worlds:
        ev._worlds.clear()  # one world per process (world + map ~ 11 GB)
    t0 = time.time()
    sc = scenario(wid); suite = load_suite()
    world = _world(wid)
    pl = Planner(*recog_map(sc, A.out))
    start, goal = strip(wid, i)
    straight = to_route(world, np.array([start, goal]), f"{sc['id']}-s{i:02d}")
    L0 = horizontal_distance(straight.position)[-1]
    W, planned = pl.plan(world, start, goal, f"{sc['id']}-p{i:02d}", L0)
    row = {"world": wid, "run": i, "W": W, "recog_frac": float((pl.reward >= 1).mean()),
           "start": start.round(1).tolist(), "goal": goal.round(1).tolist(), "path": {}}
    for kind, r in (("straight", straight), ("plan", planned)):
        rec = {}
        m = run_one(A.experiment, sc, i, suite, save_trajectory=False, hooks={"route": r, "record": rec})
        row[kind] = {"len": round(float(horizontal_distance(r.position)[-1])), "recog": round(pl.route_reward(r), 3),
                     "score_log10": m["score_log10"], "lost": m["lost"], "lost_at_m": m["lost_at_m"], "mae_m": m["mae_m"],
                     "max_error_m": m["max_error_m"]}
        k = 10  # 1 Hz: true position flown and the navigator's estimate
        row["path"][kind] = {"t": np.round(rec["score_t"][::k], 1).tolist(),
                             "truth": np.round(rec["traj"].sample(rec["score_t"][::k])["p"], 1).tolist(),
                             "est": np.round(np.nan_to_num(rec["est"][::k]), 1).tolist()}
    print(f"    task {wid} r{i:02d} {time.time()-t0:.0f}s", flush=True)
    return row


def _recog(w):
    import gpsfree.evaluate as ev
    recog_map(scenario(w), A.out)
    ev._worlds.clear()


def report(rows, header=True):
    by = {}
    for r in rows:
        if "straight" in r: by.setdefault(r["world"], []).append(r)
    if not by: return
    med = lambda rs, k: 10 ** np.median([r[k]["score_log10"] for r in rs])
    lost = lambda rs, k: np.mean([r[k]["lost"] for r in rs])
    if header:
        print(f"\n{'world':22s} recog%  len s/p (m)    score s/p (m)       lost s/p   lost_at s/p (km)")
    for w, rs in by.items():
        L = lambda k: int(np.median([r[k]["len"] for r in rs]))
        la = lambda k: np.median([r[k]["lost_at_m"] for r in rs]) / 1000
        print(f"{w:22s} {100*rs[0]['recog_frac']:5.1f}  {L('straight'):6d}/{L('plan'):6d}  {med(rs,'straight'):8.1f}/{med(rs,'plan'):8.1f}  "
              f"{lost(rs,'straight'):4.0%}/{lost(rs,'plan'):4.0%}   {la('straight'):5.1f}/{la('plan'):5.1f}", flush=True)
    if len(by) > 1:
        print(f"{'ALL (geomean of world medians)':22s}  " + "/".join(f"{10**np.mean([np.log10(med(rs,k)) for rs in by.values()]):8.1f}" for k in ("straight", "plan"))
              + "   " + "/".join(f"{np.mean([lost(rs,k) for rs in by.values()]):.0%}" for k in ("straight", "plan")), flush=True)


def main():
    global A
    p = argparse.ArgumentParser()
    p.add_argument("out"); p.add_argument("experiment")
    p.add_argument("--runs", type=int, default=4); p.add_argument("--jobs", type=int, default=9); p.add_argument("--recog-jobs", type=int, default=6)
    p.add_argument("worlds", nargs="*")
    A = p.parse_args()
    os.makedirs(A.out, exist_ok=True)
    worlds = A.worlds or [w for w in FLAT_IDS if (WORLDS_DIR / w / "meta.json").exists()]
    print(f"{len(worlds)} worlds x {A.runs} strips x 2 routes (straight, planned), strips {STRIP_M[0]/1000:.0f}-{STRIP_M[1]/1000:.0f} km, {A.experiment}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(A.recog_jobs) as pool:
        list(pool.map(_recog, worlds))
    print(f"recognisability maps done in {time.time()-t0:.0f}s", flush=True)
    rows = []
    for w in list(worlds):
        if os.path.exists(f"{A.out}/{w}.json"):
            rows += json.load(open(f"{A.out}/{w}.json")); worlds.remove(w)
    tasks = [(w, i) for w in worlds for i in range(A.runs)]
    pending = []
    with ProcessPoolExecutor(A.jobs) as pool:
        for k, row in enumerate(pool.map(task, tasks, chunksize=1)):
            pending.append(row)
            if (k + 1) % A.runs == 0:
                json.dump(pending, open(f"{A.out}/{row['world']}.json", "w"))
                rows += pending; pending = []
                report([r for r in rows if r["world"] == row["world"]], header=k + 1 == A.runs)
                print(f"      ({k+1}/{len(tasks)} tasks, {time.time()-t0:.0f}s)", flush=True)
    json.dump(rows, open(f"{A.out}/rows.json", "w"))
    print("\n=== FINAL"); report(rows)


if __name__ == "__main__":
    main()
