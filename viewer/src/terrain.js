import * as THREE from "three";

// Natural terrain from slippy-map tiles: Terrarium elevation PNGs + satellite imagery.
// Same local frame as the city: x = east, y = up (0 = height at the centre), z = south.
const R = 6378137;

function mercatorPx(lat, lon, z) {
  const n = 2 ** z * 256;
  const φ = THREE.MathUtils.degToRad(lat);
  return [((lon + 180) / 360) * n, ((1 - Math.asinh(Math.tan(φ)) / Math.PI) / 2) * n];
}

async function mosaic(base, kind, ext, r, onTile) {
  const cols = r.x1 - r.x0 + 1, rows = r.y1 - r.y0 + 1;
  const canvas = document.createElement("canvas");
  canvas.width = cols * 256; canvas.height = rows * 256;
  const ctx = canvas.getContext("2d", { willReadFrequently: kind === "elev" });
  const jobs = [];
  for (let x = r.x0; x <= r.x1; x++) for (let y = r.y0; y <= r.y1; y++) {
    jobs.push((async () => {
      const img = new Image();
      img.src = `${base}/${kind}/${x}_${y}.${ext}`;
      await img.decode();
      ctx.drawImage(img, (x - r.x0) * 256, (y - r.y0) * 256);
      onTile();
    })());
  }
  await Promise.all(jobs);
  return canvas;
}

export async function loadTerrain(scene, manifest, base, onProgress, step = 15) {
  const { elev, img, lat, lon, radius } = manifest;
  const total = (elev.x1 - elev.x0 + 1) * (elev.y1 - elev.y0 + 1) + (img.x1 - img.x0 + 1) * (img.y1 - img.y0 + 1);
  let done = 0;
  const tick = () => onProgress?.(++done, total);
  const [elevCanvas, imgCanvas] = await Promise.all([
    mosaic(base, "elev", "png", elev, tick),
    mosaic(base, "img", "jpg", img, tick),
  ]);

  const ew = elevCanvas.width, eh = elevCanvas.height;
  const px = elevCanvas.getContext("2d").getImageData(0, 0, ew, eh).data;
  const heightPx = (x, y) => {
    const i = 4 * (Math.min(eh - 1, Math.max(0, y)) * ew + Math.min(ew - 1, Math.max(0, x)));
    return px[i] * 256 + px[i + 1] + px[i + 2] / 256 - 32768;
  };
  const sampleHeight = (fx, fy) => { // bilinear
    const x = Math.floor(fx), y = Math.floor(fy), tx = fx - x, ty = fy - y;
    return (heightPx(x, y) * (1 - tx) + heightPx(x + 1, y) * tx) * (1 - ty) +
           (heightPx(x, y + 1) * (1 - tx) + heightPx(x + 1, y + 1) * tx) * ty;
  };

  const degPerM = 180 / (Math.PI * R);
  const cosLat = Math.cos(THREE.MathUtils.degToRad(lat));
  const n = Math.round((2 * radius) / step);
  const geom = new THREE.PlaneGeometry(n * step, n * step, n, n).rotateX(-Math.PI / 2);
  const pos = geom.getAttribute("position"), uv = geom.getAttribute("uv");
  for (let i = 0; i < pos.count; i++) {
    const vLat = lat - pos.getZ(i) * degPerM, vLon = lon + (pos.getX(i) * degPerM) / cosLat;
    const [ex, ey] = mercatorPx(vLat, vLon, elev.z);
    pos.setY(i, sampleHeight(ex - elev.x0 * 256 - 0.5, ey - elev.y0 * 256 - 0.5));
    const [ix, iy] = mercatorPx(vLat, vLon, img.z);
    uv.setXY(i, (ix - img.x0 * 256) / imgCanvas.width, 1 - (iy - img.y0 * 256) / imgCanvas.height);
  }
  const [cx, cy] = mercatorPx(lat, lon, elev.z);
  const centerHeight = sampleHeight(cx - elev.x0 * 256, cy - elev.y0 * 256);
  geom.translate(0, -centerHeight, 0);
  geom.computeVertexNormals();
  geom.computeBoundingSphere();
  geom.computeBoundingBox();
  geom.computeBoundsTree();

  const texture = new THREE.CanvasTexture(imgCanvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  const ground = new THREE.Mesh(geom, new THREE.MeshStandardMaterial({ map: texture, roughness: 1 }));
  ground.receiveShadow = true;
  scene.add(ground);

  return { colliders: [ground], meshes: [], ground, manifest, fog: [2000, 14000], minHeight: geom.boundingBox.min.y };
}
