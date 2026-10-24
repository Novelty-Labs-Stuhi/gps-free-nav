import argparse
import json
import shutil
import sys
import time

from gpsfree.paths import EXPERIMENTS, ROOT, WORLDS


def fetch_world(wid):
    from gpsfree.worlds import WORLDS as CATALOGUE
    from gpsfree.worlds.bake import bake
    from gpsfree.worlds.fetch import fetch_city, fetch_terrain

    cfg = CATALOGUE[wid]
    out = WORLDS / wid
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print(f"[{wid}] downloading…", flush=True)
    raw = (fetch_city if cfg["kind"] == "city" else fetch_terrain)(cfg, out)
    print(f"[{wid}] baking…", flush=True)
    meta = bake(wid, cfg, out, raw)
    print(f"[{wid}] {meta['triangles'] / 1e6:.2f}M triangles, {meta.get('buildings', 0)} buildings, "
          f"{meta.get('trees', 0)} trees in {time.time() - t0:.0f}s")
    (WORLDS / "index.json").write_text(json.dumps(sorted(p.name for p in WORLDS.iterdir() if (p / "meta.json").exists())))


def suite_worlds():
    from gpsfree.evaluate import load_scenario, suite_scenarios
    return sorted({load_scenario(s)["world"] for s in suite_scenarios()})


def _fetch_if_needed(wid):
    from gpsfree.worlds.bake import BAKE_VERSION
    meta = WORLDS / wid / "meta.json"
    if not meta.exists() or json.loads(meta.read_text()).get("bake_version") != BAKE_VERSION:
        fetch_world(wid)


def cmd_fetch(args):
    """Fetch + bake worlds (all catalogue worlds, the given ones, or --suite: those the suite uses) in parallel."""
    from concurrent.futures import ProcessPoolExecutor

    from gpsfree.worlds import WORLDS as CATALOGUE
    ids = args.worlds or (suite_worlds() if args.suite else list(CATALOGUE))
    with ProcessPoolExecutor(args.jobs or 4) as pool:
        list(pool.map(_fetch_if_needed if args.missing else fetch_world, ids))
    (WORLDS / "index.json").write_text(json.dumps(sorted(p.name for p in WORLDS.iterdir() if (p / "meta.json").exists())))


def _routes_for(sid):
    from gpsfree.evaluate import _world, load_scenario, load_suite
    from gpsfree.routes import scenario_route
    sc = load_scenario(sid)
    w = _world(sc["world"])
    for i in range(load_suite()["runs_per_scenario"]):
        scenario_route(sc, i, w)
    return sid


def cmd_routes(args):
    """Generate (and cache in data/routes) every route of the suite's scenarios."""
    from concurrent.futures import ProcessPoolExecutor

    from gpsfree.evaluate import suite_scenarios
    with ProcessPoolExecutor(args.jobs) as pool:
        for sid in pool.map(_routes_for, args.scenarios or suite_scenarios()):
            print(f"routes ready: {sid}", flush=True)


def cmd_eval(args):
    from gpsfree.evaluate import evaluate, results_path

    runs = 3 if args.quick else args.runs
    res = evaluate(args.experiment, args.scenario, runs, args.jobs)
    if not res["partial"]:
        results_path(args.experiment).write_text(json.dumps(res, indent=1))
    print_summary(res)
    if res["partial"]:
        print("(partial run: --scenario/--runs/--quick given, results.json not written)")


def cmd_verify(args):
    """Re-run committed experiments and fail if their results.json can't be reproduced or their hardware is over budget."""
    from gpsfree.evaluate import compare, evaluate, results_path
    from gpsfree.leaderboard import MAX_COST_USD, hardware_cost, within_budget

    failed = False
    for exp in args.experiments or list_experiments():
        path = results_path(exp)
        if not path.exists():
            print(f"✗ {exp}: no results.json (run `uv run gpsfree eval {exp}` and commit it)")
            failed = True
            continue
        if not within_budget(exp):
            print(f"✗ {exp}: hardware costs ${hardware_cost(exp):,.0f}, must be under ${MAX_COST_USD:,}")
            failed = True
            continue
        t0 = time.time()
        problems = compare(json.loads(path.read_text()), evaluate(exp, jobs=args.jobs))
        if args.max_seconds and time.time() - t0 > args.max_seconds:
            problems.append(f"took {time.time() - t0:.0f}s, over the {args.max_seconds:.0f}s CI budget")
        print(f"{'✗' if problems else '✓'} {exp}")
        for p in problems:
            print(f"    {p}")
        failed |= bool(problems)
    sys.exit(1 if failed else 0)


