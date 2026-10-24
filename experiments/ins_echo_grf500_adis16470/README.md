# ins_echo_grf500_adis16470

**Summary.** ins_echo with a single-beam GRF-500 rangefinder: TERCOM-style, matching the height profile flown so far.

**Author:** Arsenii Chistiakov.

**Idea.** `ins_echo` with a LightWare GRF-500 single beam looking down. With one beam per frame, matching works like cruise-missile TERCOM: the filter correlates the terrain profile flown so far against the map.

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 13.3 m | 80% |
| Lapland fells | 12.5 m | 70% |
| Boreal forest hills | 13.1 m | 80% |
| Gulf of Finland archipelago | 409.3 m | 100% |
| Mid-size city | 138.0 m | 100% |
| Small border town | 77.0 m | 90% |
| Big dense city | 352.8 m | 100% |
| Steppe fields | 405.5 m | 100% |
| Farmland and villages | 38.6 m | 95% |
| Forested mountains | 47.6 m | 95% |
| Flat port city | 201.6 m | 100% |
| Desert dunes | 34.5 m | 85% |
| **overall** | **71.3 m** | 91% |
