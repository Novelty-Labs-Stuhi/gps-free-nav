# ins_echo_avia_adis16470

**Summary.** ins_echo on a $408 ADIS16470 IMU plus the Livox Avia scanning lidar looking down.

**Author:** Arsenii Chistiakov.

**Idea.** `ins_echo` on real hardware: ADIS16470 IMU + Livox Avia lidar looking down.

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 4.3 m | 50% |
| Lapland fells | 4.6 m | 10% |
| Boreal forest hills | 7.9 m | 15% |
| Gulf of Finland archipelago | 530.3 m | 100% |
| Mid-size city | 10.2 m | 85% |
| Small border town | 6.2 m | 70% |
| Big dense city | 5.5 m | 60% |
| Steppe fields | 397.2 m | 100% |
| Farmland and villages | 40.3 m | 85% |
| Forested mountains | 14.4 m | 60% |
| Flat port city | 2.9 m | 40% |
| Desert dunes | 7.5 m | 40% |
| **overall** | **15.2 m** | 60% |
