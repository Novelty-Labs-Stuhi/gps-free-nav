# ins_compass_icm42688p: dead reckoning plus a compass

**Author:** Arsenii Chistiakov.

**Idea.** `ins_icm42688p` plus a magnetometer (PNI RM3100, $17): a complementary filter pulls the heading towards the
compass, zeroed against the known start heading. Tilt still comes from the gyro alone. IMU: TDK ICM-42688-P, $8 consumer IMU.

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

**Verdict.** Practically the same as `ins_icm42688p`: heading drift is not the main error source; integrated
acceleration and tilt errors are.
