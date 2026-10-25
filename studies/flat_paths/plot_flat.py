"""Overview of every finished world: median score and lost share, straight strip vs planned path; per-run pairs."""
import glob, json, sys
import numpy as np, os
D = os.environ.get('FLAT_DIR', 'data/flat')
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
files = [f for f in sorted(glob.glob(f"{D}/*.json")) if not f.endswith("rows.json")]
rows = [r for f in files for r in json.load(open(f)) if "straight" in r]
by = {}
for r in rows: by.setdefault(r["world"], []).append(r)
worlds = sorted(by, key=lambda w: np.median([r["straight"]["score_log10"] for r in by[w]]))
med = lambda w, k: 10 ** np.median([r[k]["score_log10"] for r in by[w]])
lost = lambda w, k: np.mean([r[k]["lost"] for r in by[w]])
fig, ax = plt.subplots(3, 1, figsize=(max(10, 0.35 * len(worlds) + 3), 13), gridspec_kw={"height_ratios": [2, 1, 1.4]})
x = np.arange(len(worlds)); wd = 0.38
for j, (k, c, lab) in enumerate((("straight", "#1f77b4", "straight 10-11 km strip"), ("plan", "#2ca02c", "planned over recognisability (<= 1.3x longer)"))):
    ax[0].bar(x + (j - 0.5) * wd, [med(w, k) for w in worlds], wd, color=c, label=lab)
    ax[1].bar(x + (j - 0.5) * wd, [100 * lost(w, k) for w in worlds], wd, color=c)
ax[0].set_yscale("log"); ax[0].set_ylabel("median score (m), log"); ax[0].legend(loc="upper left"); ax[0].grid(axis="y", alpha=0.3)
ax[0].set_title(f"{len(worlds)} flat worlds, {len(rows)} strips, Avia + ADIS16470 particle filter")
ax[1].set_ylabel("runs lost (%)"); ax[1].grid(axis="y", alpha=0.3)
for a in ax[:2]:
    a.set_xticks(x); a.set_xticklabels(worlds, rotation=70, ha="right", fontsize=8)
s = np.array([r["straight"]["score_log10"] for r in rows]); p = np.array([r["plan"]["score_log10"] for r in rows])
rec = np.array([r["plan"]["recog"] - r["straight"]["recog"] for r in rows])
sc = ax[2].scatter(10 ** s, 10 ** p, c=rec, cmap="viridis", s=18, alpha=0.85)
lim = [1, max(10 ** s.max(), 10 ** p.max()) * 1.2]
ax[2].plot(lim, lim, "k--", lw=0.8); ax[2].set_xscale("log"); ax[2].set_yscale("log"); ax[2].set_xlim(lim); ax[2].set_ylim(lim)
ax[2].set_xlabel("straight strip score (m)"); ax[2].set_ylabel("planned path score (m)")
plt.colorbar(sc, ax=ax[2], label="recognisability gained by planning (0-1)")
better = np.mean(p < s - 0.05); worse = np.mean(p > s + 0.05)
ax[2].set_title(f"{len(rows)} strips: planned better in {better:.0%}, worse in {worse:.0%}, tie {1-better-worse:.0%}  |  geomean straight {10**s.mean():.0f} m, planned {10**p.mean():.0f} m")
fig.tight_layout(); fig.savefig(sys.argv[1], dpi=90)
print(f"{len(worlds)} worlds, {len(rows)} strips plotted -> {sys.argv[1]}")
