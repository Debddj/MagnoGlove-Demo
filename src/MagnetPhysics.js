import * as CANNON from 'cannon-es';

export class MagnetPhysics {
  constructor() {
    this.world = new CANNON.World({
      gravity: new CANNON.Vec3(0, -9.82, 0)
    });

    this.floorMaterial = new CANNON.Material('floor');
    this.objectMaterial = new CANNON.Material('object');

    const contactMaterial = new CANNON.ContactMaterial(this.floorMaterial, this.objectMaterial, {
      friction: 0.8,
      restitution: 0.15
    });
    this.world.addContactMaterial(contactMaterial);

    // Object-object contact for stacking
    const objObj = new CANNON.ContactMaterial(this.objectMaterial, this.objectMaterial, {
      friction: 0.4,
      restitution: 0.2
    });
    this.world.addContactMaterial(objObj);

    this.objects = [];

    // Per-hand magnet state: { target, state, strength }
    this.magnets = {
      Left:  { target: null, state: 'OFF', strength: 0 },
      Right: { target: null, state: 'OFF', strength: 0 }
    };

    this.grabbedCount = 0;

    this.createBounds();
    this.spawnObjects();
  }

  createBounds() {
    // Floor
    const floorBody = new CANNON.Body({ mass: 0, material: this.floorMaterial });
    floorBody.addShape(new CANNON.Plane());
    floorBody.quaternion.setFromAxisAngle(new CANNON.Vec3(1, 0, 0), -Math.PI / 2);
    floorBody.position.set(0, -3.5, 0);
    this.world.addBody(floorBody);

    // Walls: keep objects in a reasonable space
    const walls = [
      { pos: [0, 0, -8], rot: [0, 0, 0] },       // back
      { pos: [0, 0, 5],  rot: [Math.PI, 0, 0] },  // front
      { pos: [-12, 0, 0], rot: [0, Math.PI/2, 0] }, // left
      { pos: [12, 0, 0],  rot: [0, -Math.PI/2, 0] }, // right
      { pos: [0, 15, 0],  rot: [Math.PI/2, 0, 0] }, // ceiling
    ];
    walls.forEach(w => {
      const body = new CANNON.Body({ mass: 0 });
      body.addShape(new CANNON.Plane());
      if (w.rot[0]) body.quaternion.setFromAxisAngle(new CANNON.Vec3(1,0,0), w.rot[0]);
      if (w.rot[1]) body.quaternion.setFromAxisAngle(new CANNON.Vec3(0,1,0), w.rot[1]);
      body.position.set(...w.pos);
      this.world.addBody(body);
    });
  }

  spawnObjects() {
    const objDefs = [
      // Small objects
      { mass: 0.15, shape: 'sphere', size: [0.15], label: 'Screw' },
      { mass: 0.2,  shape: 'box',    size: [0.12, 0.12, 0.12], label: 'Nut' },
      { mass: 0.25, shape: 'sphere', size: [0.18], label: 'Ball Bearing' },
      { mass: 0.1,  shape: 'box',    size: [0.08, 0.08, 0.3], label: 'Nail' },
      { mass: 0.18, shape: 'sphere', size: [0.14], label: 'Rivet' },
      // Medium objects
      { mass: 0.5,  shape: 'sphere', size: [0.3], label: 'Steel Sphere' },
      { mass: 0.6,  shape: 'box',    size: [0.35, 0.35, 0.35], label: 'Iron Cube' },
      { mass: 0.4,  shape: 'box',    size: [0.15, 0.6, 0.15], label: 'Rod' },
      { mass: 0.7,  shape: 'sphere', size: [0.35], label: 'Chrome Ball' },
      { mass: 0.55, shape: 'box',    size: [0.4, 0.25, 0.4], label: 'Plate' },
      // Large objects
      { mass: 1.5,  shape: 'sphere', size: [0.55], label: 'Cannon Ball' },
      { mass: 2.0,  shape: 'box',    size: [0.5, 0.5, 0.5], label: 'Heavy Cube' },
      { mass: 1.2,  shape: 'sphere', size: [0.45], label: 'Lead Sphere' },
      { mass: 1.8,  shape: 'box',    size: [0.6, 0.35, 0.6], label: 'Anvil Block' },
      { mass: 2.5,  shape: 'sphere', size: [0.65], label: 'Wrecking Ball' },
    ];

    objDefs.forEach((def, i) => {
      let shape;
      if (def.shape === 'sphere') shape = new CANNON.Sphere(def.size[0]);
      else shape = new CANNON.Box(new CANNON.Vec3(def.size[0]/2, def.size[1]/2, def.size[2]/2));

      const body = new CANNON.Body({
        mass: def.mass,
        shape,
        material: this.objectMaterial,
        linearDamping: 0.4,
        angularDamping: 0.4
      });

      // Spread across the floor
      const x = (Math.random() - 0.5) * 14;
      const z = (Math.random() - 0.5) * 6 - 1;
      body.position.set(x, -3 + def.size[0] + Math.random() * 2, z);

      this.world.addBody(body);
      this.objects.push({ id: i, body, def, grabbed: false });
    });
  }