def cmd_leaderboard(args):
    from gpsfree.leaderboard import render, update_readme

    path = ROOT / "README.md"
    path.write_text(update_readme(path.read_text() if path.exists() else "", render()))
    print(f"updated {path.relative_to(ROOT)}")


def cmd_new(args):
    dst = EXPERIMENTS / args.name
    if dst.exists():
        sys.exit(f"{dst} already exists")
    shutil.copytree(EXPERIMENTS / args.template, dst, ignore=shutil.ignore_patterns("results.json", "__pycache__"))
    print(f"created {dst.relative_to(ROOT)} from {args.template}; edit algo.py then `uv run gpsfree eval {args.name}`")


def cmd_viz(args):
    from gpsfree.viz import build

    out = build(args.experiments or None, args.jobs)
    print(f"wrote {out.relative_to(ROOT)} (open it in a browser)")


def cmd_study(args):
    from gpsfree.studies import ALL

    unknown = set(args.names) - set(ALL)
    if unknown:
        sys.exit(f"unknown studies {sorted(unknown)}; choose from {list(ALL)}")
    for name in args.names or list(ALL):
        t0 = time.time()
        out = ALL[name]()
        print(f"{name}: wrote {out.relative_to(ROOT)} in {time.time() - t0:.0f}s", flush=True)


def cmd_replay(args):
    from gpsfree.replay import export

    for run in args.run or [0]:
        print("wrote replay", export(args.experiment, args.scenario, run), flush=True)


def list_experiments():
    return sorted(p.parent.name for p in EXPERIMENTS.glob("*/algo.py"))


def print_summary(res):
    print(f"\n{res['experiment']}  (suite {res['suite']}, {len(res['runs'])} runs, {res['elapsed_s']}s)")
    for key, s in res["summary"].items():
        if key == "overall":
            continue
        integ = f"  misleading {s['misleading_frac']:.0%}  silent {s['silent_failure_frac']:.0%}" if "misleading_frac" in s else ""
        print(f"  {key:12s} score {s['score_m']:>10,.1f} m  p90 {s['p90_score_m']:>10,.1f} m  lost {s['lost_frac']:4.0%}{integ}")
    o = res["summary"].get("overall")
    if o:
        integ = f"  misleading {o['misleading_frac']:.0%}  silent {o['silent_failure_frac']:.0%}" if "misleading_frac" in o else ""
        print(f"  {'OVERALL':12s} score {o['score_m']:>10,.1f} m  worst {o['worst_scenario']} ({o['worst_score_m']:,.1f} m)  lost {o['lost_frac']:.0%}{integ}")


def main():
    ap = argparse.ArgumentParser(prog="gpsfree")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="download + bake worlds into data/worlds")
    p.add_argument("worlds", nargs="*")
    p.add_argument("--suite", action="store_true", help="only the worlds the suite's scenarios use")
    p.add_argument("--missing", action="store_true", help="skip worlds that are already baked")
    p.add_argument("--jobs", type=int)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("routes", help="generate and cache every route of the suite's scenarios")
    p.add_argument("scenarios", nargs="*")
    p.add_argument("--jobs", type=int)
    p.set_defaults(func=cmd_routes)

    p = sub.add_parser("eval", help="run an experiment on the benchmark, write results.json")
    p.add_argument("experiment")
    p.add_argument("--scenario", action="append", help="limit to scenario(s); partial runs don't write results")
    p.add_argument("--runs", type=int, help="runs per scenario (default: the suite's)")
    p.add_argument("--quick", action="store_true", help="3 runs per scenario, for iterating")
    p.add_argument("--jobs", type=int)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("verify", help="re-run experiments and check committed results reproduce (CI)")
    p.add_argument("experiments", nargs="*")
    p.add_argument("--jobs", type=int)
    p.add_argument("--max-seconds", type=float, help="fail an experiment whose re-run takes longer than this")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("leaderboard", help="regenerate the README leaderboard from experiments/*/results.json")
    p.set_defaults(func=cmd_leaderboard)

    p = sub.add_parser("new", help="start a new experiment from a template")
    p.add_argument("name")
    p.add_argument("--template", default="imu_deadreckoning")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("study", help="stress studies (map errors, trees, wrong start, ablations) into data/studies")
    p.add_argument("names", nargs="*", help="ablation, wrong_start, map_error, trees, steppe (default: all)")
    p.set_defaults(func=cmd_study)

    p = sub.add_parser("replay", help="export runs for the replay app into data/replays")
    p.add_argument("experiment")
    p.add_argument("scenario")
    p.add_argument("--run", type=int, action="append", help="run index (repeatable; default 0)")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("viz", help="build data/viz/index.html: paths, errors and scores of every run")
    p.add_argument("experiments", nargs="*")
    p.add_argument("--jobs", type=int)
    p.set_defaults(func=cmd_viz)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
