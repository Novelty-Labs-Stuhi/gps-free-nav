import * as THREE from "three";
import { Sky } from "three/examples/jsm/objects/Sky.js";
import { loadWorld, listWorlds } from "./world.js";
import { Player, EYE } from "./player.js";

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
document.body.prepend(renderer.domElement);

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xc9d6e3, 300, 3500);
const camera = new THREE.PerspectiveCamera(70, innerWidth / innerHeight, 0.1, 30000);

const sky = new Sky();
sky.scale.setScalar(25000);
const sunDir = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(55), THREE.MathUtils.degToRad(210));
sky.material.uniforms.sunPosition.value.copy(sunDir);
sky.material.uniforms.turbidity.value = 4;
scene.add(sky);

scene.add(new THREE.HemisphereLight(0xdde8ff, 0x8a8f80, 1.8));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -120, right: 120, top: 120, bottom: -120, near: 1, far: 1500 });
sun.shadow.bias = -0.0005;
scene.add(sun, sun.target);

addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

const status = document.getElementById("status");
// ?world=<id> picks a folder in public/worlds; the dropdown just reloads with it.
const worlds = await listWorlds();
const worldId = new URLSearchParams(location.search).get("world") ?? (worlds.find((w) => w.type === "terrain") ?? worlds[0]).id;
const picker = document.getElementById("world");
picker.innerHTML = worlds.map((w) => `<option value="${w.id}" ${w.id === worldId ? "selected" : ""}>${w.name}</option>`).join("");
picker.addEventListener("change", () => { location.search = `?world=${picker.value}`; });
picker.addEventListener("keydown", (e) => e.preventDefault());

const world = await loadWorld(scene, worldId, (done, total) => { status.textContent = `loading tiles ${done}/${total}…`; });
scene.fog.near = world.fog[0];
scene.fog.far = world.fog[1];
document.getElementById("credit").textContent = world.manifest.attribution;
const player = new Player(world.colliders);

// Third-person body.
const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.35, 1.1, 4, 12), new THREE.MeshStandardMaterial({ color: 0x2f9e44 }));
body.castShadow = true;
scene.add(body);

// Spawn on open ground near the centre: spiral out until a downward ray hits the ground plane.
const ray = new THREE.Raycaster();
ray.firstHitOnly = true;
function groundAt(x, z) {
  ray.set(new THREE.Vector3(x, 10000, z), new THREE.Vector3(0, -1, 0));
  ray.far = Infinity;
  return ray.intersectObjects(world.colliders)[0];
}
function spawn() {
  for (let i = 0; i < 2000; i++) {
    const a = i * 0.5, r = i * 1.5;
    const hit = groundAt(Math.cos(a) * r, Math.sin(a) * r);
    if (hit?.object === world.ground) { player.position.copy(hit.point); player.velocity.set(0, 0, 0); return; }
  }
}
spawn();

// --- input -------------------------------------------------------------------
const keys = new Set();
let thirdPerson = false;
addEventListener("keydown", (e) => {
  keys.add(e.code);
  if (e.repeat) return;
  if (e.code === "KeyF") player.mode = player.mode === "walk" ? "fly" : "walk";
  if (e.code === "KeyC") thirdPerson = !thirdPerson;
  if (e.code === "KeyH") { const h = document.getElementById("help"); h.hidden = !h.hidden; }
});
addEventListener("keyup", (e) => keys.delete(e.code));
addEventListener("blur", () => keys.clear());
renderer.domElement.addEventListener("click", () => renderer.domElement.requestPointerLock());
document.addEventListener("mousemove", (e) => {
  if (document.pointerLockElement !== renderer.domElement) return;
  player.yaw += e.movementX * 0.0022;
  player.pitch = THREE.MathUtils.clamp(player.pitch - e.movementY * 0.0022, -1.5, 1.5);
});
const axis = (a, b) => (keys.has(a) ? 1 : 0) - (keys.has(b) ? 1 : 0);

// --- loop --------------------------------------------------------------------
const clock = new THREE.Clock();
let fps = 60;
renderer.setAnimationLoop(() => {
  const rawDt = clock.getDelta();
  const dt = Math.min(rawDt, 0.05);
  fps += (1 / Math.max(rawDt, 1e-3) - fps) * 0.05;
  const input = {
    forward: axis("KeyW", "KeyS"),
    right: axis("KeyD", "KeyA"),
    up: axis("Space", "KeyQ"),
    jump: keys.has("Space"),
    fast: keys.has("ShiftLeft") || keys.has("ShiftRight"),
  };
  for (let i = 0; i < 4; i++) player.update(dt / 4, input);
  if (player.position.y < world.minHeight - 100) spawn(); // fell off the edge of the map

  const eye = player.position.clone().setY(player.position.y + EYE);
  if (thirdPerson) {
    camera.position.copy(eye).addScaledVector(player.lookDir(), -7).y += 1.5;
    camera.lookAt(eye);
  } else {
    camera.position.copy(eye);
    camera.lookAt(eye.clone().add(player.lookDir()));
  }
  body.visible = thirdPerson;
  body.position.copy(player.position).y += 0.9;
  body.rotation.y = -player.yaw;

  sun.position.copy(player.position).addScaledVector(sunDir, 600);
  sun.target.position.copy(player.position);

  const p = player.position;
  status.textContent =
    `${player.mode}  E ${p.x.toFixed(1)}  N ${(-p.z).toFixed(1)}  h ${p.y.toFixed(1)} m` +
    `  hdg ${((THREE.MathUtils.radToDeg(player.yaw) % 360 + 360) % 360).toFixed(0)}°  ${fps.toFixed(0)} fps`;
  renderer.render(scene, camera);
});

// Handle for console experiments / future sensor code: window.sim.raycast(origin, dir)
window.sim = {
  THREE, scene, camera, player, world,
  raycast(origin, dir, far = 500) {
    ray.set(origin, dir.clone().normalize());
    ray.far = far;
    return ray.intersectObjects(world.colliders)[0] ?? null;
  },
};
