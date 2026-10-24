import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Chart, SERIES, fmtM } from "./chart.js";

// Replay JSON is ENU (x east, y north, z up); three.js is Y-up: (x, y, z) -> (x, z, -y).
const enu = (p, out = new THREE.Vector3()) => out.set(p[0], p[2], -p[1]);
const enuQuat = (q, out = new THREE.Quaternion()) => out.set(q[0], q[2], -q[1], q[3]);

const $ = (id) => document.getElementById(id);
const status = (s) => ($("status").textContent = s);

// ---------- loading ----------

async function listReplays() {
  try {
    const r = await fetch("/replays/index.json");
    return r.ok ? await r.json() : [];
  } catch {
    return [];
  }
}

async function loadMesh(url, ramp) {
  const gltf = await new GLTFLoader().loadAsync(url);
  const group = new THREE.Group();
  gltf.scene.traverse((o) => {
    if (!o.isMesh) return;
    const g = o.geometry;
    g.computeVertexNormals();
    colorByHeight(g, ramp);
    group.add(new THREE.Mesh(g, contourMaterial()));
  });
  return group;
}

// Lambert with thin contour lines every CONTOUR_M of height, so slopes and altitude read at any zoom.
const CONTOUR_M = 20;
function contourMaterial() {
  const m = new THREE.MeshLambertMaterial({ vertexColors: true });
  m.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace("#include <common>", "#include <common>\nvarying float vHeight;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvHeight = (modelMatrix * vec4(position, 1.0)).y;");
    sh.fragmentShader = sh.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying float vHeight;")
      .replace("#include <dithering_fragment>", `#include <dithering_fragment>
        float h = vHeight / ${CONTOUR_M.toFixed(1)};
        float line = 1.0 - smoothstep(0.0, 1.2, abs(fract(h - 0.5) - 0.5) / fwidth(h));
        gl_FragColor.rgb *= 1.0 - 0.35 * line;`);
  };
  return m;
}

const MAP_RAMP = ["#33496b", "#557aa6", "#93afd3", "#e2ebf7"];
const TRUTH_RAMP = ["#3f5a2c", "#6b7d43", "#8a7556", "#a9a397", "#f2f2f2"];

function colorByHeight(g, ramp) {
  const pos = g.attributes.position;
  g.computeBoundingBox();
  const { min, max } = g.boundingBox;
  const stops = ramp.map((c) => new THREE.Color(c));
  const col = new Float32Array(pos.count * 3);
  const c = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const f = Math.min(0.999, Math.max(0, (pos.getY(i) - min.y) / (max.y - min.y || 1))) * (stops.length - 1);
    const k = Math.floor(f);
    c.copy(stops[k]).lerp(stops[k + 1], f - k);
    col.set([c.r, c.g, c.b], i * 3);
  }
  g.setAttribute("color", new THREE.BufferAttribute(col, 3));
}

// ---------- scene pieces ----------

class View {
  constructor(container) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    container.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0e1116);
    this.scene.add(new THREE.HemisphereLight(0xdde8ff, 0x404040, 0.9));
    const sun = new THREE.DirectionalLight(0xffffff, 2.4);
    sun.position.set(-0.5, 1, 0.3);
    this.scene.add(sun);
    this.camera = new THREE.PerspectiveCamera(55, 1, 0.5, 400000);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI * 0.95;
    this.follow = true;
    this.last = null;
    new ResizeObserver(() => this.resize()).observe(container);
  }

  resize() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  place(target, offset) {
    this.controls.target.copy(target);
    this.camera.position.copy(target).add(offset);
    this.last = target.clone();
  }

  // Move the orbit target with the drone, keeping the user's chosen view offset.
  track(target) {
    if (this.follow && this.last) {
      const d = target.clone().sub(this.last);
      this.controls.target.add(d);
      this.camera.position.add(d);
    }
    this.last = target.clone();
  }

  render() {
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}

