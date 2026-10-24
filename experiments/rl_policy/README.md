# X5 rl_policy: learning what to do with the belief (in progress)

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

**Result.** Pending: training is running. The policy, training log, evaluation table and verdict are added here when
it finishes.
