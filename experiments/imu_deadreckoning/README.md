# imu_deadreckoning: inertial dead reckoning (baseline)

**Summary.** Integrates the IMU alone (rotation into attitude, acceleration twice into position), baro for height; we fixed its start attitude for drones that start tilted.

**Author:** Arsenii Chistiakov.

**Idea.** Integrate the inertial unit and nothing else: rotation rates into orientation, acceleration (minus gravity)
twice into velocity and position. Altitude comes from the barometer. Every small sensor error is integrated twice, so
the error grows without bound. Everything else should beat this.

**Sensors:** the suite's default, unpriced IMU + barometer.

**Change on 24 Oct (Artem):** the start attitude used to assume a level drone. In the 12-scenario suite drones start
mid-flight and tilted by drag, so `level_attitude` now takes roll and pitch from gravity in the first accelerometer
sample. All `ins_*` variants inherit this.

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 6.4 km | 100% |
| Lapland fells | 6.7 km | 100% |
| Boreal forest hills | 5.2 km | 100% |
| Gulf of Finland archipelago | 7.5 km | 100% |
| Mid-size city | 9.5 km | 100% |
| Small border town | 10.5 km | 100% |
| Big dense city | 11.2 km | 100% |
| Steppe fields | 7.2 km | 100% |
| Farmland and villages | 5.4 km | 100% |
| Forested mountains | 6.6 km | 100% |
| Flat port city | 11.3 km | 100% |
| Desert dunes | 6.1 km | 100% |
| **overall** | **7.5 km** | 100% |

**Verdict.** The floor every method must beat: kilometres off within a five-minute flight.
