# ins_icm42688p: dead reckoning on a real IMU

**Summary.** Dead reckoning on the real $8 TDK ICM-42688-P IMU with datasheet noise; no outside reference.

**Author:** Arsenii Chistiakov.

**Idea.** `imu_deadreckoning` with the IMU replaced by a real part: TDK ICM-42688-P, $8 consumer IMU. Noise and bias come from its datasheet
(`benchmark/hardware/icm42688p.json`).

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 1.4 km | 100% |
| Lapland fells | 1.3 km | 100% |
| Boreal forest hills | 1.2 km | 100% |
| Gulf of Finland archipelago | 2.0 km | 100% |
| Mid-size city | 2.2 km | 100% |
| Small border town | 2.4 km | 100% |
| Big dense city | 3.0 km | 100% |
| Steppe fields | 2.0 km | 100% |
| Farmland and villages | 1.0 km | 100% |
| Forested mountains | 1.6 km | 100% |
| Flat port city | 2.3 km | 100% |
| Desert dunes | 1.2 km | 100% |
| **overall** | **1.7 km** | 100% |

**Verdict.** A better IMU slows the drift but never stops it: without an outside reference, every flight eventually
goes more than 50 m off. See `ins_compass_icm42688p` for the same IMU plus a magnetometer.
