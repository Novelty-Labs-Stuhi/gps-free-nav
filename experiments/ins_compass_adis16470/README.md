# ins_compass_adis16470: dead reckoning plus a compass

**Author:** Arsenii Chistiakov.

**Idea.** `ins_adis16470` plus a magnetometer (PNI RM3100, $17): a complementary filter pulls the heading towards the
compass, zeroed against the known start heading. Tilt still comes from the gyro alone. IMU: Analog Devices ADIS16470, $408 industrial IMU.

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 176.6 m | 100% |
| Lapland fells | 127.9 m | 100% |
| Boreal forest hills | 138.7 m | 100% |
| Gulf of Finland archipelago | 356.4 m | 100% |
| Mid-size city | 228.0 m | 100% |
| Small border town | 205.1 m | 100% |
| Big dense city | 448.8 m | 100% |
| Steppe fields | 276.7 m | 100% |
| Farmland and villages | 168.1 m | 100% |
| Forested mountains | 192.8 m | 100% |
| Flat port city | 285.4 m | 100% |
| Desert dunes | 138.8 m | 100% |
| **overall** | **212.2 m** | 100% |

**Verdict.** Practically the same as `ins_adis16470`: heading drift is not the main error source; integrated
acceleration and tilt errors are.
