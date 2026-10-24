import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";
import { loadTerrain } from "./terrain.js";
import { computeBoundsTree, disposeBoundsTree, acceleratedRaycast } from "three-mesh-bvh";

THREE.BufferGeometry.prototype.computeBoundsTree = computeBoundsTree;
THREE.BufferGeometry.prototype.disposeBoundsTree = disposeBoundsTree;
THREE.Mesh.prototype.raycast = acceleratedRaycast;

// World coordinates (meters): x = east, y = up (0 = ground level), z = south.
// 3D Tiles store ECEF positions in a Y-up glTF; we bake everything into this local frame.
function ecefToLocalMatrix(lat, lon) {
  const φ = THREE.MathUtils.degToRad(lat), λ = THREE.MathUtils.degToRad(lon);
  const a = 6378137.0, e2 = 6.69437999014e-3;
  const N = a / Math.sqrt(1 - e2 * Math.sin(φ) ** 2);
  const p0 = new THREE.Vector3(N * Math.cos(φ) * Math.cos(λ), N * Math.cos(φ) * Math.sin(λ), N * (1 - e2) * Math.sin(φ));
  const e = [-Math.sin(λ), Math.cos(λ), 0];
  const n = [-Math.sin(φ) * Math.cos(λ), -Math.sin(φ) * Math.sin(λ), Math.cos(φ)];
  const u = [Math.cos(φ) * Math.cos(λ), Math.cos(φ) * Math.sin(λ), Math.sin(φ)];
  // rows: x = east, y = up, z = -north
  const R = new THREE.Matrix4().set(
    e[0], e[1], e[2], 0,
    u[0], u[1], u[2], 0,
    -n[0], -n[1], -n[2], 0,
    0, 0, 0, 1,
  );
  const yUpToZUp = new THREE.Matrix4().makeRotationX(Math.PI / 2);
  return R.multiply(new THREE.Matrix4().makeTranslation(-p0.x, -p0.y, -p0.z)).multiply(yUpToZUp);
}

// Copy positions out of the (quantized) tile geometry into float32 local coordinates.
function bakeGeometry(src, matrix) {
  const pos = src.getAttribute("position");
  const out = new Float32Array(pos.count * 3);
  const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i).applyMatrix4(matrix);
    out[3 * i] = v.x; out[3 * i + 1] = v.y; out[3 * i + 2] = v.z;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(out, 3));
  if (src.index) g.setIndex(src.index.clone());
  return g;
}

export async function listWorlds() {
  const names = await (await fetch("/worlds/index.json")).json();
  return Promise.all(names.map(async (id) => ({ id, ...(await (await fetch(`/worlds/${id}/manifest.json`)).json()) })));
}

export async function loadWorld(scene, id, onProgress) {
  const base = `/worlds/${id}`;
  const manifest = await (await fetch(`${base}/manifest.json`)).json();
  if (manifest.type === "terrain") return loadTerrain(scene, manifest, base, onProgress);
  const toLocal = ecefToLocalMatrix(manifest.lat, manifest.lon);
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  const material = new THREE.MeshStandardMaterial({ color: 0xd9d4cc, flatShading: true, roughness: 0.9 });
  const roofMaterial = new THREE.MeshStandardMaterial({ color: 0xb5654f, flatShading: true, roughness: 0.8 });

  const meshes = [];
  let done = 0;
  await Promise.all(manifest.tiles.map(async (file) => {
    const gltf = await loader.loadAsync(`${base}/${file}`);
    gltf.scene.updateMatrixWorld(true);
    gltf.scene.traverse((o) => {
      if (!o.isMesh) return;
      const m = new THREE.Matrix4().multiplyMatrices(toLocal, o.matrixWorld);
      const geometry = bakeGeometry(o.geometry, m);
      meshes.push(new THREE.Mesh(geometry, material));
    });
    onProgress?.(++done, manifest.tiles.length);
  }));

  for (const mesh of meshes) {
    colorRoofs(mesh, material, roofMaterial);
    mesh.castShadow = mesh.receiveShadow = true;
  }

  // 3DBAG has buildings only, so derive terrain from where the buildings touch the ground.
  const ground = buildTerrain(meshes, manifest.radius * 2.4, 20);
  const shift = ground.userData.centerHeight;
  ground.geometry.translate(0, -shift, 0);
  ground.geometry.computeBoundsTree();
  scene.add(ground);
  for (const mesh of meshes) {
    mesh.geometry.translate(0, -shift, 0);
    mesh.geometry.computeBoundingSphere();
    mesh.geometry.computeBoundsTree();
    scene.add(mesh);
  }

  return { colliders: [...meshes, ground], meshes, ground, manifest, fog: [300, 3500], minHeight: -50 };
}

