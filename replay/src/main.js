import * as THREE from "three";
import { BeamHeatmap, TimeChart, bisect, fmtM } from "./charts.js";
import {
  Beams, CAMERA_MODES, MAP_RAMP, TRUTH_RAMP, View, beamLabel, beamLayer, enu, enuQuat,
  loadMesh, makeDrone, makeLine, scaleToCamera, vectors,
} from "./scene.js";

const $ = (id) => document.getElementById(id);
const status = (s) => ($("status").textContent = s);
const SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16, 32, 64];
const LOST_M = 50;  // suite lost_threshold_m

const ERR_SERIES = [
  { key: "err", label: "error", color: "#ff4d6d", width: 1.6 },
  { key: "geo_mean_err", label: "running geo-mean", color: "#ffffff", width: 2 },
];
const DEV_SERIES = [
  { key: "dev_xy", label: "horizontal", color: "#58a6ff", width: 1.2 },
  { key: "dev_z", label: "vertical (signed)", color: "#c792ea", width: 1.2, signed: true },
  { key: "dev_plan", label: "truth vs planned", color: "#ffd23f", width: 1.2 },
];

// Per-viewer preferences survive switching runs; storage may be unavailable.
const prefs = (() => {
  try { return JSON.parse(localStorage.getItem("gpsfree-replay") || "{}"); } catch { return {}; }
})();
const savePrefs = () => {
  try { localStorage.setItem("gpsfree-replay", JSON.stringify(prefs)); } catch { /* private mode */ }
};

// ---------- run picker ----------

async function listReplays() {
  try {
    const r = await fetch("/replays/index.json");
    if (!r.ok) return [];
    // Entries are objects; older indexes were plain "<experiment>/<run_id>" strings.
    return (await r.json()).map((e) => (typeof e === "string"
      ? { id: e, experiment: e.split("/")[0], scenario: "–", run_id: e.split("/")[1] } : e));
  } catch {
    return [];
  }
}

function setupPicker(entries, current) {
  const pe = $("pickExperiment"), ps = $("pickScenario"), pr = $("pickRun");
  let cur = entries.find((e) => e.id === current);
  if (!cur) {
    cur = { id: current, experiment: current.split("/")[0], scenario: "–", run_id: current.split("/")[1] };
    entries = [cur, ...entries];
  }
  const uniq = (xs) => [...new Set(xs)];
  const fill = (sel, values, chosen, label = (v) => v) => {
    sel.replaceChildren(...values.map((v) => new Option(label(v), v, false, v === chosen)));
  };
  fill(pe, uniq(entries.map((e) => e.experiment)), cur.experiment);
  const inExp = entries.filter((e) => e.experiment === cur.experiment);
  fill(ps, uniq(inExp.map((e) => e.scenario)), cur.scenario);
  fill(pr, inExp.filter((e) => e.scenario === cur.scenario).map((e) => e.id), cur.id, (id) => entries.find((e) => e.id === id).run_id);
  const go = (id) => id && id !== current && (location.search = `?replay=${encodeURIComponent(id)}`);
  pe.onchange = () => {
    const c = entries.filter((e) => e.experiment === pe.value);
    go((c.find((e) => e.scenario === cur.scenario && e.run_id === cur.run_id) || c.find((e) => e.scenario === cur.scenario) || c[0])?.id);
  };
  ps.onchange = () => {
    const c = inExp.filter((e) => e.scenario === ps.value);
    go((c.find((e) => e.run_id === cur.run_id) || c[0])?.id);
  };
  pr.onchange = () => go(pr.value);
}

// ---------- run summary ----------

function summarize(R) {
  const err = R.metrics.err, t = R.t, n = t.length, dt = (t.at(-1) - t[0]) / Math.max(1, n - 1);
  let worst = -1, worstI = 0, over = 0, firstLost = -1;
  err.forEach((e, i) => {
    if (e == null) return;
    if (e > worst) { worst = e; worstI = i; }
    if (e > LOST_M) { over++; if (firstLost < 0) firstLost = i; }
  });
  // Beam agreement: share of returned echoes within the noise band of the map prediction.
  const nb = R.echo.dirs_body.length, seen = new Array(nb).fill(0), bad = new Array(nb).fill(0);
  let hits = 0, total = 0;
  R.echo.measured.forEach((row, j) => row.forEach((m, b) => {
    if (m == null) return;
    seen[b]++;
    total++;
    if (beamLayer(m, R.echo.predicted[j][b]) === "hit") hits++; else bad[b]++;
  }));
  // Rank by the number of disagreeing echoes, so a beam that rarely returns doesn't top the list.
  const ranked = seen.map((s, b) => ({ b, bad: bad[b], frac: s ? bad[b] / s : 0 })).filter((x) => x.bad > 0)
    .sort((a, b) => b.bad - a.bad).slice(0, 3);
  return {
    geo: R.metrics.geo_mean_err.findLast((v) => v != null), final: err.findLast((v) => v != null),
    worst, worstT: t[worstI], over: over * dt, firstLostT: firstLost >= 0 ? t[firstLost] : null,
    agree: total ? hits / total : null, ranked,
  };
}

