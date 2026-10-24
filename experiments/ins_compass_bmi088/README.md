# ins_compass_bmi088: dead reckoning plus a compass

**Summary.** Dead reckoning on the $5 Bosch BMI088 plus a magnetometer for heading.

**Author:** Arsenii Chistiakov.

**Idea.** `ins_bmi088` plus a magnetometer (PNI RM3100, $17): a complementary filter pulls the heading towards the
compass, zeroed against the known start heading. Tilt still comes from the gyro alone. IMU: Bosch BMI088, $5 consumer IMU (PX4/ArduPilot).

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 4.2 km | 100% |
| Lapland fells | 3.8 km | 100% |
| Boreal forest hills | 3.5 km | 100% |
| Gulf of Finland archipelago | 4.9 km | 100% |
| Mid-size city | 6.6 km | 100% |
| Small border town | 7.2 km | 100% |
| Big dense city | 8.2 km | 100% |
| Steppe fields | 5.2 km | 100% |
| Farmland and villages | 3.0 km | 100% |
| Forested mountains | 4.7 km | 100% |
| Flat port city | 6.9 km | 100% |
| Desert dunes | 3.6 km | 100% |
| **overall** | **4.9 km** | 100% |

**Verdict.** Practically the same as `ins_bmi088`: heading drift is not the main error source; integrated
acceleration and tilt errors are.
