# terrain_ekf: matching the ground with a lidar (Kalman filter)

**Summary.** Kalman filter on an $8 IMU corrected 10x/s by 49 lidar ranges matched against the drone's 3D map, with a beam-disagreement monitor that says 'lost'.

**Author:** Artem.

**Idea.** An error-state Kalman filter tracks 16 numbers: position, velocity, orientation error, accelerometer and
gyro biases, and barometer drift. The inertial unit predicts the motion 100 times a second. Ten times a second, a
downward Livox Avia lidar measures 49 distances to the ground. For each beam the filter casts the same ray into the
drone's map from its estimated pose, and the differences correct position, orientation and biases in one update.
Beams that graze edges, hit nothing, or disagree too much (unmapped trees, roofs) are dropped.

**Integrity.** A 95% radius from the filter's covariance, widened 3x with a 3 m floor, because the covariance doesn't
know about map errors. A running share of disagreeing beams widens it further, and above 60% the filter reports
"I don't know where I am".

**Sensors:** TDK ICM-42688-P ($8) + Livox Avia lidar + barometer.

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 2.3 m | 25% |
| Lapland fells | 1.7 m | 0% |
| Boreal forest hills | 1.1 m | 0% |
| Gulf of Finland archipelago | 299.9 m | 100% |
| Mid-size city | 2.4 m | 30% |
| Small border town | 1.3 m | 25% |
| Big dense city | 10.2 km | 100% |
| Steppe fields | 2.4 km | 100% |
| Farmland and villages | 4.1 m | 20% |
| Forested mountains | 3.7 m | 10% |
| Flat port city | 1.0 m | 5% |
| Desert dunes | 2.7 m | 0% |
| **overall** | **11.3 m** | 35% |

Integrity, overall: the truth lies outside the reported radius 17% of the time, and 25% of flights are silent
failures (more than 50 m off while claiming to be within 50 m).

**History.** On the old one-world suite with a perfect map it scored 1.1 m against the inertial champion's 55.8 m.
Stress tests then showed how fast it degrades with realistic maps: 2 m of map error, unmapped forest, flat steppe, a
wrong start. Those findings shaped the 12-scenario suite.

**Verdict.** The most accurate method, and the only one that works on the $8 IMU. Its weakness is believing a wrong
position: after a spoofed start it locks onto the wrong terrain (Kyiv 10 km), and over open sea and flat steppe it
has nothing to match.
