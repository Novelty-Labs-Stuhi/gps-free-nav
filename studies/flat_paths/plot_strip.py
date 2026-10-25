"""One strip of one world on the full recognisability heat map: straight strip and planned path as flown (solid),
the navigator's estimate for each (dashed). Usage: plot_strip.py DIR WORLD RUN"""
import json, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
D, w, run = sys.argv[1], sys.argv[2], int(sys.argv[3])
d = np.load(f"{D}/recog/{w}_recog.npz"); xs, ys, S = d["xs"], d["ys"], d["score"]
r = next(r for r in json.load(open(f"{D}/{w}.json")) if r.get("run") == run and "straight" in r)
nav = json.load(open(f"{D}/{w}.json")) and (D.split("/")[-1])
cell = float(xs[1] - xs[0]); ext = [xs[0] - cell / 2, xs[-1] + cell / 2, ys[0] - cell / 2, ys[-1] + cell / 2]
fmt = lambda m: f"{10**m['score_log10']:.0f} m, " + (f"lost at {m['lost_at_m']/1000:.1f} km" if m["lost"] else "never lost") + f", {m['len']/1000:.1f} km"
fig, ax = plt.subplots(figsize=(16, 15))
im = ax.imshow(np.log10(S + 0.01), origin="lower", extent=ext, cmap="magma", vmin=-2, vmax=1, interpolation="bilinear", alpha=0.9)
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02); cb.set_label("log10 recognisability of the drone's map (0 = lidar frame unique within 500 m)")
for kind, col, lab in (("straight", "#00e5ff", "straight strip"), ("plan", "#39ff14", "planned over recognisability")):
    tr = np.array(r["path"][kind]["truth"]); es = np.array(r["path"][kind]["est"])
    ax.plot(tr[:, 0], tr[:, 1], color=col, lw=3.5, zorder=4, label=f"{lab}: flown, {fmt(r[kind])}")
    ax.plot(es[:, 0], es[:, 1], color=col, lw=1.5, ls="--", zorder=3, label=f"{lab}: navigator's estimate")
ax.plot(*r["start"], "o", color="cyan", ms=14, mec="k", zorder=6, label="start"); ax.plot(*r["goal"], "s", color="magenta", ms=14, mec="k", zorder=6, label="goal")
ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_xlabel("east (m)"); ax.set_ylabel("north (m)")
gain = 10 ** (r["straight"]["score_log10"] - r["plan"]["score_log10"])
ax.set_title(f"{w}, strip {run}, navigator {'terrain_ekf' if 'ekf' in D else 'ins_echo_avia_adis16470'}: planned {gain:.0f}x better", fontsize=14)
ax.legend(loc="lower left", fontsize=11, framealpha=0.85)
out = f"{D}/wins/{w}_strip{run}.png"; fig.tight_layout(); fig.savefig(out, dpi=90); print(out)
