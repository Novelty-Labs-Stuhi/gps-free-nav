# X5 rl_policy: learning what to do with the belief

**Summary.** Linear policy trained by cross-entropy search to choose continue/climb/detour/slow/land from the belief.

**Hypothesis.** A policy that reads how sure the navigator is can fly a mission more safely than one that always
continues. It can detour to informative terrain, slow down, climb or land early.

**Setup.** Closed-loop missions (`gpsfree/closedloop.py`): fly 2-3 km to a goal and land within 50 m, steered by the
navigator's own estimate (X4 `terrain_pf_guarded`). Never cross a no-fly line 150-400 m beside the path, which
stands in for a border. The battery lasts 1.5 times the direct flight.

**Policy.** Linear: 8 belief features (uncertainty radius, P(lost), distance to goal, margin to the border, terrain
informativeness, battery, height, a constant) times 5 actions (continue, climb, detour, slow, land), so 40 weights.
At each 10 s decision the highest-scoring action wins.

**Training** (`train.py`). Cross-entropy policy search: each round flies 32 candidate weight sets on the same 8
training missions (seeds 0-999), keeps the best quarter and moves towards them. 25 rounds on a Google Cloud VM
(g2-standard-48). Started from "always continue". Two earlier local runs were stopped after running the laptop out
of memory.

**Evaluation** (`missions.py`). 60 held-out missions (seeds 1000-1004 on every scenario), comparing always continue,
the X6 rule and this policy.

**Result** (60 held-out missions, seeds 1000-1004 on all 12 scenarios; `eval.json`):

| policy | success | border crossed | battery out | silent wrong landing | median landing error |
|---|---|---|---|---|---|
| always continue | 47% | 17% | 20% | 3.3% | 72 m |
| hand-written rule (X6) | 3% | 0% | 0% | 0.0% | 2,153 m |
| **learned policy (X5)** | 67% | 10% | 12% | 1.7% | 21 m |

Actions chosen by the learned policy: 1153 continue, 441 climb, 47 land, never detour or slow.

**Training curve** (`train_log.json`): the current policy's reward on each round's 8 training missions climbed from
-27 (round 0, close to always-continue) to between +25 and +75 in later rounds, noisy because each round draws new
missions. Training ran all 25 rounds on the VM; the held-out evaluation ran afterwards on the laptop.

**What it learned** (weights; for each decision the action with the highest sum of input x weight wins):

| input | continue | climb | detour | slow | land |
|---|---|---|---|---|---|
| radius | +0.13 | -0.06 | -0.18 | -0.05 | -0.18 |
| P(lost) | -0.01 | -0.03 | +0.14 | +0.22 | +0.05 |
| distance to goal | -0.24 | +0.31 | -0.18 | -0.02 | -0.25 |
| border margin | -0.41 | +0.04 | -0.10 | +0.23 | -0.02 |
| terrain info | -0.23 | +0.01 | -0.11 | -0.09 | -0.02 |
| battery | -0.17 | -0.15 | -0.34 | -0.46 | +0.26 |
| height | +0.42 | +0.23 | -0.03 | -0.16 | -0.41 |
| constant | +0.89 | -0.70 | -0.95 | -0.82 | -0.79 |

**Verdict: kept.** The learned policy succeeds more often than flying blind (67% vs 47%), crosses the border less
(10% vs 17%), runs out of battery less and lands closer (median 21 m vs 72 m). It discovered that climbing helps:
a higher drone sees more terrain with its lidar, which keeps the navigator localised. It still crosses the border in
10% of missions, so a hard safety rule on top (land when the border margin minus the radius goes negative) would be
the next step before trusting it.
