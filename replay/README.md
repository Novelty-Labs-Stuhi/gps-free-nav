# Replay viewer

One window for one benchmark run: what the drone believed next to what really happened, with every chart
on the same clock.

- **Run browser (left sidebar):** every run in `data/replays/index.json`, grouped by experiment (and by scenario
  inside an experiment when several scenarios are listed). Each row shows the score (geometric-mean error, graded
  green < 10 m, amber < 50 m, red beyond), a log-scale error sparkline with the 50 m "lost" line, final error, time
  over 50 m and the share of echoes that agree with the map. Search box (`/`), scenario and world filters, sort by
  name or score, collapsible groups. One click opens a run in place: the playhead (seconds into the run), camera
  preset and layers carry over, so the same moment can be compared across runs. `↑`/`↓` or `J`/`K` walk the list.
  `[` hides it; collapsed, it becomes a rail of grade-coloured dots that still switch runs. Below 1100 px the list
  floats over the views instead of squeezing them, and closes when you click back into the app.
- **Run header:** experiment / route / seed, scenario and world, previous/next, help. Under it the headline numbers
  for the open run: score, final error, worst error, time over 50 m, echo agreement and the three beams with the
  most disagreeing echoes. Click worst error or time over 50 m to jump there; click a beam to focus it in both views
  and the heatmap.
- **Left 3D view, the drone's world:** the prior map mesh, the drone at its *estimated* pose, and every echo beam
  it fires. Each beam is coloured by measured range minus the range the map predicts from the estimated pose:
  green agrees (within 3σ of the echo noise, 0.05 m + 1 % of range), red is shorter than the map (something the
  map lacks), blue is longer (the map has something that isn't there, or the estimate is off), magenta means the
  map predicts no hit. Colours saturate 10 m past the agreement band. Beams with no return are faint grey.
  Chips toggle the layers: hits, disagree, misses. Off the map edge, a grid and a notice say how far out it is.
- **Right 3D view, the real world:** the true mesh, true trajectory (dark), planned route (amber dashes),
  estimated trajectory (red), both drones and the line joining them. Chips toggle each layer, plus the measured
  beams from the true pose.
- **Transport:** play/pause, ±1 s, scrubber, speed, and camera presets: follow, top-down, chase, overview.
- **Charts:** position error and running geo-mean (log, with the 50 m line), deviations (estimate vs truth
  horizontally and vertically, truth vs planned), and a beam × time heatmap of echo residuals. Hovering any chart
  previews that moment in both 3D views while paused (the clock turns blue); click or drag to seek. Legend entries
  toggle series; shift-click a heatmap row to focus that beam.
- **Keys:** Space play/pause · ←/→ 1 s (Shift 10 s) · , . one sample · Home/End · −/+ speed · ↑/↓ or J/K run ·
  `[` run list · `/` search · 1–4 camera · H/D/M beam layers · B true-pose beams · L log scale · Esc clear focus ·
  ? help. The dock is resizable from its top edge; camera, speed, layers, filters, sort, sidebar and dock height are
  remembered per browser.

Light theme throughout: neutral greys, one indigo accent for what is interactive or current, green/amber/red only
for grading. Beam and trajectory colours are defined once in `src/scene.js` (`BEAM_COLORS`, `COLORS`) and mirrored
as CSS variables in `src/style.css`; chart ink lives in `INK` in `src/charts.js`.

```bash
cd replay && npm install && npm run dev     # http://localhost:5174
```

The page lists every replay in `data/replays/index.json`; `?replay=<experiment>/<run_id>&t=<seconds>` opens one
directly at that moment (the address bar keeps both up to date, and Back returns to the previous run).
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

`index.json` is a list of `{id, experiment, scenario, world, run_id}` plus a compact summary for the run browser:
`score_m` (last geo-mean error), `final_err_m`, `worst_err_m`, `time_over_50_s`, `duration_s`, `echo_agree` (share
of returned echoes within `3·(0.05 + 0.01·predicted)` of the map) and `err`, a ~60-point max-pooled error sparkline.
Summaries are cached by replay.json mtime and size (`stamp`). Rebuild it after adding replays by hand with
`uv run python -c "import sys; sys.path.insert(0,'replay'); import export_sample as e; e.update_index()"`. The viewer
also accepts entries without the summary, or plain `"<experiment>/<run_id>"` strings.

## Integrity: the method's own uncertainty

When `replay.json` carries `uncertainty[n]` (the method's 95 % horizontal radius per pose; `"inf"` = "I don't know
where I am", `null` = no claim), the viewer shows whether the method can be trusted about itself:

- **Drone's world:** a disc of that radius around the estimate, blue under the 50 m alert limit and amber above it,
  with the value in the corner. `"inf"` shows a **LOST: I don't know where I am** banner instead.
- **Real world:** the same disc around the estimate; it turns red, with a **HAZARDOUSLY MISLEADING** banner, when the
  error is over 50 m while the radius claims under 50 m.
- **Error chart:** the radius as a blue band under the error line, amber spans where the method declared itself
  lost, and red spans (with the error line in red) where it was hazardously misleading.
- **Summary and run list:**
  - *Misleading* is the share of the time a radius was claimed in which the error was outside it. A calibrated
    95 % radius should be near 5 %.
  - *Silent failure* is **yes** when a hazardously misleading episode lasts longer than the 6 s time-to-alert
    (ICAO LPV-200) without an alarm, **late alarm** when the alarm (lost, or a radius past 50 m) came after it,
    and **no** otherwise.
  - The run list badges these runs.

The dev server builds `/replays/index.json` itself from `data/replays/*/*/replay.json` (cached by file mtime), so
runs from any exporter show up with their summaries; the logic is in `src/summary.js`.

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
