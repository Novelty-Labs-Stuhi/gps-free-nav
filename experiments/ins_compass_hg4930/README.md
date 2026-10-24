# ins_compass_hg4930: dead reckoning plus a compass

**Summary.** Dead reckoning on the $9,433 Honeywell HG4930 plus a magnetometer for heading.

**Author:** Arsenii Chistiakov.

**Idea.** `ins_hg4930` plus a magnetometer (PNI RM3100, $17): a complementary filter pulls the heading towards the
compass, zeroed against the known start heading. Tilt still comes from the gyro alone. IMU: Honeywell HG4930, $9,433 tactical IMU (over the $3,000 cap).

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 57.0 m | 100% |
| Lapland fells | 45.4 m | 100% |
| Boreal forest hills | 42.7 m | 95% |
| Gulf of Finland archipelago | 229.9 m | 100% |
| Mid-size city | 84.3 m | 100% |
| Small border town | 77.4 m | 90% |
| Big dense city | 147.4 m | 100% |
| Steppe fields | 177.0 m | 100% |
| Farmland and villages | 52.7 m | 95% |
| Forested mountains | 66.8 m | 100% |
| Flat port city | 66.3 m | 100% |
| Desert dunes | 39.1 m | 100% |
| **overall** | **76.4 m** | 98% |

**Verdict.** Practically the same as `ins_hg4930`: heading drift is not the main error source; integrated
acceleration and tilt errors are.
