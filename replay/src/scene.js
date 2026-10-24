// three.js pieces shared by both 3D panels: terrain meshes, drones, trails, the echo beam fan and
// the camera rig with presets.
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { agreeBand } from "./summary.js";

// Replay JSON is ENU (x east, y north, z up); three.js is Y-up: (x, y, z) -> (x, z, -y).
export const enu = (p, out = new THREE.Vector3()) => out.set(p[0], p[2], -p[1]);
export const enuQuat = (q, out = new THREE.Quaternion()) => out.set(q[0], q[2], -q[1], q[3]);

// ---------- terrain ----------

// Tuned for a light page: mid-tone lows so white-ish UI and pale highs never merge with the sky, and
// enough value range that the coloured beams and the dark truth trail read on top. The map is a cool
// slate (a belief), the truth an earthy ramp (reality).
export const MAP_RAMP = ["#6b809d", "#8fa2bb", "#b6c4d6", "#d5dee9"];
export const TRUTH_RAMP = ["#6f835f", "#909b6b", "#b3a685", "#cfc9ba", "#ebe7de"];
export const SKY = 0xeef1f5;

// Trajectory colours, shared with the chart legends and layer chips.
export const COLORS = { truth: "#1f2937", planned: "#d97706", estimate: "#e11d48" };

