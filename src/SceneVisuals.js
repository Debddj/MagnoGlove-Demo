import * as THREE from 'three';

// ── Shared color constants ──────────────────────────────────────
const COL_CYAN      = new THREE.Color(0x00e5ff);
const COL_AMBER     = new THREE.Color(0xffab00);
const COL_DIM       = new THREE.Color(0x1a2a40);
const COL_GLOVE_ON  = new THREE.Color(0x0088dd);
const COL_GLOVE_PR  = new THREE.Color(0xcc8800);
const COL_GLOVE_OFF = new THREE.Color(0x0c1830);

// ── Hand landmark connections for the skeleton ──────────────────
const BONE_CONNECTIONS = [
  [0,1],[1,2],[2,3],[3,4],         // Thumb
  [0,5],[5,6],[6,7],[7,8],         // Index
  [5,9],[9,10],[10,11],[11,12],    // Middle
  [9,13],[13,14],[14,15],[15,16],  // Ring
  [13,17],[0,17],[17,18],[18,19],[19,20] // Pinky + palm
];

// Finger tips for glove cap rendering
const FINGER_TIPS = [4, 8, 12, 16, 20];
const PALM_LANDMARKS = [0, 5, 9, 13, 17]; // wrist + MCP knuckles

export class SceneVisuals {
  constructor(canvas, video) {
    this.canvas = canvas;
    this.video  = video;

    // ── Renderer ──
    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.2;

    this.scene = new THREE.Scene();

    const aspect = window.innerWidth / window.innerHeight;
    this.camera = new THREE.PerspectiveCamera(50, aspect, 0.1, 100);
    this.camera.position.set(0, 0, 10);

    this.setupLighting();
    this.meshes = {};  // physics object meshes by id

    // ── Per-hand visual groups (we create two sets) ──
    this.handVisuals = {
      Left:  this.createHandVisuals(),
      Right: this.createHandVisuals()
    };

    // ── Inter-hand energy arc ──
    this.arcMaterial = new THREE.LineBasicMaterial({
      color: 0x00e5ff, transparent: true, opacity: 0.6, linewidth: 2
    });
    this.arcPoints = [];
    for (let i = 0; i < 20; i++) this.arcPoints.push(new THREE.Vector3());
    this.arcGeo = new THREE.BufferGeometry().setFromPoints(this.arcPoints);
    this.arcLine = new THREE.Line(this.arcGeo, this.arcMaterial);
    this.arcLine.visible = false;
    this.scene.add(this.arcLine);

    // ── Particle system for magnetic attraction ──
    this.particleCount = 200;
    this.particleGeo = new THREE.BufferGeometry();
    const pPos = new Float32Array(this.particleCount * 3);
    const pCol = new Float32Array(this.particleCount * 3);
    const pSize = new Float32Array(this.particleCount);
    for (let i = 0; i < this.particleCount; i++) {
      pPos[i*3] = (Math.random()-0.5)*20;
      pPos[i*3+1] = (Math.random()-0.5)*20;
      pPos[i*3+2] = (Math.random()-0.5)*4;
      pCol[i*3] = 0; pCol[i*3+1] = 0.9; pCol[i*3+2] = 1;
      pSize[i] = Math.random() * 3 + 1;
    }
    this.particleGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    this.particleGeo.setAttribute('color', new THREE.BufferAttribute(pCol, 3));
    this.particleGeo.setAttribute('size', new THREE.BufferAttribute(pSize, 1));
    this.particleMat = new THREE.PointsMaterial({
      size: 0.08,
      vertexColors: true,
      transparent: true,
      opacity: 0.6,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    });
    this.particles = new THREE.Points(this.particleGeo, this.particleMat);
    this.scene.add(this.particles);
    this.particleVelocities = [];
    for (let i = 0; i < this.particleCount; i++) {
      this.particleVelocities.push({
        vx: (Math.random()-0.5)*0.5,
        vy: (Math.random()-0.5)*0.5,
        vz: (Math.random()-0.5)*0.2
      });
    }

    window.addEventListener('resize', this.onResize.bind(this));
  }

