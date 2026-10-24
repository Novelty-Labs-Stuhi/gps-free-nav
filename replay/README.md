# Replay viewer

Watch one benchmark run play back in 3D:

- **Left, the drone's world:** the prior map mesh, the drone at its *estimated* pose, and every echo beam it fires.
  Each beam is coloured by measured range minus the range the map predicts from the estimated pose:
  green agrees (within 3σ of the echo noise, 0.05 m + 1 % of range), red is shorter than the map
  (something the map lacks), blue is longer (the map has something that isn't there, or the estimate is off),
  magenta means the map predicts no hit. Saturation is reached 10 m past the agreement band.
  Beams with no return are faint grey lines at full range. The camera follows the estimate; when it leaves
  the map, a grid and a notice show how far past the edge it is.
- **Right, the real world:** the true mesh, the true trajectory (white), the planned route (yellow dashes),
  the estimated trajectory (red), the true and estimated drones, and a red line joining them.
  Tick *beams from true pose* to draw the measured beams from where the drone really was.
- **Bottom:** error, running geometric-mean error, and deviations (estimate vs truth horizontally and vertically,
  truth vs planned) over time, on a log or linear axis. Play/pause (Space), speed, the scrub bar, ←/→ (±1 s)
  and clicking the chart all move the same clock.

```bash
cd replay && npm install && npm run dev     # http://localhost:5174
```

The page lists every replay in `data/replays/index.json`; `?replay=<experiment>/<run_id>` opens one directly.
The dev server serves `../data/replays` at `/replays/`.

## Exporting a replay

```bash
uv run python replay/export_sample.py ins_compass --route yosemite/drone-gen0 --seed 0
uv run python replay/export_sample.py path/to/some_experiment     # any folder holding an algo.py
```

It runs the experiment exactly like `gpsfree.evaluate.run_one` (same route, seed and sensor streams), records the
estimate at 10 Hz, ray-casts the map from the estimated position for the predicted ranges, crops the world mesh to
the true route and the estimated path (clipped to the world) plus 600 m (and clusters vertices if it is still above 400k triangles), then writes the folder below and
refreshes `data/replays/index.json`. Today the map is the true world, so `truth.glb` and `map.glb` are the same mesh.
`write_replay()` in that script can be reused by an evaluator that has its own truth and map.

## Format

`data/replays/<experiment>/<run_id>/`

| file | contents |
|---|---|
| `replay.json` | everything below |
| `truth.glb` | the true world mesh, glTF Y-up |
| `map.glb` | the map mesh the drone carries, glTF Y-up |

`replay.json`, all positions in ENU metres (x east, y north, z up), `null` for missing values:

| key | shape | meaning |
|---|---|---|
| `experiment`, `scenario`, `world`, `run_id` | string | labels |
| `t` | `[n]` | pose times, s (10 Hz) |
| `truth_p` | `[n][3]` | true position |
| `truth_q` | `[n][4]` | true attitude, quaternion `x, y, z, w`, body (FLU) to world |
| `est_p` | `[n][3]` | estimated position |
| `planned_p` | `[m][3]` | planned route waypoints |
| `echo.t` | `[k]` | echo scan times, s |
| `echo.dirs_body` | `[b][3]` | beam unit vectors, body FLU |
| `echo.max_range` | number | beam range limit, m |
| `echo.measured` | `[k][b]` | measured range, `null` for no return |
| `echo.predicted` | `[k][b]` | map range from the estimated pose, `null` for no hit |
| `metrics.err` | `[n]` | 3D error \|est − truth\| |
| `metrics.geo_mean_err` | `[n]` | running geometric mean of `max(err, error_floor)` over samples past `score_from_m` (`null` before) |
| `metrics.dev_xy` | `[n]` | horizontal \|est − truth\| |
| `metrics.dev_z` | `[n]` | est z − truth z (signed; the log chart plots its magnitude) |
| `metrics.dev_plan` | `[n]` | \|truth − planned route at the same time\| |

Meshes convert ENU to Y-up as `(x, z, −y)`, as `gpsfree/worlds/bake.py` does. Algorithms only report a
position, so both drones and both beam fans use the true attitude.
