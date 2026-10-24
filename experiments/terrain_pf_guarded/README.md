# X4 terrain_pf_guarded: a learned lost detector

**Summary.** terrain_pf plus a logistic-regression lost detector trained on the filter's own statistics; says 'I don't know' instead of lying.

**Hypothesis.** Lost and healthy moments look different in the filter's own statistics, so a simple trained model
can tell the drone it is lost before it acts on a wrong position.

**Change vs X1.** Same particle filter and accuracy; `uncertainty()` adds P(lost) from a logistic regression on the
filter's statistics. Above the trained threshold (0.2497) the drone reports "I don't know where I am";
below it the radius widens with P(lost).

**Training** (`train.py`, runs 20-39 of every scenario, never the scored runs 0-19): 150,295 samples, label =
true horizontal error over 50 m (31% of samples). Train AUC 0.941; leave-one-scenario-out
AUC: alpine 0.936, fells 0.662, boreal 0.903, archipelago 0.395, tampere 0.962, bordertown 0.924, kyiv 0.918, steppe 0.73, farmland 0.809, carpathians 0.87, rotterdam 0.971, desert 0.949. Threshold catches 95% of lost samples, false alarms 33% in training.

**What it learned** (standardised weights; positive = more likely lost):

| feature | weight |
|---|---|
| ess | +0.03 |
| log_spread | +1.24 |
| outliers | +0.52 |
| med_res | +0.75 |
| info | -0.87 |
| noreturn | -0.12 |
| log_fit | +1.14 |
| t_min | +0.60 |
| start_sigma | +0.86 |

A wide or poorly fitting particle cloud, a long time since the start and a big start uncertainty raise P(lost);
informative terrain lowers it. Open sea (archipelago, AUC 0.395) is where it fails:
nothing in the filter's statistics distinguishes "lost" from "fine" over flat water.

**Result** (misleading time and silent failures, X1 → X4; accuracy is unchanged):

| scenario | misleading | silent |
|---|---|---|
| alpine | 3% → 1% | 30% → 10% |
| fells | 2% → 0% | 10% → 5% |
| boreal | 9% → 2% | 25% → 15% |
| archipelago | 47% → 0% | 30% → 0% |
| tampere | 16% → 2% | 50% → 35% |
| bordertown | 22% → 2% | 55% → 40% |
| kyiv | 36% → 0% | 75% → 20% |
| steppe | 71% → 0% | 90% → 5% |
| farmland | 43% → 12% | 80% → 70% |
| carpathians | 28% → 10% | 55% → 55% |
| rotterdam | 16% → 2% | 40% → 40% |
| desert | 19% → 10% | 45% → 35% |
| **overall** | 26% → 3% | 49% → 28% |

**Verdict: kept.** The detector removes most of the "confidently wrong" time. Silent failures are still too common
in farmland, the Carpathians and cities, where the filter drifts slowly enough to look healthy.
