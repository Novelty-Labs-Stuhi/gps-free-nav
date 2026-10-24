import * as THREE from "three";
import { BeamHeatmap, TimeChart, bisect, fmtM } from "./charts.js";
import {
  Beams, CAMERA_MODES, COLORS, MAP_RAMP, RADIUS_COLORS, TRUTH_RAMP, View, beamLabel, beamLayer, disposeTree, enu, enuQuat,
  loadMesh, makeDrone, makeLine, makeRadius, scaleToCamera, vectors,
} from "./scene.js";
import { ALERT_M, TIME_TO_ALERT_S, integrity, uncertaintyOf } from "./summary.js";
import { LOST_M, RunBrowser, fmtPct, fmtS, grade, normalizeEntry } from "./sidebar.js";

const $ = (id) => document.getElementById(id);
const SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16, 32, 64];
const NARROW = matchMedia("(max-width: 1099px)");

const ERR_SERIES = [
  { key: "err", label: "error", color: COLORS.estimate, width: 1.5 },
  { key: "geo_mean_err", label: "running geo-mean", color: "#111827", width: 2 },
];
const DEV_SERIES = [
  { key: "dev_xy", label: "horizontal", color: "#2563eb", width: 1.25 },
  { key: "dev_z", label: "vertical (signed)", color: "#7c3aed", width: 1.25, signed: true },
  { key: "dev_plan", label: "truth vs planned", color: COLORS.planned, width: 1.25 },
];

// Per-viewer preferences survive switching runs; storage may be unavailable.
const prefs = (() => {
  try { return JSON.parse(localStorage.getItem("gpsfree-replay") || "{}"); } catch { return {}; }
})();
const savePrefs = () => {
  try { localStorage.setItem("gpsfree-replay", JSON.stringify(prefs)); } catch { /* private mode */ }
};

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

async function listReplays() {
  try {
    const r = await fetch("/replays/index.json");
    if (!r.ok) return [];
    const list = await r.json();
    return Array.isArray(list) ? list.filter((e) => typeof e === "string" || e?.id).map(normalizeEntry) : [];
  } catch {
    return [];
  }
}

// Message over the 3D views: kind is "loading", "error" or "empty"; null hides it.
function viewState(kind, title = "", body = "") {
  const el = $("viewState");
  el.hidden = !kind;
  el.className = kind || "";
  if (kind === "loading") el.innerHTML = `<div class="pill"><span class="spinner"></span>${esc(title)}</div>`;
  else if (kind) el.innerHTML = `<div class="card-msg"><b>${esc(title)}</b>${body}</div>`;
}

// ---------- run summary ----------

function summarize(R, integ) {
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
    geo: R.score_m ?? R.metrics.geo_mean_err.findLast((v) => v != null), final: err.findLast((v) => v != null),
    worst: worst < 0 ? null : worst, worstT: t[worstI], over: over * dt, firstLostT: firstLost >= 0 ? t[firstLost] : null,
    agree: total ? hits / total : null, ranked, integ,
  };
}

// Headline numbers for the open run. Score leads; the ones that point at a moment are buttons that seek.
function renderSummary(S, R, { seek, focusBeam }) {
  const t0 = R.t[0];
  const stat = (label, value, cls = "", extra = "", onclick = null) => {
    const d = document.createElement(onclick ? "button" : "div");
    d.className = `stat ${cls}`;
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
    btn.textContent = `${beamLabel(R.echo.dirs_body[b])} · ${frac < 0.01 ? "<1" : (frac * 100).toFixed(0)}%`;
    btn.title = `${bad} of its echoes disagree with the map; click to focus it in both views and the heatmap`;
    btn.onclick = () => focusBeam(b);
    list.append(btn);
  }
  beams.append(list);
  const g = (m) => (m == null ? "" : grade(m));
  $("summary").replaceChildren(
    stat("score", fmtM(S.geo), `hero ${g(S.geo)}`),
    ...integrityStats(S.integ, t0, stat, seek),
    stat("final error", fmtM(S.final), g(S.final)),
    stat("worst", fmtM(S.worst), g(S.worst), S.worst != null ? `<em>at ${(S.worstT - t0).toFixed(0)} s</em>` : "", S.worst != null ? () => seek(S.worstT) : null),
    stat(`over ${LOST_M} m`, fmtS(S.over), S.over > 0 ? "bad" : "good",
      S.firstLostT != null ? `<em>from ${(S.firstLostT - t0).toFixed(0)} s</em>` : "", S.firstLostT != null ? () => seek(S.firstLostT) : null),
    stat("echoes agree", fmtPct(S.agree), S.agree == null ? "" : S.agree > 0.9 ? "good" : S.agree > 0.6 ? "warn" : "bad"),
    beams,
  );
}

