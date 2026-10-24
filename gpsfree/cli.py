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
    print(f"[{wid}] {meta['triangles'] / 1e6:.2f}M triangles in {time.time() - t0:.0f}s")
    (WORLDS / "index.json").write_text(json.dumps(sorted(p.name for p in WORLDS.iterdir() if (p / "meta.json").exists())))


def cmd_fetch(args):
    from gpsfree.worlds import WORLDS as CATALOGUE

    for wid in args.worlds or list(CATALOGUE):
        fetch_world(wid)


def cmd_routes(args):
    from gpsfree.routes import generate_all
    from gpsfree.world import World

    for wid in args.worlds or json.loads((WORLDS / "index.json").read_text()):
        for p in generate_all(World(wid), args.per_platform):
            print(p.relative_to(ROOT))


def cmd_eval(args):
    from gpsfree.evaluate import evaluate, results_path

    res = evaluate(args.experiment, args.world, args.platform, args.jobs)
    if not res["partial"]:
        results_path(args.experiment).write_text(json.dumps(res, indent=1))
    print_summary(res)
    if res["partial"]:
        print("(partial run: --world/--platform given, results.json not written)")


def cmd_verify(args):
    """Re-run committed experiments and fail if their results.json can't be reproduced."""
    from gpsfree.evaluate import compare, evaluate, results_path

    failed = False
    for exp in args.experiments or list_experiments():
        path = results_path(exp)
        if not path.exists():
            print(f"✗ {exp}: no results.json (run `uv run gpsfree eval {exp}` and commit it)")
            failed = True
            continue
        problems = compare(json.loads(path.read_text()), evaluate(exp, jobs=args.jobs))
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


def list_experiments():
    return sorted(p.parent.name for p in EXPERIMENTS.glob("*/algo.py"))


def print_summary(res):
    print(f"\n{res['experiment']}  (suite {res['suite']}, {len(res['runs'])} runs, {res['elapsed_s']}s)")
    for key, s in res["summary"].items():
        mae = "  ".join(f"{band}={v}" for band, v in s["mae_m"].items())
        print(f"  {key:18s} score {s['score_m']} m (10^{s['score_log10']})  lost@{s['lost_at_m']} m  k={s['growth_k']}  "
              f"rtf≥{s['min_realtime_factor']}\n  {'':18s} MAE {mae}")


def main():
    ap = argparse.ArgumentParser(prog="gpsfree")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="download + bake worlds into data/worlds")
    p.add_argument("worlds", nargs="*")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("routes", help="(re)generate procedural benchmark routes")
    p.add_argument("worlds", nargs="*")
    p.add_argument("--per-platform", type=int, default=3)
    p.set_defaults(func=cmd_routes)

    p = sub.add_parser("eval", help="run an experiment on the benchmark, write results.json")
    p.add_argument("experiment")
    p.add_argument("--world", action="append", help="limit to world(s); partial runs don't write results")
    p.add_argument("--platform", action="append", choices=["drone", "walker"])
    p.add_argument("--jobs", type=int)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("verify", help="re-run experiments and check committed results reproduce (CI)")
    p.add_argument("experiments", nargs="*")
    p.add_argument("--jobs", type=int)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("leaderboard", help="regenerate the README leaderboard from experiments/*/results.json")
    p.set_defaults(func=cmd_leaderboard)

    p = sub.add_parser("new", help="start a new experiment from a template")
    p.add_argument("name")
    p.add_argument("--template", default="imu_deadreckoning")
    p.set_defaults(func=cmd_new)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