// Heightfield through the lowest building floor in each cell; empty cells (streets,
// parks, the river) are filled by diffusing from their neighbours.
function buildTerrain(meshes, size, cell) {
  const n = Math.round(size / cell);
  const half = (n * cell) / 2;
  const h = new Float32Array((n + 1) ** 2).fill(Infinity);
  for (const mesh of meshes) {
    const pos = mesh.geometry.getAttribute("position"), nor = mesh.geometry.getAttribute("normal");
    for (let i = 0; i < pos.count; i++) {
      if (nor.getY(i) > -0.9) continue; // only downward-facing floor faces
      const col = Math.round((pos.getX(i) + half) / cell), row = Math.round((pos.getZ(i) + half) / cell);
      if (col < 0 || row < 0 || col > n || row > n) continue;
      const k = row * (n + 1) + col;
      h[k] = Math.min(h[k], pos.getY(i));
    }
  }
  const known = h.map((v) => (Number.isFinite(v) ? 1 : 0));
  for (let missing = Infinity, iter = 0; missing > 0 && iter < 2000; iter++) {
    missing = 0;
    const next = h.slice();
    for (let r = 0; r <= n; r++) for (let c = 0; c <= n; c++) {
      const k = r * (n + 1) + c;
      if (known[k]) continue;
      let sum = 0, cnt = 0;
      for (const [dr, dc] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const rr = r + dr, cc = c + dc;
        if (rr < 0 || cc < 0 || rr > n || cc > n) continue;
        const v = h[rr * (n + 1) + cc];
        if (Number.isFinite(v)) { sum += v; cnt++; }
      }
      if (cnt) next[k] = sum / cnt; else missing++;
    }
    h.set(next);
  }

  const geom = new THREE.PlaneGeometry(n * cell, n * cell, n, n).rotateX(-Math.PI / 2);
  const pos = geom.getAttribute("position");
  for (let i = 0; i < pos.count; i++) {
    const col = Math.round((pos.getX(i) + half) / cell), row = Math.round((pos.getZ(i) + half) / cell);
    pos.setY(i, h[row * (n + 1) + col] - 0.05);
  }
  geom.computeVertexNormals();
  const mesh = new THREE.Mesh(geom, new THREE.MeshStandardMaterial({ color: 0x7d8a6e, roughness: 1 }));
  mesh.receiveShadow = true;
  mesh.userData.centerHeight = h[(n / 2 | 0) * (n + 1) + (n / 2 | 0)];
  return mesh;
}

// Split each tile into walls / roofs by face orientation so the city reads at a glance.
function colorRoofs(mesh, wallMat, roofMat) {
  const g = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry;
  g.computeVertexNormals();
  const n = g.getAttribute("normal");
  const walls = [], roofs = [];
  for (let i = 0; i < n.count; i += 3) (n.getY(i) > 0.5 ? roofs : walls).push(i);
  const order = new Float32Array(n.count * 3);
  const pos = g.getAttribute("position");
  let k = 0;
  for (const list of [walls, roofs]) {
    for (const i of list) for (let j = 0; j < 3; j++) { order[k++] = pos.getX(i + j); order[k++] = pos.getY(i + j); order[k++] = pos.getZ(i + j); }
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.BufferAttribute(order, 3));
  out.computeVertexNormals();
  out.addGroup(0, walls.length * 3, 0);
  out.addGroup(walls.length * 3, roofs.length * 3, 1);
  mesh.geometry = out;
  mesh.material = [wallMat, roofMat];
}
