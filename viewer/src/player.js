import * as THREE from "three";

// Capsule character controller against BVH colliders (after the three-mesh-bvh
// characterMovement example). position = feet; yaw/pitch drive the camera.
const GRAVITY = -9.81 * 2;
const RADIUS = 0.35;
const HEIGHT = 1.8;
export const EYE = 1.65;

const box = new THREE.Box3();
const segment = new THREE.Line3();
const triPoint = new THREE.Vector3();
const capPoint = new THREE.Vector3();
const delta = new THREE.Vector3();
const move = new THREE.Vector3();

export class Player {
  constructor(colliders) {
    this.colliders = colliders;
    this.position = new THREE.Vector3();
    this.velocity = new THREE.Vector3();
    this.yaw = 0;   // radians, 0 = looking north, positive = turning right (compass heading)
    this.pitch = 0;
    this.mode = "walk";
    this.onGround = false;
    this.walkSpeed = 1.6; this.runSpeed = 6;
    this.flySpeed = 15; this.flyFastSpeed = 60;
  }

  forward() { return new THREE.Vector3(Math.sin(this.yaw), 0, -Math.cos(this.yaw)); }
  right() { return new THREE.Vector3(Math.cos(this.yaw), 0, Math.sin(this.yaw)); }
  lookDir() {
    return this.forward().multiplyScalar(Math.cos(this.pitch)).setY(Math.sin(this.pitch));
  }

  // input: { forward, right, up in [-1,1], fast, jump }
  update(dt, input) {
    move.set(0, 0, 0)
      .addScaledVector(this.forward(), input.forward)
      .addScaledVector(this.right(), input.right);
    if (move.lengthSq() > 1) move.normalize();

    if (this.mode === "walk") {
      const speed = input.fast ? this.runSpeed : this.walkSpeed;
      this.velocity.x = move.x * speed;
      this.velocity.z = move.z * speed;
      if (this.onGround) this.velocity.y = input.jump ? 5 : GRAVITY * dt;
      else this.velocity.y += GRAVITY * dt;
    } else {
      const speed = input.fast ? this.flyFastSpeed : this.flySpeed;
      if (input.forward) move.copy(this.lookDir()).multiplyScalar(input.forward).addScaledVector(this.right(), input.right);
      move.y += input.up;
      if (move.lengthSq() > 1) move.normalize();
      this.velocity.copy(move).multiplyScalar(speed);
    }

    this.position.addScaledVector(this.velocity, dt);
    this.collide(dt);
  }

  collide(dt) {
    segment.start.copy(this.position).y += HEIGHT - RADIUS;
    segment.end.copy(this.position).y += RADIUS;
    const before = segment.end.clone();

    for (let iter = 0; iter < 2; iter++) {
      box.makeEmpty().expandByPoint(segment.start).expandByPoint(segment.end);
      box.min.addScalar(-RADIUS); box.max.addScalar(RADIUS);
      for (const mesh of this.colliders) {
        const bvh = mesh.geometry.boundsTree;
        const sphere = mesh.geometry.boundingSphere;
        if (sphere && sphere.distanceToPoint(segment.end) > HEIGHT + 2) continue;
        bvh.shapecast({
          intersectsBounds: (b) => b.intersectsBox(box),
          intersectsTriangle: (tri) => {
            const d = tri.closestPointToSegment(segment, triPoint, capPoint);
            if (d < RADIUS) {
              const depth = RADIUS - d;
              const dir = capPoint.sub(triPoint).normalize();
              segment.start.addScaledVector(dir, depth);
              segment.end.addScaledVector(dir, depth);
            }
          },
        });
      }
    }

    delta.subVectors(segment.end, before);
    this.onGround = delta.y > Math.abs(dt * this.velocity.y * 0.25);
    this.position.add(delta);
    if (this.onGround) this.velocity.y = 0;
    else if (delta.lengthSq() > 1e-10) {
      delta.normalize();
      this.velocity.addScaledVector(delta, -delta.dot(this.velocity));
    }
  }
}
