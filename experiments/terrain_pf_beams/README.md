# X3 terrain_pf_beams: a beam model learned from data

**Hypothesis.** Trees and roofs the map lacks make beams stop early in a predictable way. A likelihood learned from
data beats the hand-set Gaussian clipped at 3 sigma.

**Training** (`train.py`, runs 20-29 of every scenario, never the scored runs): at the TRUE pose, each beam endpoint's
height minus the map height under it, 3,357,937 beams. EM fit of a Normal plus a one-sided exponential tail:

| | value |
|---|---|
| normal part: mean, sigma | -0.208 m, 2.414 m |
| share of beams stopped early (trees, roofs) | 19% |
| how far above the map they stop, on average | 7.0 m |

**Change vs X1.** `_loglik` scores residuals with this mixture: a short beam costs little, a long one is strong evidence.

**Result** (score m; runs lost X1 → X3):

| scenario | X1 terrain_pf | X3 learned beams | runs lost |
|---|---|---|---|
| alpine | 4.5 | 6.0 | 50% → 60% |
| fells | 4.4 | 4.5 | 10% → 5% |
| boreal | 8.7 | 2.9 | 25% → 5% |
| archipelago | 603.2 | 735.4 | 100% → 100% |
| tampere | 10.2 | 11.4 | 75% → 80% |
| bordertown | 9.6 | 2.9 | 65% → 50% |
| kyiv | 41.3 | 10.3 | 80% → 75% |
| steppe | 408.8 | 218.8 | 95% → 100% |
| farmland | 38.6 | 25.3 | 85% → 95% |
| carpathians | 14.8 | 9.5 | 55% → 40% |
| rotterdam | 3.0 | 6.2 | 45% → 55% |
| desert | 7.8 | 8.2 | 45% → 45% |
| **overall** | **19.1** | **13.9** | 61% → 59% |

**Verdict: kept, best particle filter so far.** The gains are where unmapped clutter is: boreal forest, the border
town, Kyiv and the Carpathians. Integrity is unchanged (silent failures 53%) because it has no lost
detector; combining it with X4's detector is the next candidate. Open sea and flat steppe still fail: no terrain shape.
