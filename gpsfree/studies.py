"""Stress studies: re-run an experiment under changed conditions and save what happened.

`uv run gpsfree study <name>` writes data/studies/<name>.json (summary per variant plus the
median error-vs-distance curve) and keeps each run's trajectory under data/runs/_study/.
The viewer (`uv run gpsfree viz`) shows every saved study. Committed results.json files are
never touched: studies change the conditions, so they are not leaderboard entries."""
import json
import time

import numpy as np

import gpsfree.evaluate as ev
from gpsfree.paths import DATA, RUNS
from gpsfree.trajectory import path_length

STUDIES = DATA / "studies"
CURVE_STEP_M = 50.0


# ------------------------------------------------------------------ runner
STUDY_RUNS = 10


def _run_variant(study, label, scenario, algo_cls, runs=STUDY_RUNS, **hooks):
    """Run one variant of a study on `runs` runs of a suite scenario; hooks: sensor_world, map, start_offset."""
    suite = ev.load_suite()
    sid = scenario
    tag = f"_study/{study}/{label}"
    out = [ev.run_one(tag, sid, i, suite, save_trajectory=True, hooks={"algo_cls": algo_cls, **hooks}) for i in range(runs)]
    curves = []
    for i in range(runs):
        d = json.loads((RUNS / tag / f"{sid}__r{i:02d}.json").read_text())
        tr, es = np.array(d["truth"]), np.array(d["estimate"])
        curves.append((path_length(tr), np.linalg.norm(es - tr, axis=1)))
    grid = np.arange(0, min(c[0][-1] for c in curves), CURVE_STEP_M)
    E = np.array([np.interp(grid, dist, err) for dist, err in curves])
    rms = [float(np.hypot(r["xy_rmse_m"], r["z_rmse_m"])) for r in out]
    integ = [r for r in out if r.get("integrity")]
    return {"label": label, "scenario": sid,
            "score_m": float(10 ** np.median([r["score_log10"] for r in out])),
            "median_rms_m": float(np.median(rms)), "worst_rms_m": float(max(rms)),
            "lost_at_m": float(np.median([r["lost_at_m"] for r in out])),
            "lost_runs": int(sum(r["lost"] for r in out)), "runs": len(out),
            "misleading_frac": float(np.mean([r["misleading_frac"] for r in integ])) if integ else None,
            "silent_runs": int(sum(r["silent_failure"] for r in integ)) if integ else None,
            "curve": {"dist": grid.round(0).tolist(), "median": np.median(E, 0).round(3).tolist(),
                      "p90": np.percentile(E, 90, 0).round(3).tolist()}}


def _save(name, title, question, variants, notes, reference=True):
    STUDIES.mkdir(parents=True, exist_ok=True)
    out = STUDIES / f"{name}.json"
    out.write_text(json.dumps({"name": name, "title": title, "question": question, "experiment": "terrain_ekf",
                               "created": time.strftime("%Y-%m-%d %H:%M"), "variants": variants, "notes": notes,
                               "reference": reference}, indent=1))
    return out


def study_ablation():
    Base = ev.load_algorithm("terrain_ekf")

    class NoEcho(Base):
        def on_echo(self, t, ranges):
            pass

    class DownOnly(Base):
        MIN_BEAMS = 1

        def on_echo(self, t, ranges):
            r = np.full_like(ranges, np.inf)
            r[-1] = ranges[-1]
            super().on_echo(t, r)

    v = [_run_variant("ablation", "full method", "alpine", Base),
         _run_variant("ablation", "down beam only", "alpine", DownOnly),
         _run_variant("ablation", "echo off", "alpine", NoEcho)]
    return _save("ablation", "Where does the accuracy come from?",
                 "Alpine valley scenario: switch parts of the terrain filter off and see what is left.", v,
                 "Echo off leaves the same filter on the $8 IMU alone. Down beam only is a single laser altimeter.")


def study_wrong_start():
    Base = ev.load_algorithm("terrain_ekf")
    v = [_run_variant("wrong_start", f"start {d} m off", "alpine", Base, start_offset=[d, 0, 0]) for d in (0, 20, 100, 500)]
    return _save("wrong_start", "What if the start position is wrong?",
                 "Alpine valley: the filter starts east of where it really is, as after a spoofed GNSS handover, and is told so.", v,
                 "The filter widens its start uncertainty to the told sigma; large offsets still lock onto the wrong terrain.")


def study_map_error():
    Base = ev.load_algorithm("terrain_ekf")
    world = ev._world(ev.load_scenario("alpine")["world"])
    v = []
    for sigma in (0.0, 0.5, 2.0, 5.0):
        mp = world.map_world({"terrain_error_m": sigma, "terrain_error_corr_m": 150} if sigma else {}, seed=7)
        v.append(_run_variant("map_error", f"map error {sigma:g} m", "alpine", Base, map=mp))
    return _save("map_error", "What if the terrain map is imperfect?",
                 "Alpine valley: the sensors see the real terrain; the drone's map has smooth height errors of the given size.", v,
                 "0.5 m is a good lidar survey, 2 to 5 m is typical free global elevation data.")


def study_trees():
    Base = ev.load_algorithm("terrain_ekf")
    world = ev._world(ev.load_scenario("boreal")["world"])
    spec = ev.load_scenario("boreal")["map"]
    v = [_run_variant("trees", "map knows every tree", "boreal", Base, map=world.map_world(spec | {"trees": True}, seed=7)),
         _run_variant("trees", "map has no trees", "boreal", Base, map=world.map_world(spec, seed=7))]
    return _save("trees", "What if the map has no trees?",
                 "Boreal forest scenario: the real world has forest; the drone's map either contains every tree or none.", v,
                 "No real map knows every tree; the gap between the two variants is what unmapped forest costs.")


ALL = {"ablation": study_ablation, "wrong_start": study_wrong_start, "map_error": study_map_error, "trees": study_trees}
