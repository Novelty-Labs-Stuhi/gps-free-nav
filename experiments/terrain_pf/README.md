# X1 terrain_pf: many guesses instead of one

**Author:** Arsenii Chistiakov (particle filter, `ins_echo` on branch `echo-lidar`), ported to the 12-scenario suite.

**Hypothesis.** Keeping hundreds of position guesses, with tempered sensor updates, avoids locking onto the wrong
terrain after a spoofed start.

**Change vs `terrain_ekf`.** A particle filter over x, y, velocity and a heading offset, scored by how well each
lidar frame lies on a height grid of the drone's map. Particles start spread over the told start uncertainty.
Hardware: ADIS16470 IMU + Livox Avia; the $8 IMU drifts too far in tilt without the Kalman filter's lidar-corrected
attitude, and pulling tilt towards gravity made things worse (manoeuvres and drag). 500 particles to fit the CI
budget (1000 scored Kyiv 7.6 m instead of 41 m, but takes ~9 min on 4 cores).

**Uncertainty.** 3 m + k x particle spread, k = 3.76 calibrated on training runs 20-25 (`calibrate.py`) while the
drone is within 50 m; "lost" when no particle fits the terrain for 2 s.

**Result** (score m; runs lost and silent failures, Kalman filter → particle filter):

| scenario | terrain_ekf | terrain_pf | runs lost | silent |
|---|---|---|---|---|
| alpine | 2.3 | 4.5 | 25% → 50% | 20% → 30% |
| fells | 1.7 | 4.4 | 0% → 10% | 0% → 10% |
| boreal | 1.1 | 8.7 | 0% → 25% | 0% → 25% |
| archipelago | 299.9 | 603.2 | 100% → 100% | 100% → 30% |
| tampere | 2.4 | 10.2 | 30% → 75% | 20% → 50% |
| bordertown | 1.3 | 9.6 | 25% → 65% | 20% → 55% |
| kyiv | 10,162.5 | 41.3 | 100% → 80% | 35% → 75% |
| steppe | 2,387.8 | 408.8 | 100% → 95% | 80% → 90% |
| farmland | 4.1 | 38.6 | 20% → 85% | 20% → 80% |
| carpathians | 3.7 | 14.8 | 10% → 55% | 10% → 55% |
| rotterdam | 1.0 | 3.0 | 5% → 45% | 0% → 40% |
| desert | 2.7 | 7.8 | 0% → 45% | 0% → 45% |
| **overall** | **11.3** | **19.1** | 35% → 61% | 25% → 49% |

**Verdict.** Many guesses fix the spoofed start in a city (Kyiv 10 km → 41 m) but are less accurate elsewhere and
more often confidently wrong: a collapsed particle cloud in the wrong place looks certain. The spread alone is not
an integrity signal, which motivates X4 (learned lost detector).
