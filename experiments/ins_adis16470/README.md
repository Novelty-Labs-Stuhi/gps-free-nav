# ins_adis16470: dead reckoning on a real IMU

**Author:** Arsenii Chistiakov.

**Idea.** `imu_deadreckoning` with the IMU replaced by a real part: Analog Devices ADIS16470, $408 industrial IMU. Noise and bias come from its datasheet
(`benchmark/hardware/adis16470.json`).

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 178.0 m | 100% |
| Lapland fells | 120.8 m | 100% |
| Boreal forest hills | 139.2 m | 100% |
| Gulf of Finland archipelago | 354.4 m | 100% |
| Mid-size city | 230.7 m | 100% |
| Small border town | 199.8 m | 100% |
| Big dense city | 448.2 m | 100% |
| Steppe fields | 301.3 m | 100% |
| Farmland and villages | 167.5 m | 100% |
| Forested mountains | 194.1 m | 100% |
| Flat port city | 278.0 m | 100% |
| Desert dunes | 135.2 m | 100% |
| **overall** | **211.6 m** | 100% |

**Verdict.** A better IMU slows the drift but never stops it: without an outside reference, every flight eventually
goes more than 50 m off. See `ins_compass_adis16470` for the same IMU plus a magnetometer.
