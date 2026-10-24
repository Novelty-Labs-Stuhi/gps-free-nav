# ins_echo_grf500_icm42688p

**Summary.** ins_echo on the cheapest hardware ($8 IMU + single beam), with tilt pulled to gravity and looser velocity.

**Author:** Arsenii Chistiakov.

**Idea.** `ins_echo` on the cheapest real hardware: ICM-42688-P IMU + GRF-500 single beam. The consumer gyro's tilt drift corrupts the INS acceleration, so tilt is pulled towards gravity and particle velocities may wander more.

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 36.2 m | 95% |
| Lapland fells | 59.0 m | 100% |
| Boreal forest hills | 73.9 m | 100% |
| Gulf of Finland archipelago | 755.1 m | 100% |
| Mid-size city | 500.0 m | 100% |
| Small border town | 328.1 m | 100% |
| Big dense city | 447.2 m | 100% |
| Steppe fields | 687.1 m | 100% |
| Farmland and villages | 327.3 m | 100% |
| Forested mountains | 65.1 m | 100% |
| Flat port city | 406.4 m | 100% |
| Desert dunes | 94.0 m | 100% |
| **overall** | **202.9 m** | 100% |