// "Misleading %" and "silent failure" for runs whose replay carries the method's reported radius.
function integrityStats(I, t0, stat, seek) {
  if (!I) return [];
  if (!I.claimed) return [stat("integrity", "no claim", "", `<em title="The method never reports a radius">no radius reported</em>`)];
  const at = (t) => `${(t - t0).toFixed(0)} s`;
  // A 95 % radius should contain the truth about 95 % of the time.
  const mis = stat("misleading", fmtPct(I.misleading), I.misleading <= 0.05 ? "good" : I.misleading <= 0.2 ? "warn" : "bad",
    `<em>of ${fmtS(I.claimS)} with a radius</em>`);
  mis.title = "Share of the time a radius was claimed in which the true error was outside it";
  const silent = {
    yes: () => stat("silent failure", "yes", "bad", `<em>${fmtS(I.hmiS)} misleading from ${at(I.firstHmiT)}</em>`, () => seek(I.firstHmiT)),
    late: () => stat("silent failure", "late alarm", "warn", `<em>alarm at ${at(I.alarmT)}</em>`, () => seek(I.alarmT)),
    no: () => stat("silent failure", "no", "good", I.alarmT != null ? `<em>alarm at ${at(I.alarmT)}</em>` : "", I.alarmT != null ? () => seek(I.alarmT) : null),
  }[I.silent]();
  silent.title = `Error over ${ALERT_M} m while the reported radius stayed under ${ALERT_M} m for longer than the ${TIME_TO_ALERT_S} s time-to-alert`
    + " without the method raising an alarm (declaring itself lost or growing its radius past the limit)";
  return [mis, silent];
}

