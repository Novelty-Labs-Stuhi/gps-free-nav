# ins_hg4930: dead reckoning on a real IMU

**Summary.** Dead reckoning on the real $9,433 Honeywell HG4930 IMU with datasheet noise; no outside reference.

**Author:** Arsenii Chistiakov.

**Idea.** `imu_deadreckoning` with the IMU replaced by a real part: Honeywell HG4930, $9,433 tactical IMU (over the $3,000 cap). Noise and bias come from its datasheet
(`benchmark/hardware/hg4930.json`).

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 54.1 m | 100% |
| Lapland fells | 43.1 m | 100% |
| Boreal forest hills | 37.6 m | 100% |
| Gulf of Finland archipelago | 232.0 m | 100% |
| Mid-size city | 85.4 m | 100% |
| Small border town | 68.9 m | 95% |
| Big dense city | 154.7 m | 100% |
| Steppe fields | 172.2 m | 100% |
| Farmland and villages | 48.3 m | 95% |
| Forested mountains | 58.3 m | 100% |
| Flat port city | 66.5 m | 100% |
| Desert dunes | 39.3 m | 100% |
| **overall** | **73.1 m** | 99% |

**Verdict.** A better IMU slows the drift but never stops it: without an outside reference, every flight eventually
goes more than 50 m off. See `ins_compass_hg4930` for the same IMU plus a magnetometer.
