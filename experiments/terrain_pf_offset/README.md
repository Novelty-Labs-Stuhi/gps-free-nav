# X2 terrain_pf_offset: track the map's local height error

**Hypothesis.** Free elevation maps are off by metres but smoothly, so estimating one shared local height offset
lets the beams match the terrain's shape and ignore its absolute height.

**Change vs X1.** `MAP_OFFSET = True`: each frame the offset moves 20% of the way to the particle-weighted median
vertical residual, and residuals are taken relative to it.

**Result** (score m, silent failures X1 → X2):

| scenario | X1 terrain_pf | X2 offset | silent |
|---|---|---|---|
| alpine | 4.5 | 9.2 | 30% → 50% |
| fells | 4.4 | 19.6 | 10% → 65% |
| boreal | 8.7 | 23.1 | 25% → 70% |
| archipelago | 603.2 | 391.3 | 30% → 20% |
| tampere | 10.2 | 10.5 | 50% → 50% |
| bordertown | 9.6 | 12.8 | 55% → 70% |
| kyiv | 41.3 | 77.1 | 75% → 75% |
| steppe | 408.8 | 370.7 | 90% → 100% |
| farmland | 38.6 | 138.4 | 80% → 100% |
| carpathians | 14.8 | 70.1 | 55% → 100% |
| rotterdam | 3.0 | 4.3 | 40% → 40% |
| desert | 7.8 | 2.3 | 45% → 0% |
| **overall** | **19.1** | **30.3** | 49% → 62% |

**Verdict: rejected.** The offset only helps where the terrain is smooth and featureless (desert 7.8 → 2.3 m). Elsewhere
it absorbs part of the real position error: when the particles sit in the wrong place, the median residual is
exactly the signal that should push them back, and the offset soaks it up instead. A per-particle offset, or one
estimated only from beams on flat ground, would be the next thing to try. Note: X2 ran after particles were kept
inside the map bounds; the final re-run compares both on equal code.
