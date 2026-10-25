"""All 50 recognisability maps: share of cells where the Avia frame stands out from its 100-500 m neighbours,
plus a montage of the maps themselves."""
import glob, os
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
files = sorted(glob.glob("data/flat/recog/*_recog.npz"))
stats = []
for f in files:
    d = np.load(f); s = d["score"]
    stats.append((os.path.basename(f).replace("_recog.npz", ""), float((s >= 1).mean()), float((s >= 0.3).mean()), float(np.median(s)), s))
stats.sort(key=lambda t: t[1])
fig, ax = plt.subplots(figsize=(16, 6))
x = np.arange(len(stats))
ax.bar(x - 0.2, [100 * t[2] for t in stats], 0.4, color="#9ecae1", label="cells with recognisability >= 0.3 sigma")
ax.bar(x + 0.2, [100 * t[1] for t in stats], 0.4, color="#2171b5", label="cells with recognisability >= 1 sigma (usable fix)")
ax.set_xticks(x); ax.set_xticklabels([t[0] for t in stats], rotation=75, ha="right", fontsize=8)
ax.set_ylabel("% of the 15 x 15 km map"); ax.legend(); ax.grid(axis="y", alpha=0.3)
ax.set_title("How much of each flat world the Avia echo can recognise (drone's map: 2 m terrain error, buildings, no trees)")
fig.tight_layout(); fig.savefig("data/flat/recog_share.png", dpi=90)
n = len(stats); cols = 10; rows_ = int(np.ceil(n / cols))
fig, axes = plt.subplots(rows_, cols, figsize=(cols * 2.4, rows_ * 2.6))
for a, t in zip(axes.ravel(), stats):
    a.imshow(np.log10(t[4] + 0.01), origin="lower", cmap="magma", vmin=-2, vmax=1); a.set_title(f"{t[0]}\n{100*t[1]:.0f}% >= 1 sigma", fontsize=8); a.set_xticks([]); a.set_yticks([])
for a in axes.ravel()[n:]: a.axis("off")
fig.suptitle("Recognisability maps, 50 m cells, sorted least to most recognisable (bright = Avia frame unique within 500 m)")
fig.tight_layout(); fig.savefig("data/flat/recog_maps.png", dpi=80)
print(f"{'world':22s} >=1sig  >=0.3sig  median")
for t in stats: print(f"{t[0]:22s} {100*t[1]:5.1f}%  {100*t[2]:6.1f}%  {t[3]:.3f}")