function renderCrumbs(e, R) {
  const dur = R ? `${(R.t.at(-1) - R.t[0]).toFixed(0)} s · ${R.echo.dirs_body.length} beams` : "";
  $("crumbs").innerHTML = `<span class="exp">${esc(e.experiment)}</span><span class="sep">/</span>
    <span class="run-name" title="${esc(e.id)}">${esc(e.route)}</span>${e.seed != null ? `<span class="seed">seed ${esc(e.seed)}</span>` : ""}
    ${[R?.scenario_name ?? R?.scenario ?? e.scenario_name ?? e.scenario, R?.world ?? e.world].filter((x) => x && x !== "–").map((x) => `<span class="tag">${esc(x)}</span>`).join("")}${dur ? `<span class="tag dim">${dur}</span>` : ""}`;
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
  const params = new URLSearchParams(location.search);

  // ---------- sidebar ----------
  const setSide = (open) => {
    document.body.dataset.side = open ? "open" : "closed";
    if (!NARROW.matches) { prefs.sidebar = open; savePrefs(); }
  };
  const syncNarrow = () => {
    document.body.toggleAttribute("data-narrow", NARROW.matches);
    setSide(NARROW.matches ? false : prefs.sidebar ?? true);
  };
  NARROW.addEventListener("change", syncNarrow);
  syncNarrow();
  const toggleSide = () => setSide(document.body.dataset.side !== "open");
  $("sideOpen").onclick = () => setSide(true);
  $("sideClose").onclick = () => setSide(false);
  // A floating list closes when you go back to the views.
  $("app").addEventListener("pointerdown", () => NARROW.matches && setSide(false));

  const browser = new RunBrowser($("sidebar"), entries, { prefs, savePrefs, onPick: (id) => loadRun(id) });
  $("prevRun").onclick = () => browser.step(-1);
  $("nextRun").onclick = () => browser.step(1);

  // ---------- views, drones and charts live for the whole session; runs swap in and out ----------
  const left = new View($("left")), right = new View($("right"));
  const estDroneL = makeDrone(COLORS.estimate), truthDrone = makeDrone(COLORS.truth), estDroneR = makeDrone(COLORS.estimate);
  const link = makeLine([new THREE.Vector3(), new THREE.Vector3()], COLORS.estimate, { opacity: 0.9 });
  // Off the map there is nothing to draw: show a ground grid under the estimate and say so.
  const offGrid = new THREE.GridHelper(4000, 40, 0x8d98a8, 0xc9d0da);
  offGrid.visible = false;
  // The method's reported 95 % radius around the estimate, in both worlds.
  const radiusL = makeRadius(), radiusR = makeRadius();
  left.scene.add(estDroneL, offGrid, radiusL);
  right.scene.add(truthDrone, estDroneR, link, radiusR);

  let run = null, loadSeq = 0;
  let time = 0, hoverTime = null, playing = false, lastFrame = performance.now();
  let speed = SPEEDS.includes(prefs.speed) ? prefs.speed : 1;
  let cameraMode = CAMERA_MODES.includes(prefs.camera) ? prefs.camera : "follow";
  const show = { truth: true, planned: true, estimate: true, beams: false, ...prefs.show };
  const beamLayers = { hit: true, disagree: true, miss: true, ...prefs.beamLayers };
  let focused = -1;

  const seek = (t) => { if (!run) return; time = Math.min(run.t1, Math.max(run.t0, t)); render(); syncUrl(); };
  const setPlaying = (p) => {
    if (!run) return;
    if (p && time >= run.t1) time = run.t0;
    playing = p;
    $("play").classList.toggle("playing", p);
    $("play").setAttribute("aria-label", p ? "Pause" : "Play");
    if (!p) syncUrl();
  };

  // The address bar always reopens what you see: ?replay=<id>&t=<seconds into the run>.
  let urlTimer = 0;
  function syncUrl(push = false) {
    clearTimeout(urlTimer);
    const write = () => {
      if (!run) return;
      const q = new URLSearchParams(location.search);
      q.set("replay", run.id);
      q.set("t", (time - run.t0).toFixed(1));
      history[push ? "pushState" : "replaceState"](null, "", `?${q}`);
    };
    push ? write() : (urlTimer = setTimeout(write, 400));
  }

  const chartOpts = {
    tip: $("tip"),
    onSeek: (t) => seek(t),
    onHover: (t) => { hoverTime = t; render(); },
  };
  const errChart = new TimeChart($("chartErr"), ERR_SERIES, { ...chartOpts, log: prefs.errLog ?? true, threshold: LOST_M });
  const devChart = new TimeChart($("chartDev"), DEV_SERIES, { ...chartOpts, log: prefs.devLog ?? false });
  const heat = new BeamHeatmap($("chartBeams"), { ...chartOpts, onBeam: (b) => focusBeam(b) });
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
  // The radius band on the error chart has its own legend toggle; hidden for runs without one.
  const bandChip = document.createElement("button");
  bandChip.id = "radiusChip";
  bandChip.className = "chip small on";
  bandChip.hidden = true;
  bandChip.title = "The method's reported 95% radius; red spans are hazardously misleading";
  bandChip.innerHTML = `<i class="sw-radius"></i>95% radius`;
  bandChip.onclick = () => { errChart.toggle("band"); bandChip.classList.toggle("on"); };
  $("errChips").append(bandChip);
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
    if (!run) return;
    focused = b === focused ? -1 : b;
    run.beamsL.highlight = run.beamsR.highlight = heat.highlight = focused;
    document.querySelectorAll(".beamlist button").forEach((x) => x.classList.toggle("on", +x.dataset.beam === focused));
    $("beamFocus").hidden = focused < 0;
    if (focused >= 0) $("beamFocus").textContent = `Focused on beam ${beamLabel(run.R.echo.dirs_body[focused])} · click or Esc to clear`;
    render();
  }
  $("beamFocus").onclick = () => focusBeam(-1);

  const syncChips = () => {
    document.querySelectorAll("#beamChips .chip").forEach((c) => c.classList.toggle("on", beamLayers[c.dataset.layer]));
    document.querySelectorAll("#worldChips .chip").forEach((c) => c.classList.toggle("on", show[c.dataset.show]));
    if (!run) return;
    Object.assign(run.beamsL.layers, beamLayers);
    Object.assign(run.beamsR.layers, beamLayers);
    for (const [k, objs] of Object.entries(run.layers)) for (const o of objs) o.visible = show[k];
  };
  const toggleLayer = (layer) => {
    beamLayers[layer] = !beamLayers[layer];
    prefs.beamLayers = { ...beamLayers };
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
  scrub.oninput = () => seek(+scrub.value);
  $("speed").replaceChildren(...SPEEDS.map((s) => new Option(`${s}×`, s, false, s === speed)));
  const setSpeed = (s) => { speed = s; $("speed").value = s; prefs.speed = s; savePrefs(); };
  $("speed").onchange = (e) => setSpeed(+e.target.value);
  $("play").onclick = () => setPlaying(!playing);
  $("back").onclick = () => seek(time - 1);
  $("fwd").onclick = () => seek(time + 1);

  const camButtons = document.querySelectorAll("#camModes button");
  const setCamera = (mode) => {
    cameraMode = mode;
    camButtons.forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
    prefs.camera = mode;
    savePrefs();
    if (!run) return;
    left.setMode(mode, estDroneL.position);
    right.setMode(mode, truthDrone.position);
  };
  camButtons.forEach((b) => (b.onclick = () => setCamera(b.dataset.mode)));
  camButtons.forEach((b) => b.classList.toggle("on", b.dataset.mode === cameraMode));

  // The dock (transport + charts) is resizable from its top edge.
  const dock = $("dock");
  if (prefs.dock) dock.style.setProperty("--dock", `${Math.min(prefs.dock, innerHeight - 200)}px`);
  $("grip").onpointerdown = (e) => {
    const startY = e.clientY, startH = dock.offsetHeight;
    const move = (ev) => {
      const h = Math.min(innerHeight - 200, Math.max(150, startH + startY - ev.clientY));
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
    Home: () => seek(run?.t0 ?? 0),
    End: () => seek(run?.t1 ?? 0),
    "+": faster,
    "=": faster,
    "-": () => setSpeed(SPEEDS[Math.max(0, SPEEDS.indexOf(speed) - 1)]),
    ArrowDown: () => browser.step(1),
    ArrowUp: () => browser.step(-1),
    j: () => browser.step(1),
    k: () => browser.step(-1),
    "[": toggleSide,
    "/": () => { setSide(true); $("search").focus(); $("search").select(); },
    h: () => toggleLayer("hit"),
    d: () => toggleLayer("disagree"),
    m: () => toggleLayer("miss"),
    b: () => toggleShow("beams"),
    l: () => logBtns[0].click(),
    Escape: () => (!help.hidden ? (help.hidden = true) : NARROW.matches && document.body.dataset.side === "open" ? setSide(false) : focusBeam(-1)),
    "?": () => (help.hidden = !help.hidden),
  };
  CAMERA_MODES.forEach((m, i) => (KEYS[String(i + 1)] = () => setCamera(m)));
  addEventListener("keydown", (e) => {
    if (["SELECT", "INPUT", "TEXTAREA"].includes(e.target.tagName) && e.target.type !== "range") return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const step = e.shiftKey ? 10 : 1;
    const act = e.key === "ArrowRight" ? () => seek(time + step)
      : e.key === "ArrowLeft" ? () => seek(time - step)
      : KEYS[e.key.length === 1 ? e.key.toLowerCase() : e.key];
    if (!act) return;
    e.preventDefault();
    act();
  });
  addEventListener("popstate", () => {
    const id = new URLSearchParams(location.search).get("replay");
    if (id && id !== run?.id) loadRun(id, { push: false });
  });

  // ---------- per-run scene content ----------

  function buildRun(id, R, mapMesh, truthMesh) {
    const truthV = vectors(R.truth_p), estV = vectors(R.est_p), planV = R.planned_p.map((p) => enu(p));
    const nb = R.echo.dirs_body.length;
    const beamsL = new Beams(nb), beamsR = new Beams(nb);
    const estTrailL = makeLine(estV, COLORS.estimate);
    const truthTrail = makeLine(truthV, COLORS.truth), estTrailR = makeLine(estV, COLORS.estimate);
    const layers = {
      truth: [makeLine(truthV, COLORS.truth, { opacity: 0.22 }), truthTrail, truthDrone],
      planned: [makeLine(planV, COLORS.planned, { dashed: true, dash: 8, opacity: 0.95 })],
      estimate: [estTrailR, link, estDroneR],
      beams: [beamsR.group],
    };
    const own = {  // objects this run added and must remove/dispose
      left: [mapMesh, beamsL.group, estTrailL],
      right: [truthMesh, ...layers.truth.slice(0, 2), ...layers.planned, estTrailR, beamsR.group],
    };
    left.scene.add(...own.left);
    right.scene.add(...own.right);
    left.bounds.makeEmpty();
    right.bounds.makeEmpty();
    for (const p of [...truthV, ...planV]) right.bounds.expandByPoint(p);
    for (const p of estV) left.bounds.expandByPoint(p);
    return {
      id, R, t0: R.t[0], t1: R.t.at(-1), truthV, estV, beamsL, beamsR, layers,
      trails: [estTrailL, estTrailR, truthTrail],
      mapBox: new THREE.Box3().setFromObject(mapMesh),
      dispose() {
        left.scene.remove(...own.left);
        right.scene.remove(...own.right);
        for (const o of [...own.left, ...own.right]) disposeTree(o);
      },
    };
  }

  const updateOffMap = (p) => {
    const b = run.mapBox;
    const dx = Math.max(b.min.x - p.x, 0, p.x - b.max.x), dz = Math.max(b.min.z - p.z, 0, p.z - b.max.z);
    const out = dx > 0 || dz > 0;
    offGrid.visible = out;
    offGrid.position.set(Math.round(p.x / 100) * 100, b.min.y, Math.round(p.z / 100) * 100);
    $("offmap").hidden = !out;
    if (out) $("offmap").textContent = `Estimate is ${fmtM(Math.hypot(dx, dz))} past the edge of the map: nothing for the beams to hit`;
  };

  // Load a run and swap it in. The previous run stays on screen until the new one is ready; a newer
  // request supersedes an older one still in flight.
  async function loadRun(id, { push = true } = {}) {
    const seq = ++loadSeq;
    browser.setCurrent(id);
    const entry = browser.cur();
    renderCrumbs(entry, null);
    viewState("loading", `Loading ${entry.route}${entry.seed != null ? ` · s${entry.seed}` : ""}…`);
    const base = `/replays/${id.split("/").map(encodeURIComponent).join("/")}`;
    let R, meshes;
    try {
      const rj = await fetch(`${base}/replay.json`);
      if (!rj.ok) throw new Error(`${base}/replay.json returned ${rj.status}`);
      R = await rj.json();
      meshes = await Promise.all([loadMesh(`${base}/map.glb`, MAP_RAMP), loadMesh(`${base}/truth.glb`, TRUTH_RAMP)]);
    } catch (err) {
      if (seq !== loadSeq) return;
      console.warn(err);
      return viewState("error", "Couldn't load this run", `<p>${esc(err.message)}</p><p>Pick another run from the list.</p>`);
    }
    if (seq !== loadSeq) return meshes.forEach(disposeTree);

    // Carry the playhead across as seconds into the run, so the same moment of a different run lines up.
    const first = !run;
    const rel = first ? +params.get("t") || 0 : time - run.t0;
    run?.dispose();
    focused = -1;
    run = buildRun(id, R, ...meshes);
    run.unc = uncertaintyOf(R);
    run.integ = run.unc ? integrity(R.t, R.metrics.err, run.unc) : null;
    time = Math.min(run.t1, Math.max(run.t0, run.t0 + rel));
    hoverTime = null;
    errChart.setData(R.t, R.metrics, { band: run.unc, hazard: run.integ?.hmi });
    devChart.setData(R.t, R.metrics);
    $("radiusChip").hidden = !run.unc;
    heat.highlight = -1;
    heat.setData(R.t, R.echo);
    Object.assign(scrub, { min: run.t0, max: run.t1, step: (run.t1 - run.t0) / 5000 });
    syncChips();
    $("beamFocus").hidden = true;
    render();

    if (first) {
      // Initial views: behind and above the start, looking down the route.
      const p0 = run.truthV[0], dir = run.truthV[Math.min(50, run.truthV.length - 1)].clone().sub(p0).setY(0);
      if (dir.lengthSq() < 1) dir.set(1, 0, 0);
      const off = dir.normalize().multiplyScalar(-160).add(new THREE.Vector3(0, 90, 0));
      left.place(estDroneL.position, off);
      right.place(truthDrone.position, off.clone().multiplyScalar(2.5));
      setCamera(cameraMode);
    } else {
      // Keep each camera's framing relative to its drone; overview re-fits the new route.
      for (const [v, p] of [[left, estDroneL.position], [right, truthDrone.position]]) {
        cameraMode === "overview" ? v.setMode("overview", p) : v.retarget(p);
      }
    }

    renderCrumbs(entry, R);
    renderSummary(summarize(R, run.integ), R, { seek, focusBeam });
    document.title = `${R.experiment} · ${R.run_id} · gpsfree replay`;
    viewState(null);
    syncUrl(push && !first);
  }

  // ---------- per-frame drawing ----------
  const qa = new THREE.Quaternion(), qb = new THREE.Quaternion(), q = new THREE.Quaternion();
  const pT = new THREE.Vector3(), pE = new THREE.Vector3();

  // Place drones, beams and trails at the playhead, or at a chart hover while paused.
  function render() {
    if (!run) return;
    const R = run.R, t0 = run.t0;
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

    estDroneL.visible = run.beamsL.group.visible = hasEst;
    estDroneR.visible = link.visible = hasEst && show.estimate;
    if (hasEst) {
      estDroneL.position.copy(pE);
      estDroneL.quaternion.copy(q);
      run.beamsL.update(pE, q, R.echo.dirs_body, meas, pred, R.echo.max_range);
      estDroneR.position.copy(pE);
      estDroneR.quaternion.copy(q);
      updateOffMap(pE);
    }
    if (hasTruth) {
      truthDrone.position.copy(pT);
      truthDrone.quaternion.copy(q);
      if (show.beams) run.beamsR.update(pT, q, R.echo.dirs_body, meas, pred, R.echo.max_range);
    }
    if (hasEst && hasTruth) {
      link.geometry.attributes.position.array.set([pT.x, pT.y, pT.z, pE.x, pE.y, pE.z]);
      link.geometry.attributes.position.needsUpdate = true;
    }
    for (const l of run.trails) l.geometry.setDrawRange(0, i + 1);
    renderIntegrity(i, hasEst);

    for (const c of charts) c.draw(time);
    scrub.value = time;
    const clock = $("clock");
    clock.classList.toggle("preview", at !== time);
    clock.title = at !== time ? "Previewing the hovered moment; click the chart to jump there" : "";
    clock.innerHTML = `${(at - t0).toFixed(1)} <span class="total">/ ${(run.t1 - t0).toFixed(0)} s</span>`;
  }

  // Radius rings, the LOST banner and the hazard banner for pose sample i.
  function renderIntegrity(i, hasEst) {
    const u = run.unc?.[i], hmi = !!run.integ?.hmi[i];
    const claim = hasEst && u != null && isFinite(u);
    const color = u >= ALERT_M ? RADIUS_COLORS.over : RADIUS_COLORS.ok;
    for (const [ring, at, vis] of [[radiusL, pE, claim], [radiusR, pE, claim && show.estimate]]) {
      ring.visible = vis;
      if (!vis) continue;
      ring.position.copy(at);
      ring.scale.set(u, 1, u);
      // In the real world the ring turns red when the truth is outside it and that is hazardous.
      ring.setColor(ring === radiusR && hmi ? RADIUS_COLORS.hmi : color);
    }
    $("lostBanner").hidden = !(hasEst && u === Infinity);
    const tag = $("radiusTag");
    tag.hidden = !run.unc || !hasEst || u === Infinity;
    tag.className = u == null ? "none" : u >= ALERT_M ? "over" : "";
    tag.innerHTML = u == null ? "no position claim" : `reported 95% radius <b>${fmtM(u)}</b>`;
    const hb = $("hmiBanner");
    hb.hidden = !hmi;
    if (hmi) hb.innerHTML = `<b>HAZARDOUSLY MISLEADING</b><span>${fmtM(run.R.metrics.err[i])} off while claiming ${fmtM(u)}</span>`;
  }

  function frame(now) {
    const dt = Math.min(0.1, (now - lastFrame) / 1000);
    lastFrame = now;
    if (run) {
      if (playing) {
        time += dt * speed;
        if (time >= run.t1) { time = run.t1; setPlaying(false); }
        render();
      }
      if (estDroneL.visible) left.track(estDroneL.position, q);
      right.track(truthDrone.position, q);
      for (const [v, drones] of [[left, [estDroneL]], [right, [truthDrone, estDroneR]]]) {
        for (const d of drones) scaleToCamera(d, v.camera);
      }
    }
    left.render();
    right.render();
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  const id = params.get("replay") || browser.visible()[0]?.id || entries[0]?.id;
  if (!id) {
    renderCrumbs({ experiment: "gpsfree", route: "no replays", seed: null, scenario: "–", world: "–" }, null);
    return viewState("empty", "No replays yet", `<p>Export a run and reload this page.</p>
      <code>uv run python replay/export_sample.py ins_compass --route yosemite/drone-gen0</code>`);
  }
  await loadRun(id, { push: false });
}

main().catch((e) => {
  console.error(e);
  viewState("error", "Something went wrong", `<p>${esc(e.message)}</p>`);
});