export async function loadMesh(url, ramp) {
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
        float fw = fwidth(h);
        float line = 1.0 - smoothstep(0.0, 1.2, abs(fract(h - 0.5) - 0.5) / fw);
        // Fade lines out where they'd pack tighter than a few pixels, so far slopes don't go dark.
        line *= 1.0 - smoothstep(0.15, 0.45, fw);
        gl_FragColor.rgb *= 1.0 - 0.22 * line;`);
  };
  return m;
}

// ---------- view + camera rig ----------

export const CAMERA_MODES = ["follow", "top", "chase", "overview"];

export class View {
  constructor(container) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    container.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(SKY);
    this.scene.add(new THREE.HemisphereLight(0xf2f6ff, 0x6b6458, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 2.0);
    sun.position.set(-0.5, 1, 0.3);
    this.scene.add(sun);
    this.camera = new THREE.PerspectiveCamera(55, 1, 0.5, 400000);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI * 0.95;
    this.mode = "follow";
    this.last = null;
    this.bounds = new THREE.Box3();
    new ResizeObserver(() => this.resize()).observe(container);
  }

  resize() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  // Move camera and orbit target together so the view keeps its framing around a new point.
  retarget(target) {
    const d = target.clone().sub(this.controls.target);
    this.controls.target.add(d);
    this.camera.position.add(d);
    this.last = target.clone();
  }

  place(target, offset) {
    this.controls.target.copy(target);
    this.camera.position.copy(target).add(offset);
    this.last = target.clone();
  }

  setMode(mode, target) {
    this.mode = mode;
    const dist = Math.max(80, this.camera.position.distanceTo(this.controls.target));
    if (mode === "top") {
      this.controls.target.copy(target);
      this.camera.position.copy(target).add(new THREE.Vector3(0, THREE.MathUtils.clamp(dist, 400, 2000), 0.01));
    } else if (mode === "overview" && !this.bounds.isEmpty()) {
      const c = this.bounds.getCenter(new THREE.Vector3()), size = this.bounds.getSize(new THREE.Vector3());
      const r = Math.max(size.x, size.z, 200);
      this.controls.target.copy(c);
      this.camera.position.copy(c).add(new THREE.Vector3(r * 0.35, r * 0.9, r * 0.6));
    } else if (mode === "follow") {
      const off = this.camera.position.clone().sub(this.controls.target);
      if (off.y < dist * 0.2) off.y = dist * 0.5;
      this.place(target, off.setLength(Math.min(dist, 600)));
    }
    this.last = target.clone();
  }

  // Keep the camera on the drone according to the preset. q gives the heading for the chase cam.
  track(target, q) {
    if (this.mode === "chase") {
      const fwd = new THREE.Vector3(1, 0, 0).applyQuaternion(q).setY(0);
      if (fwd.lengthSq() < 1e-6) fwd.set(1, 0, 0);
      const dist = THREE.MathUtils.clamp(this.camera.position.distanceTo(this.controls.target), 15, 1500);
      const want = target.clone().addScaledVector(fwd.normalize(), -dist * 0.94).add(new THREE.Vector3(0, dist * 0.34, 0));
      this.camera.position.lerp(want, 0.12);
      this.controls.target.copy(target);
    } else if (this.mode !== "overview" && this.last) {
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

// ---------- drones and lines ----------

// A quadrotor in body FLU mapped to Y-up (forward +x, up +y, left -z).
export function makeDrone(color) {
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
  g.add(new THREE.Mesh(new THREE.SphereGeometry(0.9, 16, 12), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.18, depthWrite: false })));
  return g;
}

// Drones are ~1 m; scale them with camera distance so they stay visible from a kilometre up.
export function scaleToCamera(obj, camera, frac = 0.025) {
  obj.scale.setScalar(Math.max(1, obj.position.distanceTo(camera.position) * frac));
}

export const RADIUS_COLORS = { ok: "#0284c7", over: "#f59e0b", hmi: "#dc2626" };

// The method's reported 95 % horizontal radius: a flat disc with a rim at unit radius, scaled to metres
// per frame. Drawn over the terrain so it never hides inside a hill.
export function makeRadius() {
  const g = new THREE.Group();
  const flat = (geo) => geo.rotateX(-Math.PI / 2);
  const disc = new THREE.Mesh(flat(new THREE.CircleGeometry(1, 96)),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.14, depthWrite: false, depthTest: false, side: THREE.DoubleSide }));
  const rim = new THREE.Mesh(flat(new THREE.RingGeometry(0.97, 1, 128)),
    new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.95, depthWrite: false, depthTest: false, side: THREE.DoubleSide }));
  disc.renderOrder = rim.renderOrder = 5;
  g.add(disc, rim);
  g.visible = false;
  g.setColor = (c) => { disc.material.color.set(c); rim.material.color.set(c); };
  return g;
}

export function makeLine(points, color, opts = {}) {
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
export function vectors(arr) {
  let prev = arr.find((p) => p && p.every((v) => v != null)) || [0, 0, 0];
  return arr.map((p) => {
    if (p && p.every((v) => v != null)) prev = p;
    return enu(prev);
  });
}

// ---------- echo beams ----------

// Saturated mid-value hues so all five stay apart on light terrain and on the white heatmap; the
// grey for "no echo" is dark enough to show at low alpha.
export const BEAM_COLORS = { agree: "#16a34a", short: "#ea2a1f", long: "#2563eb", nohit: "#c026d3", miss: "#5b6472" };
const C = Object.fromEntries(Object.entries(BEAM_COLORS).map(([k, v]) => [k, new THREE.Color(v)]));

// "Agrees" means within 3 sigma of the suite's echo noise (agreeBand, in summary.js); colours
// saturate FULL_M beyond that.
export const FULL_M = 10;
export { agreeBand };

// Layer of one beam reading: "hit" (agrees with the map), "disagree" or "miss" (no echo).
export function beamLayer(measured, predicted) {
  if (measured == null) return "miss";
  if (predicted == null) return "disagree";
  return Math.abs(measured - predicted) <= agreeBand(predicted) ? "hit" : "disagree";
}

// Colour by measured - predicted range: green agrees, red shorter (something the map lacks),
// blue longer (the map has something that is not there, or the estimate is off), magenta when the
// map predicts no hit. Returns the colour into `out` and an alpha.
export function beamColor(measured, predicted, out) {
  if (measured == null) return [out.copy(C.miss), 0.28];
  if (predicted == null) return [out.copy(C.nohit), 0.95];
  const r = measured - predicted;
  const a = Math.min(1, Math.max(0, (Math.abs(r) - agreeBand(predicted)) / FULL_M));
  return [out.copy(C.agree).lerp(r < 0 ? C.short : C.long, a), 0.95];
}

export class Beams {
  constructor(n) {
    this.n = n;
    this.layers = { hit: true, disagree: true, miss: true };
    this.highlight = -1;
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
      enu(dirs[b], d).applyQuaternion(q).multiplyScalar(m ?? maxRange).add(origin);
      pos.set([origin.x, origin.y, origin.z, d.x, d.y, d.z], b * 6);
      let [, alpha] = beamColor(m, p, c);
      if (!this.layers[beamLayer(m, p)]) alpha = 0;
      if (this.highlight >= 0) alpha = b === this.highlight ? Math.max(alpha, 0.6) * 1.0 : alpha * 0.12;
      col.set([c.r, c.g, c.b, alpha * 0.5, c.r, c.g, c.b, alpha], b * 8);
      hp.set([d.x, d.y, d.z], b * 3);
      hc.set([c.r, c.g, c.b, m == null ? 0 : alpha && 1], b * 4);
    }
    for (const g of [this.lines.geometry, this.hits.geometry]) {
      g.attributes.position.needsUpdate = true;
      g.attributes.color.needsUpdate = true;
    }
  }
}

// Free GPU memory for everything under obj (used when switching runs in place).
export function disposeTree(obj) {
  obj.traverse((o) => {
    o.geometry?.dispose();
    for (const m of [o.material].flat()) m?.dispose();
  });
}

// Human label for a body-frame beam: elevation and azimuth (0 = forward, 90 = left).
export function beamLabel(dir) {
  const el = Math.round((Math.asin(Math.max(-1, Math.min(1, dir[2]))) * 180) / Math.PI);
  if (el <= -89) return "down";
  const az = Math.round(((Math.atan2(dir[1], dir[0]) * 180) / Math.PI + 360) % 360);
  return `el ${el}° az ${az}°`;
}