// A quadrotor in body FLU mapped to Y-up (forward +x, up +y, left -z); scaled with camera distance.
function makeDrone(color) {
  const g = new THREE.Group();
  const mat = new THREE.MeshLambertMaterial({ color });
  const dark = new THREE.MeshLambertMaterial({ color: 0x222222 });
  g.add(new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.15, 0.35), mat));
  for (const [x, z] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.05, 0.06), dark);
    arm.position.set(x * 0.25, 0, z * 0.25);
    arm.rotation.y = Math.atan2(-z, x);
    const rotor = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.02, 20), mat);
    rotor.position.set(x * 0.5, 0.06, z * 0.5);
    g.add(arm, rotor);
  }
  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.3, 12), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  nose.rotation.z = -Math.PI / 2;
  nose.position.x = 0.4;
  g.add(nose);
  // A halo so the drone stays findable from far away.
  const halo = new THREE.Mesh(new THREE.SphereGeometry(0.9, 16, 12), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.18, depthWrite: false }));
  g.add(halo);
  return g;
}

function scaleToCamera(obj, camera, frac = 0.025) {
  obj.scale.setScalar(Math.max(1, obj.position.distanceTo(camera.position) * frac));
}

function makeLine(points, color, opts = {}) {
  const geo = new THREE.BufferGeometry().setFromPoints(points);
  const mat = opts.dashed
    ? new THREE.LineDashedMaterial({ color, dashSize: opts.dash || 20, gapSize: opts.dash || 20, transparent: true, opacity: opts.opacity ?? 1 })
    : new THREE.LineBasicMaterial({ color, transparent: true, opacity: opts.opacity ?? 1 });
  const line = new THREE.Line(geo, mat);
  if (opts.dashed) line.computeLineDistances();
  line.frustumCulled = false;
  return line;
}

// Positions with nulls (no estimate yet) carried forward so trails stay continuous.
function vectors(arr) {
  let prev = arr.find((p) => p && p.every((v) => v != null)) || [0, 0, 0];
  return arr.map((p) => {
    if (p && p.every((v) => v != null)) prev = p;
    return enu(prev);
  });
}

const GREEN = new THREE.Color("#2ecc71"), RED = new THREE.Color("#ff5a36"), BLUE = new THREE.Color("#3b8cff");
const MAGENTA = new THREE.Color("#e040fb"), GREY = new THREE.Color("#bbbbbb");
// "Agrees" means within 3 sigma of the suite's echo noise (0.05 m + 1 % of range); the colour
// saturates FULL_M beyond that.
const FULL_M = 10;
const agreeBand = (range) => 3 * (0.05 + 0.01 * range);

// Colour by measured - predicted range: green agrees, red shorter (something the map lacks),
// blue longer (the map has something that is not there, or the estimate is off).
function beamColor(measured, predicted, out) {
  if (measured == null) return out.copy(GREY), 0.16;
  if (predicted == null) return out.copy(MAGENTA), 0.95;
  const r = measured - predicted;
  const a = Math.min(1, Math.max(0, (Math.abs(r) - agreeBand(predicted)) / FULL_M));
  return out.copy(GREEN).lerp(r < 0 ? RED : BLUE, a), 0.95;
}

class Beams {
  constructor(n) {
    this.n = n;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 6), 3));
    geo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * 8), 4));
    this.lines = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false }));
    this.lines.frustumCulled = false;
    const pgeo = new THREE.BufferGeometry();
    pgeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    pgeo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * 4), 4));
    this.hits = new THREE.Points(pgeo, new THREE.PointsMaterial({ size: 5, sizeAttenuation: false, vertexColors: true, transparent: true, depthWrite: false }));
    this.hits.frustumCulled = false;
    this.group = new THREE.Group().add(this.lines, this.hits);
  }

  // origin: Vector3 (Y-up), q: body->world Quaternion (Y-up), dirs: body FLU unit vectors.
  update(origin, q, dirs, measured, predicted, maxRange) {
    const pos = this.lines.geometry.attributes.position.array, col = this.lines.geometry.attributes.color.array;
    const hp = this.hits.geometry.attributes.position.array, hc = this.hits.geometry.attributes.color.array;
    const d = new THREE.Vector3(), c = new THREE.Color();
    for (let b = 0; b < this.n; b++) {
      const m = measured?.[b] ?? null, p = predicted?.[b] ?? null;
      const len = m ?? maxRange;
      enu(dirs[b], d).applyQuaternion(q).multiplyScalar(len).add(origin);
      pos.set([origin.x, origin.y, origin.z, d.x, d.y, d.z], b * 6);
      const alpha = beamColor(m, p, c);
      col.set([c.r, c.g, c.b, alpha * 0.5, c.r, c.g, c.b, alpha], b * 8);
      hp.set([d.x, d.y, d.z], b * 3);
      hc.set([c.r, c.g, c.b, m == null ? 0 : 1], b * 4);
    }
    for (const g of [this.lines.geometry, this.hits.geometry]) {
      g.attributes.position.needsUpdate = true;
      g.attributes.color.needsUpdate = true;
    }
  }
}

