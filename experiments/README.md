# Experiments

Every navigation method we tried, in the order we tried it. Each folder holds the method (`algo.py`), its benchmark
result (`results.json`, made by `uv run gpsfree eval <name>`) and, for the newer ones, a card (`README.md`) with the
hypothesis, the change and the verdict. Learned parts also keep their training script and parameters.

**How to read the numbers.** Unless stated otherwise, results are on the 12-scenario suite: 20 drone flights of
about 3 km in each of 12 places (Finnish and Ukrainian towns, forest, fells, archipelago, steppe, farmland,
Carpathians, plus Yosemite, Rotterdam and the Namib), with wind, imperfect maps without trees, and three
scenarios that start from a spoofed, wrong position.
- **Score** is the typical error along the flight, as a geometric mean over scenarios. Lower is better.
- **Lost** is the share of flights that were ever more than 50 m off.
- **Silent** is the share of flights that were more than 50 m off while claiming to be within 50 m: believing a
  wrong position.
- **False alarm** is the share of time a method says "I'm lost" while actually within 50 m.

Learned parts train only on flights 20–59 of each scenario and are scored on flights 0–19, so they never see the
test flights.

## Timeline: Saturday 24 October 2026

| time | what | who |
|---|---|---|
| 13:06 | Simulator, Yosemite world, inertial and step-counting baselines | Arsenii |
| 15:48 | Real priced IMU parts (ICM-42688-P, BMI088, ADIS16470, HG4930) and compass variants | Arsenii |
| ~16:05 | `terrain_ekf` first beats the inertial champion on the old one-world suite: 1.1 m vs 55.8 m | Artem |
| 16:58 | Particle filter `ins_echo` on branch `echo-lidar`, later ported as X1 | Arsenii |
| 17:42 | The 12-scenario suite replaces the one-world suite; every result re-run | Artem |
| 18:50 | X1 particle filter | Artem |
| 18:58 | X4 learned lost detector | Artem |
| 19:11 | Closed-loop mission harness, X6 rule baseline, X5 RL trainer | Artem |
| ~20:00 | X5 RL training moved to a Google Cloud VM after two local runs ran out of memory | Artem |
| 20:05 | X2 map offset (rejected) | Artem |
| 20:11 | X3 learned beam model | Artem |
| 20:19 | X7 = X3 + X4 | Artem |

## Results at a glance (12-scenario suite)

| experiment | sensors | score | lost | silent | false alarm |
|---|---|---|---|---|---|
| `imu_deadreckoning` | default IMU | 7.5 km | 100% | no claim | no claim |
| `ins_icm42688p` | $8 IMU | 1.7 km | 100% | no claim | no claim |
| `ins_adis16470` | $408 IMU | 212 m | 100% | no claim | no claim |
| `ins_hg4930` | $9,433 IMU, over the cost cap | 73 m | 99% | no claim | no claim |
| `terrain_ekf` | $8 IMU + lidar | **11.3 m** | 35% | 25% | not measured |
| X1 `terrain_pf` | $408 IMU + lidar | 19.1 m | 61% | 49% | not measured |
| X2 `terrain_pf_offset` | $408 IMU + lidar | 30.3 m | 73% | 62% | 8% |
| X3 `terrain_pf_beams` | $408 IMU + lidar | 13.9 m | 59% | 53% | 4% |
| X4 `terrain_pf_guarded` | $408 IMU + lidar | 19.1 m | 61% | 28% | not measured |
| X7 `terrain_pf_best` | $408 IMU + lidar | 13.9 m | 59% | **24%** | 28% |

The lidar is a Livox Avia pointing down. A version of every row with the corrected Avia price, on equal code, comes
with the final re-run.

## The experiments

### Baselines: Arsenii

- **`imu_deadreckoning`.** Integrates the inertial unit: rotation rates into orientation, acceleration twice into
  position. Altitude comes from the barometer. Nothing outside the drone corrects it, so the error grows without
  bound. Its startup was fixed when the 12-scenario suite arrived, because drones now start mid-flight and tilted.
- **`ins_<part>`.** The same filter on real parts with datasheet noise. A better IMU only delays getting lost: even
  the $9,433 Honeywell ends up more than 50 m off on almost every flight.
- **`ins_compass_<part>`.** Adds the magnetometer for heading. It makes almost no difference, because heading drift
  isn't the main error source here.
- **`pdr_compass`.** Step counting for a walker. The current suite is drones only, so this has no result.

### `terrain_ekf`: matching the ground with a lidar

- **Idea.** A downward lidar measures 49 distances to the ground ten times a second. A Kalman filter predicts each
  distance from the drone's map at its estimated position, and corrects position, orientation and sensor biases from
  the differences. A consistency monitor says "lost" when most beams stop matching the map.
