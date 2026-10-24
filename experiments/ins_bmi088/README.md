# ins_bmi088: dead reckoning on a real IMU

**Summary.** Dead reckoning on the real $5 Bosch BMI088 IMU with datasheet noise; no outside reference.

**Author:** Arsenii Chistiakov.

**Idea.** `imu_deadreckoning` with the IMU replaced by a real part: Bosch BMI088, $5 consumer IMU (PX4/ArduPilot). Noise and bias come from its datasheet
(`benchmark/hardware/bmi088.json`).

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 4.1 km | 100% |
| Lapland fells | 3.7 km | 100% |
| Boreal forest hills | 3.5 km | 100% |
| Gulf of Finland archipelago | 4.9 km | 100% |
| Mid-size city | 6.6 km | 100% |
| Small border town | 7.1 km | 100% |
| Big dense city | 8.1 km | 100% |
| Steppe fields | 5.4 km | 100% |
| Farmland and villages | 3.0 km | 100% |
| Forested mountains | 4.8 km | 100% |
| Flat port city | 7.1 km | 100% |
| Desert dunes | 3.6 km | 100% |
| **overall** | **4.9 km** | 100% |

**Verdict.** A better IMU slows the drift but never stops it: without an outside reference, every flight eventually
goes more than 50 m off. See `ins_compass_bmi088` for the same IMU plus a magnetometer.
