# X6 rule_policy: a hand-written decision baseline (closed loop)

**Hypothesis.** Even a simple rule on the belief beats flying blind.

**Rule** (`gpsfree/closedloop.py:rule_policy`): land when P(lost) > 0.8 or the estimated margin to the no-fly
line minus the uncertainty radius is negative; detour toward informative terrain while the radius is over 50 m;
otherwise continue to the goal.

**Setup.** Closed-loop missions (`gpsfree/closedloop.py`): fly 2-3 km to a goal and land within 50 m, never cross a
no-fly line 150-400 m beside the direct path, battery 1.5x the direct flight time. The autopilot steers by the
navigator's estimate (`terrain_pf_guarded`), so its errors really push the drone. Evaluation: 5 held-out missions
(seeds 1000-1004) on each of the 12 suite scenarios, `uv run python experiments/rl_policy/missions.py continue rule`.

**Result** (60 missions):

| policy | success | no-fly crossed | battery out | silent wrong landing | median landing error |
|---|---|---|---|---|---|
| always continue | 47% | 17% | 20% | 3% | 72 m |
| rule | 3% | 0% | 0% | 0% | 2,153 m |

**Verdict.** The rule never crosses the border but gives up almost every mission: the radius is often over 50 m
early on, and P(lost) or the margin check makes it land immediately. Safe but useless, which is the gap X5 (RL)
has to close.
