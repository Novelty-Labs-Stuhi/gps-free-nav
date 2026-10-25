"""PF vs EKF on the same 200 strips: per world, planned-vs-straight gain against how recognisable the map is."""
import glob, json
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
def load(d):
    rows = [r for f in glob.glob(f"{d}/*.json") if "rows" not in f and "reruns" not in f for r in json.load(open(f)) if "straight" in r]
    by = {}
    for r in rows: by.setdefault(r["world"], []).append(r)
    return by
P, E = load("data/flat"), load("data/flat_ekf")
worlds = sorted(set(P) & set(E), key=lambda w: P[w][0]["recog_frac"])
rec = np.array([100 * P[w][0]["recog_frac"] for w in worlds])
med = lambda by, w, k: np.median([r[k]["score_log10"] for r in by[w]])
la = lambda by, w, k: np.median([r[k]["lost_at_m"] for r in by[w]]) / 1000
fig, ax = plt.subplots(2, 2, figsize=(18, 12))
for j, (by, name) in enumerate(((P, "particle filter (ins_echo_avia_adis16470)"), (E, "EKF (terrain_ekf, icm42688p + avia)"))):
    gain = np.array([med(by, w, "straight") - med(by, w, "plan") for w in worlds])
    a = ax[0, j]; a.axhline(0, color="k", lw=0.8)
    a.bar(range(len(worlds)), gain, color=np.where(gain > 0, "#2ca02c", "#d62728"))
    a.set_xticks(range(len(worlds))); a.set_xticklabels([f"{w} ({r:.1f}%)" for w, r in zip(worlds, rec)], rotation=80, ha="right", fontsize=7)
    a.set_ylabel("log10(straight score) - log10(planned score)\n> 0: planned better"); a.set_title(f"{name}: planner gain per world, sorted by recognisable share of the map")
    s = np.array([r["straight"]["score_log10"] for w in worlds for r in by[w]]); p = np.array([r["plan"]["score_log10"] for w in worlds for r in by[w]])
    a.text(0.02, 0.95, f"geomean straight {10**s.mean():.0f} m, planned {10**p.mean():.0f} m; planned better in {np.mean(p < s-0.05):.0%} of strips, worse in {np.mean(p > s+0.05):.0%}",
           transform=a.transAxes, va="top", fontsize=10, bbox=dict(fc="w", alpha=0.8))
    a = ax[1, j]
    a.scatter(rec, [la(by, w, "straight") for w in worlds], color="#1f77b4", label="straight strip", s=40)
    a.scatter(rec, [la(by, w, "plan") for w in worlds], color="#2ca02c", label="planned path", s=40, marker="s")
    for w, r in zip(worlds, rec):
        a.plot([r, r], [la(by, w, "straight"), la(by, w, "plan")], color="gray", lw=0.8, alpha=0.6)
    a.set_xscale("log"); a.set_xlabel("recognisable share of the map (%)"); a.set_ylabel("median distance before lost (km)"); a.legend(); a.grid(alpha=0.3)
    a.set_title(f"{name}: how far before the filter is off by 50 m")
fig.suptitle("50 flat worlds, 4 random 10-11 km strips each, straight vs planned over echo recognisability", fontsize=14)
fig.tight_layout(); fig.savefig("data/flat/compare_pf_ekf.png", dpi=90); print("data/flat/compare_pf_ekf.png")
