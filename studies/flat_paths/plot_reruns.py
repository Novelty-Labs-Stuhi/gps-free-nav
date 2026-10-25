"""One world, one strip, all seeds: recognisability map, flown routes solid, every seed's estimate dashed;
neon blue = straight strip runs, neon green = planned runs. No legend; stats in the title only."""
import json, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
f = sys.argv[1]
R = json.load(open(f)); w = R["world"]
d = np.load(f"data/flat/recog/{w}_recog.npz"); xs, ys, S = d["xs"], d["ys"], d["score"]
cell = float(xs[1] - xs[0]); ext = [xs[0] - cell / 2, xs[-1] + cell / 2, ys[0] - cell / 2, ys[-1] + cell / 2]
fig, ax = plt.subplots(figsize=(16, 15))
im = ax.imshow(np.log10(S + 0.01), origin="lower", extent=ext, cmap="magma", vmin=-2, vmax=1, interpolation="bilinear", alpha=0.85)
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.set_label("log10 recognisability of the drone's map")
line = {}
for kind, col in (("straight", "#00e5ff"), ("plan", "#39ff14")):
    runs = [r for r in R["runs"] if r["kind"] == kind]
    for r in runs:
        es = np.array(r["est"]); ax.plot(es[:, 0], es[:, 1], color=col, lw=1.3, ls="--", alpha=0.9, zorder=3)
    tr = np.array(runs[0]["truth"]); ax.plot(tr[:, 0], tr[:, 1], color=col, lw=4, zorder=4)
    sc = 10 ** np.array([r["score_log10"] for r in runs]); lost = np.mean([r["lost"] for r in runs])
    line[kind] = f"median {np.median(sc):.0f} m, lost {lost:.0%}, {len(runs)} seeds"
ax.plot(*R["start"], "o", color="cyan", ms=14, mec="k", zorder=6); ax.plot(*R["goal"], "s", color="magenta", ms=14, mec="k", zorder=6)
ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_xlabel("east (m)"); ax.set_ylabel("north (m)")
ax.set_title(f"{w}, strip {R['strip']}, {R['experiment']}   |   blue = straight strip: {line['straight']}   |   green = planned: {line['plan']}", fontsize=12)
out = f.replace(".json", ".png"); fig.tight_layout(); fig.savefig(out, dpi=90); print(out)