- **Result.** It is the most accurate method, at 11.3 m, and the only one that works on the $8 IMU. It fails when
  the start is spoofed, reaching 10 km off in Kyiv, and over flat steppe and open sea. In those cases it is often
  confidently wrong: 25% silent failures.

### X1 `terrain_pf`: many guesses instead of one

- **Idea.** Arsenii's particle filter keeps 500 weighted guesses of the position instead of one bell curve, so it
  can hold "either this valley or that one" until the terrain decides. Particles start spread over the spoofed-start
  uncertainty.
- **Result.** It fixes the spoofed start in a city: Kyiv 10 km → 41 m. It is worse elsewhere, at 19.1 m overall,
  and a collapsed cloud of guesses looks certain even when it's in the wrong place: 49% silent failures. It needs
  the $408 IMU, because the $8 one drifts too far in tilt.

### X2 `terrain_pf_offset`: track the map's height error

- **Idea.** Estimate one shared local offset between the map and reality, so the beams match the terrain's shape
  rather than its absolute height.
- **Result: rejected.** It helps only in the featureless desert, 7.8 → 2.3 m, and is worse everywhere else at
  30.3 m. The offset soaks up part of the real position error.

### X3 `terrain_pf_beams`: a beam model learned from data

- **Idea.** Learn from 3.4 million training beams how lidar ranges actually disagree with the map. 81% are ordinary
  noise with a spread of 2.4 m. 19% stop about 7 m too early on trees and roofs the map lacks. Score the particles
  with that learned model instead of a hand-set one.
- **Result.** It is the best particle filter, at 13.9 m. The gains are exactly where unmapped clutter is: boreal
  forest 8.7 → 2.9 m, the border town 9.6 → 2.9 m, Kyiv 41 → 10 m. Its trust numbers are unchanged, because it has
  no lost detector.

### X4 `terrain_pf_guarded`: a learned lost detector

- **Idea.** A logistic regression reads the filter's own statistics and predicts whether the drone is more than
  50 m off: how much the guesses agree, how well the best one fits, how informative the terrain is, and time since
  the start. Above a threshold the drone says "I don't know where I am".
- **Result.** On held-out scenarios it separates lost from fine moments well, with AUC 0.86–0.97, except over open
  sea. The time spent confidently wrong drops from 26% to 3%, and silent failures from 49% to 28%, at the same
  accuracy.

### X7 `terrain_pf_best`: learned beams plus the lost detector

- **Idea.** X3 with X4's detector, retrained on X3's own statistics.
- **Result.** The most trustworthy method so far. It scores 13.9 m, the truth lies outside its radius only 4% of
  the time, and it has the fewest silent failures, at 24%. The price is false alarms: it says "lost" 28% of the
  time while actually fine. It is slightly less accurate than `terrain_ekf` where both work.

### X6 `rule_policy` and X5 `rl_policy`: what should the drone do with its belief?

The benchmark flies fixed routes, so these two run in closed-loop missions (`gpsfree/closedloop.py`). The drone
flies 2–3 km to a goal and lands within 50 m of it, steered by its own estimate. It must never cross a no-fly line,
which stands in for a border, and its battery lasts 1.5 times the direct flight. The navigator is X4.

- **X6 rule, a hand-written baseline.** Land when lost or near the border, detour to informative terrain when
  unsure, otherwise continue. On 60 held-out missions:

  | policy | success | border crossed | battery out |
  |---|---|---|---|
  | always continue | 47% | 17% | 20% |
  | rule | 3% | 0% | 0% |

  The rule is safe but gives up almost every time.
- **X5 RL, in progress.** A 40-weight linear policy reads the belief and picks continue, climb, detour, slow down
  or land every 10 s. It is trained by cross-entropy policy search on training missions, on a Google Cloud VM. Its
  results, the training curve and its card land here when training finishes.

## What we learned

- **Any outside reference beats a better IMU.** Matching the ground beats a $9,400 IMU by a factor of 6–20.
- **The map is the bottleneck.** About 2 m of map error breaks terrain matching. Open sea and flat steppe defeat it
  entirely, because every spot looks the same.
- **Many guesses fix spoofed starts in distinctive terrain.** A single guess locks onto the wrong place.
- **Trust can be learned, mostly.** A simple detector cuts the time spent confidently wrong several-fold. Being
  slowly and silently wrong over flat land is still the open problem.
- **Not yet tested: the sky.** A star or sun fix needs no map and can't be spoofed, so it is the missing piece for
  sea, steppe and stale maps.
