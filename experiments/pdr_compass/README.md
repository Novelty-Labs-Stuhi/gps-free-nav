# pdr_compass: step counting for a walker (baseline)

**Summary.** Walker step counting: each step moves one stride along the compass heading.

**Author:** Arsenii Chistiakov.

**Idea.** Pedestrian dead reckoning: each detected step moves the position by the reported stride length along the
magnetometer heading, which is calibrated once at the known start. Height comes from the barometer.

**Result.** None on the current suite. Since 24 Oct the benchmark is drones only, so this walker-only method has no
scenario to run on, and its `results.json` belongs to the earlier one-world suite.