const grade = (m) => (m == null ? "" : m < 10 ? "good" : m < LOST_M ? "warn" : "bad");

function renderSummary(S, R, { seek, focusBeam }) {
  const t0 = R.t[0];
  const stat = (label, value, cls = "", extra = "", onclick = null) => {
    const d = document.createElement("div");
    d.className = `stat ${cls}${onclick ? " link" : ""}`;
    d.innerHTML = `<small>${label}</small><b>${value}</b>${extra}`;
    if (onclick) {
      d.onclick = onclick;
      d.title = "Jump there";
    }
    return d;
  };
  const beams = document.createElement("div");
  beams.className = "stat";
  beams.innerHTML = `<small>most disagreeing beams</small>`;
  const list = document.createElement("div");
  list.className = "beamlist";
  if (!S.ranked.length) list.innerHTML = `<span class="muted">none</span>`;
  for (const { b, bad, frac } of S.ranked) {
    const btn = document.createElement("button");
    btn.dataset.beam = b;
    btn.textContent = `${beamLabel(R.echo.dirs_body[b])} · ${(frac * 100).toFixed(0)}%`;
    btn.title = `${bad} of its echoes disagree with the map; click to focus it in both views and the heatmap`;
    btn.onclick = () => focusBeam(b);
    list.append(btn);
  }
  beams.append(list);
  $("summary").replaceChildren(
    stat("score (geo-mean error)", fmtM(S.geo), grade(S.geo)),
    stat("final error", fmtM(S.final), grade(S.final)),
    stat("worst error", fmtM(S.worst), grade(S.worst), `<em>at ${(S.worstT - t0).toFixed(0)} s</em>`, () => seek(S.worstT)),
    stat(`time over ${LOST_M} m`, `${S.over.toFixed(0)} s`, S.over > 0 ? "bad" : "good",
      S.firstLostT != null ? `<em>from ${(S.firstLostT - t0).toFixed(0)} s</em>` : "", S.firstLostT != null ? () => seek(S.firstLostT) : null),
    stat("echoes agreeing with map", S.agree == null ? "–" : `${(S.agree * 100).toFixed(0)}%`, S.agree > 0.9 ? "good" : S.agree > 0.6 ? "warn" : "bad"),
    beams,
  );
}

// ---------- sampling ----------

function lerpPos(arr, i, f, out) {
  const a = arr[i], b = arr[Math.min(i + 1, arr.length - 1)];
  if (!a || a[0] == null) return null;
  if (!b || b[0] == null) return enu(a, out);
  return out.set(a[0] + (b[0] - a[0]) * f, a[2] + (b[2] - a[2]) * f, -(a[1] + (b[1] - a[1]) * f));
}

// ---------- app ----------

