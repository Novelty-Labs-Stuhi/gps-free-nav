"""One world, the strip with the largest score gap: full recognisability heat map with the straight strip, the
planned path, and the navigator's estimated track for each (dashed)."""
import json, sys
import numpy as np, os
D = os.environ.get('FLAT_DIR', 'data/flat')
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
w = sys.argv[1]
d = np.load(f"{D}/recog/{w}_recog.npz"); xs, ys, S = d["xs"], d["ys"], d["score"]
rows = [r for r in json.load(open(f"{D}/{w}.json")) if "straight" in r]
cell = float(xs[1] - xs[0]); ext = [xs[0] - cell / 2, xs[-1] + cell / 2, ys[0] - cell / 2, ys[-1] + cell / 2]
fmt = lambda m: f"{10**m['score_log10']:.0f} m, " + (f"lost at {m['lost_at_m']/1000:.1f} km" if m["lost"] else "never lost") + f", {m['len']/1000:.1f} km"
r = max(rows, key=lambda r: abs(r["straight"]["score_log10"] - r["plan"]["score_log10"]))
fig, ax = plt.subplots(figsize=(16, 15))
im = ax.imshow(np.log10(S + 0.01), origin="lower", extent=ext, cmap="magma", vmin=-2, vmax=1, interpolation="bilinear")
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.set_label("log10 recognisability of the drone's map (0 = lidar frame unique within 500 m)")
for kind, col, lab in (("straight", "#00c8ff", "straight strip"), ("plan", "#00ff6a", "planned over recognisability")):
    tr = np.array(r["path"][kind]["truth"]); es = np.array(r["path"][kind]["est"])
    ax.plot(tr[:, 0], tr[:, 1], color=col, lw=3, label=f"{lab}: flown, {fmt(r[kind])}")
    ax.plot(es[:, 0], es[:, 1], color=col, lw=1.2, ls="--", alpha=0.9, label=f"{lab}: navigator's estimate")
ax.plot(*r["start"], "o", color="cyan", ms=12, mec="k", label="start"); ax.plot(*r["goal"], "s", color="magenta", ms=12, mec="k", label="goal")
ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_xlabel("east (m)"); ax.set_ylabel("north (m)")
ax.set_title(f"{w}, strip {r['run']} (largest gap of {len(rows)})", fontsize=14); ax.legend(loc="lower left", fontsize=11)
fig.tight_layout(); fig.savefig(f"{D}/{w}_best_run.png", dpi=90)
print(f"{D}/{w}_best_run.png")