  /**
   * Update magnet states from hand data array
   * @param {Array} hands - [{ handedness, gesture, palmWorld }]
   */
  updateFromHands(hands) {
    // Reset both
    this.magnets.Left.target = null;
    this.magnets.Left.state = 'OFF';
    this.magnets.Right.target = null;
    this.magnets.Right.state = 'OFF';

    hands.forEach(h => {
      const m = this.magnets[h.handedness];
      if (!m) return;
      m.target = h.palmWorld;
      if (h.gesture === 'FIST') m.state = 'ON';
      else if (h.gesture === 'PINCH') m.state = 'PRECISION';
      else m.state = 'OFF';
    });
  }

  step(dt) {
    // Smooth ramp per hand
    ['Left', 'Right'].forEach(side => {
      const m = this.magnets[side];
      let target = 0;
      if (m.state === 'ON') target = 1.0;
      else if (m.state === 'PRECISION') target = 0.35;
      m.strength += (target - m.strength) * Math.min(dt * 6, 1);
    });

    this.grabbedCount = 0;

    // Apply forces from each active hand
    this.objects.forEach(obj => {
      obj.grabbed = false;
      let totalForce = new CANNON.Vec3(0, 0, 0);

      ['Left', 'Right'].forEach(side => {
        const m = this.magnets[side];
        if (!m.target || m.strength < 0.03) return;

        const tx = m.target.x;
        const ty = m.target.y;
        const tz = m.target.z;
        const body = obj.body;

        const dx = tx - body.position.x;
        const dy = ty - body.position.y;
        const dz = tz - body.position.z;
        const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);

        if (dist < 0.15) return; // too close, skip

        const maxRange = m.state === 'ON' ? 12 : 6;
        if (dist > maxRange) return;

        if (dist < 1.2) {
          // Grabbed — strong centering + damping
          obj.grabbed = true;
          body.velocity.scale(0.85, body.velocity);
          const pull = 40 * m.strength * body.mass;
          totalForce.x += (dx / dist) * pull;
          totalForce.y += (dy / dist) * pull;
          totalForce.z += (dz / dist) * pull;
        } else {
          // Long range attraction — inverse-square-ish
          const pull = (150 * m.strength * body.mass) / (dist * dist * 0.3 + 0.5);
          totalForce.x += (dx / dist) * pull;
          totalForce.y += ((dy + 1.5) / dist) * pull; // bias upward
          totalForce.z += (dz / dist) * pull;
        }
      });

      if (totalForce.length() > 0.01) {
        obj.body.applyForce(totalForce, obj.body.position);
        if (obj.grabbed) this.grabbedCount++;
      }
    });

    this.world.step(1/60, dt, 3);
  }

  getObjectsInfo() {
    return this.objects.map(o => ({ id: o.id, def: o.def }));
  }

  getObjectsData() {
    return this.objects.map(o => ({
      id: o.id,
      position: o.body.position,
      quaternion: o.body.quaternion,
      grabbed: o.grabbed
    }));
  }

  getMagnets() { return this.magnets; }
  getGrabbedCount() { return this.grabbedCount; }
}