async function main() {
  const entries = await listReplays();
  const id = new URLSearchParams(location.search).get("replay") || entries[0]?.id;
  if (!id) return status("no replays in data/replays: run replay/export_sample.py");
  setupPicker(entries, id);

  const base = `/replays/${id.split("/").map(encodeURIComponent).join("/")}`;
  status(`loading ${id}…`);
  const rj = await fetch(`${base}/replay.json`);
  if (!rj.ok) return status(`cannot load ${base}/replay.json (${rj.status})`);
  const R = await rj.json();
  const [mapMesh, truthMesh] = await Promise.all([loadMesh(`${base}/map.glb`, MAP_RAMP), loadMesh(`${base}/truth.glb`, TRUTH_RAMP)]);
  document.title = `${R.experiment} · ${R.run_id} · gpsfree replay`;

  const left = new View($("left")), right = new View($("right"));
  left.scene.add(mapMesh);
  right.scene.add(truthMesh);
  const truthV = vectors(R.truth_p), estV = vectors(R.est_p), planV = R.planned_p.map((p) => enu(p));
  const nb = R.echo.dirs_body.length;
  for (const p of [...truthV, ...planV]) right.bounds.expandByPoint(p);
  for (const p of estV) left.bounds.expandByPoint(p);

  // Left: what the drone believes.
  const estDroneL = makeDrone(0xff4d6d), beamsL = new Beams(nb), estTrailL = makeLine(estV, 0xff4d6d);
  left.scene.add(estDroneL, beamsL.group, estTrailL);

  // Off the map there is nothing to draw: show a ground grid under the estimate and say so.
  const mapBox = new THREE.Box3().setFromObject(mapMesh);
  const offGrid = new THREE.GridHelper(4000, 40, 0x5a6b85, 0x2c3646);
  offGrid.position.y = mapBox.min.y;
  left.scene.add(offGrid);
  const updateOffMap = (p) => {
    const dx = Math.max(mapBox.min.x - p.x, 0, p.x - mapBox.max.x), dz = Math.max(mapBox.min.z - p.z, 0, p.z - mapBox.max.z);
    const out = dx > 0 || dz > 0;
    offGrid.visible = out;
    offGrid.position.x = Math.round(p.x / 100) * 100;
    offGrid.position.z = Math.round(p.z / 100) * 100;
    $("offmap").hidden = !out;
    if (out) $("offmap").textContent = `Estimate is ${fmtM(Math.hypot(dx, dz))} past the edge of the map: nothing for the beams to hit`;
  };

  // Right: what actually happened. Each chip in the panel header toggles one layer.
  const truthDrone = makeDrone(0xffffff), estDroneR = makeDrone(0xff4d6d);
  const truthTrail = makeLine(truthV, 0xffffff), estTrailR = makeLine(estV, 0xff4d6d);
  const link = makeLine([new THREE.Vector3(), new THREE.Vector3()], 0xff4d6d, { opacity: 0.9 });
  const beamsR = new Beams(nb);
  const layers = {
    truth: [makeLine(truthV, 0xffffff, { opacity: 0.25 }), truthTrail, truthDrone],
    planned: [makeLine(planV, 0xffd23f, { dashed: true, dash: 8, opacity: 0.9 })],
    estimate: [estTrailR, link, estDroneR],
    beams: [beamsR.group],
  };
  for (const objs of Object.values(layers)) right.scene.add(...objs);

  // ---------- state ----------
  const t0 = R.t[0], t1 = R.t.at(-1);
  let time = t0, hoverTime = null, playing = false, lastFrame = performance.now();
  let speed = SPEEDS.includes(prefs.speed) ? prefs.speed : 1;
  const show = { truth: true, planned: true, estimate: true, beams: false, ...prefs.show };
  Object.assign(beamsL.layers, prefs.beamLayers);
  Object.assign(beamsR.layers, prefs.beamLayers);

  const seek = (t) => { time = Math.min(t1, Math.max(t0, t)); render(); };
  const setPlaying = (p) => {
    if (p && time >= t1) time = t0;
    playing = p;
    $("play").textContent = playing ? "❚❚" : "▶";
  };

  // ---------- charts ----------
  const chartOpts = {
    tip: $("tip"),
    onSeek: (t) => seek(t),
    onHover: (t) => { hoverTime = t; render(); },
  };
  const errChart = new TimeChart($("chartErr"), R.t, R.metrics, ERR_SERIES, { ...chartOpts, log: prefs.errLog ?? true });
  const devChart = new TimeChart($("chartDev"), R.t, R.metrics, DEV_SERIES, { ...chartOpts, log: prefs.devLog ?? false });
  const heat = new BeamHeatmap($("chartBeams"), R.t, R.echo, { ...chartOpts, onBeam: (b) => focusBeam(b) });
  const charts = [errChart, devChart, heat];

  for (const [chart, holder] of [[errChart, "errChips"], [devChart, "devChips"]]) {
    for (const s of chart.series) {
      const b = document.createElement("button");
      b.className = "chip small on";
      b.innerHTML = `<i style="background:${s.color}"></i>${s.label}`;
      b.onclick = () => { chart.toggle(s.key); b.classList.toggle("on"); };
      $(holder).append(b);
    }
  }
  const logBtns = [...document.querySelectorAll("[data-log]")];
  const chartFor = (b) => (b.dataset.log === "err" ? errChart : devChart);
  const syncLog = () => logBtns.forEach((b) => b.classList.toggle("on", chartFor(b).log));
  logBtns.forEach((b) => (b.onclick = () => {
    const c = chartFor(b);
    c.setLog(!c.log);
    prefs[b.dataset.log === "err" ? "errLog" : "devLog"] = c.log;
    savePrefs();
    syncLog();
  }));
  syncLog();

  // ---------- beam focus + layers ----------
  function focusBeam(b) {
    const next = b === beamsL.highlight ? -1 : b;
    beamsL.highlight = beamsR.highlight = heat.highlight = next;
    document.querySelectorAll(".beamlist button").forEach((x) => x.classList.toggle("on", +x.dataset.beam === next));
    $("beamFocus").hidden = next < 0;
    if (next >= 0) $("beamFocus").textContent = `Focused on beam ${beamLabel(R.echo.dirs_body[next])} · click or Esc to clear`;
    render();
  }
  $("beamFocus").onclick = () => focusBeam(-1);

  const syncChips = () => {
    document.querySelectorAll("#beamChips .chip").forEach((c) => c.classList.toggle("on", beamsL.layers[c.dataset.layer]));
    document.querySelectorAll("#worldChips .chip").forEach((c) => c.classList.toggle("on", show[c.dataset.show]));
    for (const [k, objs] of Object.entries(layers)) for (const o of objs) o.visible = show[k];
  };
  const toggleLayer = (layer) => {
    beamsL.layers[layer] = beamsR.layers[layer] = !beamsL.layers[layer];
    prefs.beamLayers = { ...beamsL.layers };
    savePrefs();
    syncChips();
    render();
  };
  const toggleShow = (k) => {
    show[k] = !show[k];
    prefs.show = show;
    savePrefs();
    syncChips();
    render();
  };
  document.querySelectorAll("#beamChips .chip").forEach((c) => (c.onclick = () => toggleLayer(c.dataset.layer)));
  document.querySelectorAll("#worldChips .chip").forEach((c) => (c.onclick = () => toggleShow(c.dataset.show)));
  syncChips();

  // ---------- transport ----------
  const scrub = $("scrub");
  Object.assign(scrub, { min: t0, max: t1, step: (t1 - t0) / 5000 });
  scrub.oninput = () => seek(+scrub.value);
  $("speed").replaceChildren(...SPEEDS.map((s) => new Option(`${s}×`, s, false, s === speed)));
  const setSpeed = (s) => { speed = s; $("speed").value = s; prefs.speed = s; savePrefs(); };
  $("speed").onchange = (e) => setSpeed(+e.target.value);
  $("play").onclick = () => setPlaying(!playing);
  $("back").onclick = () => seek(time - 1);
  $("fwd").onclick = () => seek(time + 1);

  const camButtons = document.querySelectorAll("#camModes button");
  const setCamera = (mode) => {
    left.setMode(mode, estDroneL.position);
    right.setMode(mode, truthDrone.position);
    camButtons.forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
    prefs.camera = mode;
    savePrefs();
  };
  camButtons.forEach((b) => (b.onclick = () => setCamera(b.dataset.mode)));

  // The dock (summary, transport, charts) is resizable from its top edge.
  const dock = $("dock");
  if (prefs.dock) dock.style.setProperty("--dock", `${prefs.dock}px`);
  $("grip").onpointerdown = (e) => {
    const startY = e.clientY, startH = dock.offsetHeight;
    const move = (ev) => {
      const h = Math.min(innerHeight - 160, Math.max(170, startH + startY - ev.clientY));
      dock.style.setProperty("--dock", `${h}px`);
      prefs.dock = h;
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", () => { removeEventListener("pointermove", move); savePrefs(); }, { once: true });
  };

  const help = $("help");
  $("helpBtn").onclick = () => (help.hidden = !help.hidden);
  help.onclick = (e) => e.target === help && (help.hidden = true);

  const faster = () => setSpeed(SPEEDS[Math.min(SPEEDS.length - 1, SPEEDS.indexOf(speed) + 1)]);
  const KEYS = {
    " ": () => setPlaying(!playing),
    ".": () => seek(time + 0.1),
    ",": () => seek(time - 0.1),
    Home: () => seek(t0),
    End: () => seek(t1),
    "+": faster,
    "=": faster,
    "-": () => setSpeed(SPEEDS[Math.max(0, SPEEDS.indexOf(speed) - 1)]),
    h: () => toggleLayer("hit"),
    d: () => toggleLayer("disagree"),
    m: () => toggleLayer("miss"),
    b: () => toggleShow("beams"),
    l: () => logBtns[0].click(),
    Escape: () => (help.hidden ? focusBeam(-1) : (help.hidden = true)),
    "?": () => (help.hidden = !help.hidden),
  };
  KEYS["/"] = KEYS["?"];
  CAMERA_MODES.forEach((m, i) => (KEYS[String(i + 1)] = () => setCamera(m)));
  addEventListener("keydown", (e) => {
    if (e.target.tagName === "SELECT" || e.metaKey || e.ctrlKey || e.altKey) return;
    const step = e.shiftKey ? 10 : 1;
    const act = e.key === "ArrowRight" ? () => seek(time + step)
      : e.key === "ArrowLeft" ? () => seek(time - step)
      : KEYS[e.key.length === 1 ? e.key.toLowerCase() : e.key];
    if (!act) return;
    e.preventDefault();
    act();
  });

  // ---------- per-frame drawing ----------
  const qa = new THREE.Quaternion(), qb = new THREE.Quaternion(), q = new THREE.Quaternion();
  const pT = new THREE.Vector3(), pE = new THREE.Vector3();

  // Place drones, beams and trails at the playhead, or at a chart hover while paused.
  function render() {
    const at = hoverTime != null && !playing ? hoverTime : time;
    const i = bisect(R.t, at);
    const f = i + 1 < R.t.length ? Math.min(1, Math.max(0, (at - R.t[i]) / (R.t[i + 1] - R.t[i]))) : 0;
    const hasTruth = lerpPos(R.truth_p, i, f, pT) != null;
    const hasEst = lerpPos(R.est_p, i, f, pE) != null;
    enuQuat(R.truth_q[i], qa);
    enuQuat(R.truth_q[Math.min(i + 1, R.t.length - 1)], qb);
    q.slerpQuaternions(qa, qb, f);

    // Echo frame: the latest scan at or before `at`. Algorithms report position only, so both
    // drones use the true attitude.
    const e = bisect(R.echo.t, at), meas = R.echo.measured[e], pred = R.echo.predicted[e];

    estDroneL.visible = beamsL.group.visible = hasEst;
    estDroneR.visible = link.visible = hasEst && show.estimate;
    if (hasEst) {
      estDroneL.position.copy(pE);
      estDroneL.quaternion.copy(q);
      beamsL.update(pE, q, R.echo.dirs_body, meas, pred, R.echo.max_range);
      estDroneR.position.copy(pE);
      estDroneR.quaternion.copy(q);
      updateOffMap(pE);
    }
    if (hasTruth) {
      truthDrone.position.copy(pT);
      truthDrone.quaternion.copy(q);
      if (show.beams) beamsR.update(pT, q, R.echo.dirs_body, meas, pred, R.echo.max_range);
    }
    if (hasEst && hasTruth) {
      link.geometry.attributes.position.array.set([pT.x, pT.y, pT.z, pE.x, pE.y, pE.z]);
      link.geometry.attributes.position.needsUpdate = true;
    }
    for (const l of [estTrailL, estTrailR, truthTrail]) l.geometry.setDrawRange(0, i + 1);

    for (const c of charts) c.draw(time);
    scrub.value = time;
    const preview = at !== time ? ` <span class="muted">· preview ${(at - t0).toFixed(1)} s</span>` : "";
    $("clock").innerHTML = `${(time - t0).toFixed(1)} / ${(t1 - t0).toFixed(0)} s${preview}`;
  }

  function frame(now) {
    const dt = Math.min(0.1, (now - lastFrame) / 1000);
    lastFrame = now;
    if (playing) {
      time += dt * speed;
      if (time >= t1) { time = t1; setPlaying(false); }
      render();
    }
    if (estDroneL.visible) left.track(estDroneL.position, q);
    right.track(truthDrone.position, q);
    for (const [v, drones] of [[left, [estDroneL]], [right, [truthDrone, estDroneR]]]) {
      for (const d of drones) scaleToCamera(d, v.camera);
      v.render();
    }
    requestAnimationFrame(frame);
  }

  // Initial views: behind and above the start, looking down the route.
  const p0 = truthV[0], dir = truthV[Math.min(50, truthV.length - 1)].clone().sub(p0).setY(0);
  if (dir.lengthSq() < 1) dir.set(1, 0, 0);
  const off = dir.normalize().multiplyScalar(-160).add(new THREE.Vector3(0, 90, 0));
  left.place(estV[0], off);
  right.place(truthV[0], off.clone().multiplyScalar(2.5));
  render();
  setCamera(CAMERA_MODES.includes(prefs.camera) ? prefs.camera : "follow");

  renderSummary(summarize(R), R, { seek, focusBeam });
  status(`${R.world} · ${(t1 - t0).toFixed(0)} s · ${nb} beams · press ? for shortcuts`);
  requestAnimationFrame(frame);
}

main().catch((e) => {
  console.error(e);
  status(`error: ${e.message}`);
});
