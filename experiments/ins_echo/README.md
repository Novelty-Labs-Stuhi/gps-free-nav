# ins_echo

**Summary.** Particle filter: 1000 position guesses, each sliding the lidar point cloud over a height grid of the map and weighted by how well it lies on the terrain.

**Author:** Arsenii Chistiakov.

**Idea.** Terrain matching with a particle filter. Each lidar frame becomes a small point cloud (ranges rotated into the world by the INS attitude). Every particle slides that cloud to its own position and heading and is weighted by how well it lies on a 10 m height grid of the map. Between frames particles move with the INS acceleration; height from the barometer. Base for `terrain_pf` (X1) and the variants below.

**Result**

| scenario | score | flights lost (over 50 m) |
|---|---|---|
| Alpine valley | 6.2 km | 100% |
| Lapland fells | 6.6 km | 100% |
| Boreal forest hills | 4.5 km | 100% |
| Gulf of Finland archipelago | 7.6 km | 100% |
| Mid-size city | 8.8 km | 100% |
| Small border town | 9.8 km | 100% |
| Big dense city | 10.6 km | 100% |
| Steppe fields | 6.7 km | 100% |
| Farmland and villages | 4.8 km | 100% |
| Forested mountains | 6.7 km | 100% |
| Flat port city | 10.9 km | 100% |
| Desert dunes | 6.1 km | 100% |
| **overall** | **7.2 km** | 100% |
