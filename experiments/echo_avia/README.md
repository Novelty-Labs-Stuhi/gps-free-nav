# echo_avia

**Summary.** Lidar alone: the Avia's built-in IMU only gives attitude; scans alone have to find the position.

**Author:** Arsenii Chistiakov.

**Idea.** Livox Avia alone: its built-in BMI088 gives attitude, but acceleration is never integrated into position. Particles move at constant velocity between scans, and the scans alone have to find where the drone is.

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 23.8 m | 85% |
| Lapland fells | 11.5 m | 80% |
| Boreal forest hills | 9.9 m | 65% |
| Gulf of Finland archipelago | 941.9 m | 100% |
| Mid-size city | 17.8 m | 85% |
| Small border town | 44.6 m | 100% |
| Big dense city | 33.7 m | 75% |
| Steppe fields | 620.1 m | 100% |
| Farmland and villages | 218.5 m | 100% |
| Forested mountains | 24.4 m | 80% |
| Flat port city | 21.9 m | 80% |
| Desert dunes | 9.5 m | 70% |
| **overall** | **43.6 m** | 85% |
