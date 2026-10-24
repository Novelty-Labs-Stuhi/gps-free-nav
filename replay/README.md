# Replay viewer

One window for one benchmark run: what the drone believed next to what really happened, with every chart
on the same clock.

- **Header:** experiment, scenario and run pickers (from `data/replays/index.json`).
- **Left 3D view, the drone's world:** the prior map mesh, the drone at its *estimated* pose, and every echo beam
  it fires. Each beam is coloured by measured range minus the range the map predicts from the estimated pose:
  green agrees (within 3σ of the echo noise, 0.05 m + 1 % of range), red is shorter than the map (something the
  map lacks), blue is longer (the map has something that isn't there, or the estimate is off), magenta means the
  map predicts no hit. Colours saturate 10 m past the agreement band. Beams with no return are faint grey.
  Chips toggle the layers: hits, disagree, misses. Off the map edge, a grid and a notice say how far out it is.
- **Right 3D view, the real world:** the true mesh, true trajectory (white), planned route (yellow dashes),
  estimated trajectory (red), both drones and the line joining them. Chips toggle each layer, plus the measured
  beams from the true pose.
- **Summary strip:** score (geometric-mean error), final and worst error, time over 50 m, share of echoes that
  agree with the map, and the three beams with the most disagreeing echoes. Click worst error or time over 50 m
  to jump there; click a beam to focus it in both views and the heatmap.
- **Transport:** play/pause, ±1 s, speed, scrubber, and camera presets: follow, top-down, chase, overview.
- **Charts:** position error and running geo-mean (log), deviations (estimate vs truth horizontally and
  vertically, truth vs planned), and a beam × time heatmap of echo residuals. Hovering any chart previews that
  moment in both 3D views while paused; click or drag to seek. Legend chips toggle series.
- **Keys:** Space play/pause · ←/→ 1 s (Shift 10 s) · , . one sample · Home/End · −/+ speed · 1–4 camera ·
  H/D/M beam layers · B true-pose beams · L log scale · Esc clear focus · ? help.
  The dock is resizable from its top edge; camera, speed, layers and dock height are remembered per browser.

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
