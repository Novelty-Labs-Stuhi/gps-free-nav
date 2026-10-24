# ins_compass: dead reckoning plus a compass (suite default sensors)

**Summary.** Dead reckoning plus a magnetometer pulling the heading via a complementary filter, on the suite's default IMU.

**Author:** Arsenii Chistiakov.

**Idea.** `imu_deadreckoning` plus a magnetometer heading through a complementary filter, on the suite's default, unpriced IMU.
The `ins_compass_<part>` variants run the same code on real parts.

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 6.6 km | 100% |
| Lapland fells | 6.4 km | 100% |
| Boreal forest hills | 4.8 km | 100% |
| Gulf of Finland archipelago | 7.3 km | 100% |
| Mid-size city | 9.5 km | 100% |
| Small border town | 10.6 km | 100% |
| Big dense city | 11.3 km | 100% |
| Steppe fields | 6.8 km | 100% |
| Farmland and villages | 5.5 km | 100% |
| Forested mountains | 6.3 km | 100% |
| Flat port city | 10.3 km | 100% |
| Desert dunes | 5.6 km | 100% |
| **overall** | **7.3 km** | 100% |

**Verdict.** The compass doesn't save a poor IMU.