// ---------- sampling ----------

function bisect(ts, t) {
  let lo = 0, hi = ts.length - 1;
  if (t <= ts[0]) return 0;
  if (t >= ts[hi]) return hi;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    ts[mid] <= t ? (lo = mid) : (hi = mid);
  }
  return lo;
}

function lerpPos(arr, i, f, out) {
  const a = arr[i], b = arr[Math.min(i + 1, arr.length - 1)];
  if (!a || a[0] == null) return null;
  if (!b || b[0] == null) return enu(a, out);
  return out.set(a[0] + (b[0] - a[0]) * f, a[2] + (b[2] - a[2]) * f, -(a[1] + (b[1] - a[1]) * f));
}

// ---------- app ----------

async function main() {
  const replays = await listReplays();
  const params = new URLSearchParams(location.search);
  const id = params.get("replay") || replays[0];
  const picker = $("picker");
  for (const r of id && !replays.includes(id) ? [id, ...replays] : replays) picker.add(new Option(r, r, false, r === id));
  picker.onchange = () => (location.search = `?replay=${encodeURIComponent(picker.value)}`);
  if (!id) return status("no replays in data/replays: run replay/export_sample.py");

  const base = `/replays/${id.split("/").map(encodeURIComponent).join("/")}`;
  status(`loading ${id}…`);
  const rj = await fetch(`${base}/replay.json`);
  if (!rj.ok) return status(`cannot load ${base}/replay.json (${rj.status})`);
  const R = await rj.json();
  const [mapMesh, truthMesh] = await Promise.all([loadMesh(`${base}/map.glb`, MAP_RAMP), loadMesh(`${base}/truth.glb`, TRUTH_RAMP)]);
  $("info").textContent = `${R.experiment} · ${R.scenario} · ${R.world} · ${R.run_id}`;
  document.title = `replay · ${R.experiment} · ${R.run_id}`;

  const left = new View($("left"));
  const right = new View($("right"));
  left.scene.add(mapMesh);
  right.scene.add(truthMesh);

  const truthV = vectors(R.truth_p), estV = vectors(R.est_p), planV = R.planned_p.map((p) => enu(p));
  const nb = R.echo.dirs_body.length;

  // Left: what the drone believes.
  const estDroneL = makeDrone(0xff4d6d);
  const beamsL = new Beams(nb);
  const estTrailL = makeLine(estV, 0xff4d6d);
  left.scene.add(estDroneL, beamsL.group, estTrailL);

  // Right: what actually happened.
  const truthDrone = makeDrone(0xffffff), estDroneR = makeDrone(0xff4d6d);
  const truthAll = makeLine(truthV, 0xffffff, { opacity: 0.25 });
  const truthTrail = makeLine(truthV, 0xffffff);
  const planLine = makeLine(planV, 0xffd23f, { dashed: true, dash: 8, opacity: 0.9 });
  const estTrailR = makeLine(estV, 0xff4d6d);
  const link = makeLine([new THREE.Vector3(), new THREE.Vector3()], 0xff4d6d, { opacity: 0.9 });
  const beamsR = new Beams(nb);
  beamsR.group.visible = false;
  right.scene.add(truthDrone, estDroneR, truthAll, truthTrail, planLine, estTrailR, link, beamsR.group);

  const chart = new Chart($("chart"), R, (t) => seek(t));

  // Initial views: behind and above the start, looking down the route.
  const p0 = truthV[0], dir = truthV[Math.min(50, truthV.length - 1)].clone().sub(p0).setY(0);
  if (dir.lengthSq() < 1) dir.set(1, 0, 0);
  const off = dir.normalize().multiplyScalar(-160).add(new THREE.Vector3(0, 90, 0));
  left.place(estV[0], off);
  right.place(truthV[0], off.clone().multiplyScalar(2.5));

  const t0 = R.t[0], t1 = R.t.at(-1);
  let time = t0, playing = false, lastFrame = performance.now();
  const scrub = $("scrub");
  scrub.min = t0;
  scrub.max = t1;
  scrub.step = (t1 - t0) / 5000;

  const setPlaying = (p) => {
    playing = p && time < t1;
    $("play").textContent = playing ? "❚❚" : "▶";
  };
  const seek = (t) => {
    time = Math.min(t1, Math.max(t0, t));
    draw();
  };
  $("play").onclick = () => {
    if (time >= t1) time = t0;
    setPlaying(!playing);
  };
  scrub.oninput = () => seek(+scrub.value);
  $("logScale").onchange = (e) => chart.setLog(e.target.checked);
  $("trueBeams").onchange = (e) => (beamsR.group.visible = e.target.checked);
  $("followTruth").onchange = (e) => (right.follow = e.target.checked);
  addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" && e.target.type !== "range" && e.target.type !== "checkbox") return;
    if (e.code === "Space") { e.preventDefault(); $("play").click(); }
    if (e.code === "ArrowRight") seek(time + 1);
    if (e.code === "ArrowLeft") seek(time - 1);
  });

  const qa = new THREE.Quaternion(), qb = new THREE.Quaternion(), q = new THREE.Quaternion();
  const pT = new THREE.Vector3(), pE = new THREE.Vector3();
  const readout = $("readout");

  function draw() {
    const i = bisect(R.t, time);
    const f = i + 1 < R.t.length ? Math.min(1, Math.max(0, (time - R.t[i]) / (R.t[i + 1] - R.t[i]))) : 0;
    const hasTruth = lerpPos(R.truth_p, i, f, pT) != null;
    const hasEst = lerpPos(R.est_p, i, f, pE) != null;
    enuQuat(R.truth_q[i], qa);
    enuQuat(R.truth_q[Math.min(i + 1, R.t.length - 1)], qb);
    q.slerpQuaternions(qa, qb, f);

    // Echo frame: the latest scan at or before now. Algorithms report position only, so both
    // drones use the true attitude.
    const e = bisect(R.echo.t, time);
    const meas = R.echo.measured[e], pred = R.echo.predicted[e];

    estDroneL.visible = beamsL.group.visible = estDroneR.visible = link.visible = hasEst;
    if (hasEst) {
      estDroneL.position.copy(pE);
      estDroneL.quaternion.copy(q);
      beamsL.update(pE, q, R.echo.dirs_body, meas, pred, R.echo.max_range);
      estDroneR.position.copy(pE);
      estDroneR.quaternion.copy(q);
      left.track(pE);
    }
    if (hasTruth) {
      truthDrone.position.copy(pT);
      truthDrone.quaternion.copy(q);
      if (beamsR.group.visible) beamsR.update(pT, q, R.echo.dirs_body, meas, pred, R.echo.max_range);
      right.track(pT);
    }
    if (hasEst && hasTruth) {
      link.geometry.attributes.position.array.set([pT.x, pT.y, pT.z, pE.x, pE.y, pE.z]);
      link.geometry.attributes.position.needsUpdate = true;
    }
    for (const l of [estTrailL, estTrailR, truthTrail]) l.geometry.setDrawRange(0, i + 1);

    chart.draw(time);
    scrub.value = time;
    $("clock").textContent = `${(time - t0).toFixed(1)} / ${(t1 - t0).toFixed(0)} s`;

    let agree = 0, seen = 0;
    for (let b = 0; b < nb; b++) {
      if (meas?.[b] == null) continue;
      seen++;
      if (pred?.[b] != null && Math.abs(meas[b] - pred[b]) <= agreeBand(pred[b])) agree++;
    }
    readout.innerHTML =
      SERIES.map((s) => `<span><i style="background:${s.color}"></i>${s.label} <b>${fmtM(R.metrics[s.key]?.[i])}</b></span>`).join("") +
      `<span>beams agreeing with map <b>${agree}/${seen}</b> (${nb - seen} no echo)</span>`;
  }

  function frame(now) {
    const dt = Math.min(0.1, (now - lastFrame) / 1000);
    lastFrame = now;
    if (playing) {
      time += dt * +$("speed").value;
      if (time >= t1) { time = t1; setPlaying(false); }
      draw();
    }
    for (const [v, drones] of [[left, [estDroneL]], [right, [truthDrone, estDroneR]]]) {
      for (const d of drones) scaleToCamera(d, v.camera);
      v.render();
    }
    requestAnimationFrame(frame);
  }

  draw();
  status("ready · Space play/pause · ←/→ step 1 s · click chart to seek");
  requestAnimationFrame(frame);
}

main().catch((e) => {
  console.error(e);
  status(`error: ${e.message}`);
});