  setupLighting() {
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.6));

    const key = new THREE.DirectionalLight(0xffffff, 2.5);
    key.position.set(5, 8, 5);
    this.scene.add(key);

    const fill = new THREE.DirectionalLight(0x4080ff, 1.2);
    fill.position.set(-5, 2, 5);
    this.scene.add(fill);

    const rim = new THREE.DirectionalLight(0xff8040, 0.8);
    rim.position.set(0, -3, -5);
    this.scene.add(rim);
  }

  /** Create a full set of visual objects for one hand */
  createHandVisuals() {
    const group = { joints: [], bones: [], aura: null, rings: [], palmGlow: null };

    // Joint nodes — glowing spheres at each landmark
    const jointMat = new THREE.MeshBasicMaterial({ color: 0x00e5ff });
    for (let i = 0; i < 21; i++) {
      const radius = FINGER_TIPS.includes(i) ? 0.12 : (PALM_LANDMARKS.includes(i) ? 0.1 : 0.07);
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 12, 12), jointMat.clone());
      mesh.visible = false;
      this.scene.add(mesh);
      group.joints.push(mesh);
    }

    // Bone lines — thick glowing connectors
    const boneMat = new THREE.LineBasicMaterial({
      color: 0x00e5ff, transparent: true, opacity: 0.7, linewidth: 2
    });
    for (let i = 0; i < BONE_CONNECTIONS.length; i++) {
      const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
      const line = new THREE.Line(geo, boneMat.clone());
      line.visible = false;
      this.scene.add(line);
      group.bones.push(line);
    }

    // Aura sphere — electromagnetic field
    const auraMat = new THREE.MeshBasicMaterial({
      color: 0x00e5ff, transparent: true, opacity: 0, wireframe: true
    });
    group.aura = new THREE.Mesh(new THREE.SphereGeometry(2, 24, 24), auraMat);
    group.aura.visible = false;
    this.scene.add(group.aura);

    // Expanding rings
    for (let i = 0; i < 3; i++) {
      const ringGeo = new THREE.RingGeometry(0.8, 0.85, 48);
      const ringMat = new THREE.MeshBasicMaterial({
        color: 0x00e5ff, transparent: true, opacity: 0, side: THREE.DoubleSide
      });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.visible = false;
      this.scene.add(ring);
      group.rings.push(ring);
    }

    // Palm glow — point light at palm center
    group.palmGlow = new THREE.PointLight(0x00e5ff, 0, 8);
    this.scene.add(group.palmGlow);

    return group;
  }

  initPhysicsObjects(objectsInfo) {
    // Material palette — varied metallic looks
    const materialDefs = [
      { color: 0xcccccc, metalness: 0.95, roughness: 0.15 }, // Polished steel
      { color: 0xb87333, metalness: 0.85, roughness: 0.25 }, // Copper
      { color: 0xffd700, metalness: 1.0,  roughness: 0.1  }, // Gold
      { color: 0x3a3a3a, metalness: 0.7,  roughness: 0.6  }, // Dark iron
      { color: 0x8888aa, metalness: 0.9,  roughness: 0.2  }, // Titanium
    ];

    objectsInfo.forEach(({ id, def }) => {
      let geo;
      if (def.shape === 'sphere') {
        geo = new THREE.SphereGeometry(def.size[0], 24, 24);
      } else {
        geo = new THREE.BoxGeometry(def.size[0], def.size[1], def.size[2]);
      }

      const matDef = materialDefs[id % materialDefs.length];
      const mat = new THREE.MeshStandardMaterial(matDef);
      const mesh = new THREE.Mesh(geo, mat);
      this.scene.add(mesh);
      this.meshes[id] = mesh;
    });
  }

  screenToWorld(nx, ny) {
    // Mirror X because CSS scaleX(-1) mirrors the video
    const screenX = -(nx * 2 - 1);
    const screenY = -(ny * 2 - 1);

    const vec = new THREE.Vector3(screenX, screenY, 0.5);
    vec.unproject(this.camera);
    vec.sub(this.camera.position).normalize();
    const distance = -this.camera.position.z / vec.z;
    const pos = new THREE.Vector3().copy(this.camera.position).add(vec.multiplyScalar(distance));
    pos.z = 0;
    return pos;
  }

  /**
   * Main update loop
   * @param {Object} handResult - raw MediaPipe results
   * @param {Array} handsData - [{ handedness, gesture, landmarks }]
   * @param {Object} magnets - { Left: {strength}, Right: {strength} }
   * @param {Array} physicsData - physics object positions
   * @param {number} dt
   */
  update(handResult, handsData, magnets, physicsData, dt) {
    const now = performance.now() * 0.001;

    // ── 1. Update physics object meshes ──
    physicsData.forEach(({ id, position, quaternion, grabbed }) => {
      const mesh = this.meshes[id];
      if (!mesh) return;
      mesh.position.copy(position);
      mesh.quaternion.copy(quaternion);

      // Glow grabbed objects
      if (grabbed && mesh.material.emissive) {
        mesh.material.emissiveIntensity = 0.3;
        mesh.material.emissive.setHex(0x00aaff);
      } else if (mesh.material.emissive) {
        mesh.material.emissiveIntensity = 0;
      }
    });

    // ── 2. Update each hand's visuals ──
    const activePalms = []; // for inter-hand arc

    ['Left', 'Right'].forEach(side => {
      const vis = this.handVisuals[side];
      const handData = handsData.find(h => h.handedness === side);
      const mag = magnets[side];

      if (handData && handData.landmarks) {
        const lms = handData.landmarks;
        const gesture = handData.gesture;
        const str = mag.strength;

        // Determine color scheme
        let gloveColor, glowColor;
        if (str > 0.1 && gesture === 'FIST') {
          gloveColor = COL_CYAN;
          glowColor = 0x00e5ff;
        } else if (str > 0.05 && gesture === 'PINCH') {
          gloveColor = COL_AMBER;
          glowColor = 0xffab00;
        } else {
          gloveColor = COL_DIM;
          glowColor = 0x1a2a40;
        }

        // Update joints
        let palmCenter = new THREE.Vector3(0, 0, 0);
        let palmCount = 0;

        for (let i = 0; i < 21; i++) {
          const pos = this.screenToWorld(lms[i].x, lms[i].y);
          vis.joints[i].position.copy(pos);
          vis.joints[i].visible = true;
          vis.joints[i].material.color.copy(gloveColor);

          // Make fingertips and palm nodes brighter when active
          if (FINGER_TIPS.includes(i) && str > 0.1) {
            vis.joints[i].material.color.multiplyScalar(1.5);
          }

          if (PALM_LANDMARKS.includes(i)) {
            palmCenter.add(pos);
            palmCount++;
          }
        }
        palmCenter.divideScalar(palmCount);
        activePalms.push(palmCenter);

        // Update bones
        BONE_CONNECTIONS.forEach((conn, idx) => {
          const p1 = vis.joints[conn[0]].position;
          const p2 = vis.joints[conn[1]].position;
          vis.bones[idx].geometry.setFromPoints([p1, p2]);
          vis.bones[idx].visible = true;
          vis.bones[idx].material.color.copy(gloveColor);
          vis.bones[idx].material.opacity = 0.5 + str * 0.5;
        });

        // Aura
        if (str > 0.05) {
          vis.aura.position.copy(palmCenter);
          vis.aura.visible = true;
          const s = (1.5 + str * 1.5) * (1 + Math.sin(now * 4) * 0.08);
          vis.aura.scale.set(s, s, s);
          vis.aura.material.opacity = str * 0.25;
          vis.aura.material.color.setHex(glowColor);
          vis.aura.rotation.y = now * 1.5;
          vis.aura.rotation.x = now * 0.7;
        } else {
          vis.aura.visible = false;
        }

        // Expanding rings
        vis.rings.forEach((ring, ri) => {
          if (str > 0.05) {
            ring.visible = true;
            ring.position.copy(palmCenter);
            ring.lookAt(this.camera.position);
            const phase = (now * 2 + ri * 0.7) % 2;
            const scale = 0.3 + phase * (1.5 + str * 2);
            ring.scale.set(scale, scale, scale);
            ring.material.opacity = Math.max(0, (1 - phase / 2)) * str * 0.5;
            ring.material.color.setHex(glowColor);
          } else {
            ring.visible = false;
          }
        });

        // Palm glow light
        vis.palmGlow.position.copy(palmCenter);
        vis.palmGlow.intensity = str * 3;
        vis.palmGlow.color.setHex(glowColor);

      } else {
        // Hand not detected — hide everything
        vis.joints.forEach(j => j.visible = false);
        vis.bones.forEach(b => b.visible = false);
        vis.aura.visible = false;
        vis.rings.forEach(r => r.visible = false);
        vis.palmGlow.intensity = 0;
      }
    });

    // ── 3. Inter-hand energy arc ──
    if (activePalms.length === 2) {
      const anyActive = (magnets.Left.strength > 0.05 || magnets.Right.strength > 0.05);
      if (anyActive) {
        const p1 = activePalms[0];
        const p2 = activePalms[1];
        const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);

        for (let i = 0; i < 20; i++) {
          const t = i / 19;
          const pos = new THREE.Vector3().lerpVectors(p1, p2, t);
          // Add sine wave displacement perpendicular to the line
          const offset = Math.sin(t * Math.PI * 3 + now * 8) * 0.3 * Math.sin(t * Math.PI);
          const offset2 = Math.cos(t * Math.PI * 2 + now * 6) * 0.2 * Math.sin(t * Math.PI);
          pos.y += offset;
          pos.x += offset2;
          this.arcPoints[i].copy(pos);
        }
        this.arcGeo.setFromPoints(this.arcPoints);
        this.arcLine.visible = true;
        const maxStr = Math.max(magnets.Left.strength, magnets.Right.strength);
        this.arcMaterial.opacity = maxStr * 0.7;
        this.arcMaterial.color.setHex(
          magnets.Left.strength > 0.3 || magnets.Right.strength > 0.3 ? 0x00e5ff : 0xffab00
        );
      } else {
        this.arcLine.visible = false;
      }
    } else {
      this.arcLine.visible = false;
    }

    // ── 4. Update ambient particles ──
    this.updateParticles(activePalms, magnets, dt, now);

    // ── 5. Render ──
    this.renderer.render(this.scene, this.camera);
  }

  updateParticles(palms, magnets, dt, now) {
    const posAttr = this.particleGeo.attributes.position;
    const colAttr = this.particleGeo.attributes.color;
    const maxStr = Math.max(magnets.Left.strength, magnets.Right.strength);

    for (let i = 0; i < this.particleCount; i++) {
      const ix = i * 3;
      let px = posAttr.array[ix];
      let py = posAttr.array[ix+1];
      let pz = posAttr.array[ix+2];
      const vel = this.particleVelocities[i];

      // Attract particles toward active palms
      if (maxStr > 0.05) {
        palms.forEach(palm => {
          const dx = palm.x - px;
          const dy = palm.y - py;
          const dz = palm.z - pz;
          const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
          if (dist > 0.5 && dist < 8) {
            const force = maxStr * 2 / (dist * dist + 1);
            vel.vx += (dx/dist) * force * dt;
            vel.vy += (dy/dist) * force * dt;
            vel.vz += (dz/dist) * force * dt;
          }
        });
      }

      // Random drift
      vel.vx += (Math.random()-0.5) * dt * 2;
      vel.vy += (Math.random()-0.5) * dt * 2;
      vel.vz += (Math.random()-0.5) * dt * 0.5;

      // Damping
      vel.vx *= 0.98; vel.vy *= 0.98; vel.vz *= 0.98;

      px += vel.vx * dt;
      py += vel.vy * dt;
      pz += vel.vz * dt;

      // Wrap around
      if (px < -12) px = 12; if (px > 12) px = -12;
      if (py < -5) py = 10; if (py > 10) py = -5;
      if (pz < -4) pz = 4; if (pz > 4) pz = -4;

      posAttr.array[ix]   = px;
      posAttr.array[ix+1] = py;
      posAttr.array[ix+2] = pz;

      // Color based on proximity to palms
      if (maxStr > 0.1) {
        colAttr.array[ix]   = 0;
        colAttr.array[ix+1] = 0.85 + Math.sin(now * 3 + i) * 0.15;
        colAttr.array[ix+2] = 1;
      } else {
        colAttr.array[ix]   = 0.1;
        colAttr.array[ix+1] = 0.15;
        colAttr.array[ix+2] = 0.25;
      }
    }

    posAttr.needsUpdate = true;
    colAttr.needsUpdate = true;
    this.particleMat.opacity = 0.15 + maxStr * 0.5;
  }

  onResize() {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
  }
}
