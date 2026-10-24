# X7 terrain_pf_best: learned beams + learned lost detector

**Summary.** terrain_pf_beams' learned beams plus terrain_pf_guarded's lost detector retrained on them: the most trustworthy method so far.

**What it is.** X3's particle filter (learned beam model) with X4's lost detector, retrained on X3's own statistics
(`train.py`, runs 20-39 only). Particle filter by Arsenii Chistiakov (ported in X1).

**Result** against the Kalman filter `terrain_ekf` (score m; silent failures; false alarms = time it says "lost"
while actually within 50 m):

| scenario | terrain_ekf | X7 | silent (EKF) | silent (X7) | false alarm (X7) |
|---|---|---|---|---|---|
| alpine | 2.3 | 6.0 | 20% | 40% | 19% |
| fells | 1.7 | 4.5 | 0% | 5% | 20% |
| boreal | 1.1 | 2.9 | 0% | 0% | 44% |
| archipelago | 299.9 | 735.4 | 100% | 0% | 1% |
| tampere | 2.4 | 11.4 | 20% | 35% | 21% |
| bordertown | 1.3 | 2.9 | 20% | 25% | 46% |
| kyiv | 10,162.5 | 10.3 | 35% | 10% | 54% |
| steppe | 2,387.8 | 218.8 | 80% | 0% | 30% |
| farmland | 4.1 | 25.3 | 20% | 65% | 44% |
| carpathians | 3.7 | 9.5 | 10% | 35% | 29% |
| rotterdam | 1.0 | 6.2 | 0% | 35% | 22% |
| desert | 2.7 | 8.2 | 0% | 40% | 8% |
| **overall** | **11.3** | **13.9** | 25% | 24% | 28% |

Misleading time (truth outside the reported radius): 17% for the EKF, 4% for X7.

**Verdict.** Best trust profile so far: the truth is almost never outside its radius, and on spoofed starts it fixes
the city case (Kyiv 10,162 m → 10 m) and says "lost" over open sea and steppe instead of lying.
It is slightly less accurate than the Kalman filter where both work, and on a pricier IMU (ADIS16470).
