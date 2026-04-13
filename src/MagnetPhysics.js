import * as CANNON from 'cannon-es';

export class MagnetPhysics {
  constructor() {
    this.world = new CANNON.World({
      gravity: new CANNON.Vec3(0, -9.82, 0)
    });
    
    // Improved bounds so stuff doesn't fall forever
    this.floorMaterial = new CANNON.Material('floor');
    this.objectMaterial = new CANNON.Material('object');
    
    const contactMaterial = new CANNON.ContactMaterial(this.floorMaterial, this.objectMaterial, {
      friction: 0.8,
      restitution: 0.1
    });
    this.world.addContactMaterial(contactMaterial);

    this.objects = [];
    this.magnetTarget = null; // Vector3
    this.magnetState = 'OFF';
    this.magnetStr = 0;
    this.grabbedCount = 0;

    this.createFloor();
    this.spawnObjects();
  }

  createFloor() {
    const floorShape = new CANNON.Plane();
    const floorBody = new CANNON.Body({
      mass: 0,
      material: this.floorMaterial
    });
    floorBody.addShape(floorShape);
    // Plane points in +Z, rotate it to face +Y
    floorBody.quaternion.setFromAxisAngle(new CANNON.Vec3(1, 0, 0), -Math.PI / 2);
    floorBody.position.set(0, -3, 0); // Put table at y= -3
    this.world.addBody(floorBody);
    
    // Back wall
    const wall1 = new CANNON.Body({ mass: 0 });
    wall1.addShape(new CANNON.Plane());
    wall1.position.set(0, 0, -8);
    this.world.addBody(wall1);
    
    // Front wall (closer to cam to prevent falling out)
    const wall2 = new CANNON.Body({ mass: 0 });
    wall2.addShape(new CANNON.Plane());
    wall2.quaternion.setFromAxisAngle(new CANNON.Vec3(1, 0, 0), Math.PI);
    wall2.position.set(0, 0, 5);
    this.world.addBody(wall2);
    
    // Left/Right walls
    const wallL = new CANNON.Body({ mass: 0 });
    wallL.addShape(new CANNON.Plane());
    wallL.quaternion.setFromAxisAngle(new CANNON.Vec3(0, 1, 0), Math.PI/2);
    wallL.position.set(-10, 0, 0);
    this.world.addBody(wallL);

    const wallR = new CANNON.Body({ mass: 0 });
    wallR.addShape(new CANNON.Plane());
    wallR.quaternion.setFromAxisAngle(new CANNON.Vec3(0, 1, 0), -Math.PI/2);
    wallR.position.set(10, 0, 0);
    this.world.addBody(wallR);
  }

  spawnObjects() {
    const objDefs = [
      { mass: 2,   shape: 'sphere', size: [0.6] }, // Large heavy sphere
      { mass: 0.5, shape: 'sphere', size: [0.3] }, // small sphere
      { mass: 1,   shape: 'box',    size: [0.5, 0.5, 0.5] }, // cube
      { mass: 0.8, shape: 'box',    size: [0.2, 0.8, 0.2] }, // rod
      { mass: 3,   shape: 'sphere', size: [0.8] }, // Big heavy sphere
      { mass: 0.3, shape: 'box',    size: [0.3, 0.3, 0.3] }, // scrap
      { mass: 0.6, shape: 'sphere', size: [0.4] }, // medium sphere
      { mass: 1.5, shape: 'box',    size: [0.6, 0.4, 0.6] }, // brick
      { mass: 0.2, shape: 'sphere', size: [0.2] }, // tiny sphere
      { mass: 0.4, shape: 'box',    size: [0.2, 0.2, 0.6] }, // screw
    ];

    objDefs.forEach((def, i) => {
      let shape;
      if (def.shape === 'sphere') shape = new CANNON.Sphere(def.size[0]);
      if (def.shape === 'box') shape = new CANNON.Box(new CANNON.Vec3(def.size[0]/2, def.size[1]/2, def.size[2]/2));

      const body = new CANNON.Body({
        mass: def.mass,
        shape: shape,
        material: this.objectMaterial,
        linearDamping: 0.5,  // air resistance
        angularDamping: 0.5
      });

      // Spread randomly around the table
      const x = (Math.random() - 0.5) * 8;
      const z = (Math.random() - 0.5) * 4 - 2;
      body.position.set(x, Math.random() * 2, z);
      
      this.world.addBody(body);
      this.objects.push({
        id: i,
        body: body,
        def: def
      });
    });
  }

  updateMagnetState(gesture) {
    if (gesture === 'FIST') this.magnetState = 'ON';
    else if (gesture === 'PINCH') this.magnetState = 'PRECISION';
    else this.magnetState = 'OFF';
  }

  setMagnetTarget(vecObj) {
    // {x, y, z} representing the palm center in 3D physics coords
    this.magnetTarget = vecObj;
  }

  step(dt) {
    // Ramp up/down magnet strength
    let targetStr = 0;
    if (this.magnetState === 'ON') targetStr = 1.0;
    if (this.magnetState === 'PRECISION') targetStr = 0.35;
    
    // Smooth damp
    this.magnetStr += (targetStr - this.magnetStr) * Math.min(dt * 5, 1);

    this.grabbedCount = 0;

    if (this.magnetTarget && this.magnetStr > 0.05) {
      const tx = this.magnetTarget.x;
      const ty = this.magnetTarget.y;
      const tz = this.magnetTarget.z; // usually 0 on projected plane

      this.objects.forEach(obj => {
        const body = obj.body;
        const dx = tx - body.position.x;
        const dy = ty - body.position.y;
        const dz = tz - body.position.z;
        const distSq = dx*dx + dy*dy + dz*dz;
        const dist = Math.sqrt(distSq);

        // Inverse square law simplified, plus linear damping for stability
        if (dist > 0.1) {
          // If very close, snap to center-ish to avoid exploding
          if (dist < 1.0) {
            this.grabbedCount++;
            
            // Apply strong damping so they stick
            body.velocity.scale(0.8, body.velocity);
            
            const pullForce = 50 * this.magnetStr * body.mass;
            body.applyForce(new CANNON.Vec3(
              (dx/dist) * pullForce,
              (dy/dist) * pullForce,
              (dz/dist) * pullForce
            ), body.position);

            // Give them a little spin for visual flavor
            body.angularVelocity.set(
              body.angularVelocity.x + (Math.random()-0.5)*0.5,
              body.angularVelocity.y + (Math.random()-0.5)*0.5,
              body.angularVelocity.z + (Math.random()-0.5)*0.5
            );
          } else {
             // Attraction force
            const pullForce = (200 * this.magnetStr * body.mass) / (distSq * 0.5 + 0.1);
            body.applyForce(new CANNON.Vec3(
              (dx/dist) * pullForce,
              ((dy + 2) /dist) * pullForce, // give positive offset so it pulls UP harder
              (dz/dist) * pullForce
            ), body.position);
          }
        }
      });
    }

    this.world.step(1/60, dt, 3);
  }

  getObjectsInfo() {
    return this.objects.map(o => ({ id: o.id, def: o.def }));
  }

  getObjectsData() {
    return this.objects.map(o => ({
      id: o.id,
      position: o.body.position,
      quaternion: o.body.quaternion
    }));
  }

  getMagnetStrength() {
    return this.magnetStr;
  }
  
  getGrabbedCount() {
    return this.grabbedCount;
  }
}
