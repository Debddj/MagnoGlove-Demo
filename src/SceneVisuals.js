import * as THREE from 'three';

export class SceneVisuals {
  constructor(canvas, video) {
    this.canvas = canvas;
    this.video = video;
    
    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    // Dark tone mapping for glowing stuff
    this.renderer.toneMapping = THREE.ReinhardToneMapping;
    
    this.scene = new THREE.Scene();
    
    // Camera is setup to mimic webcam FOV roughly
    const aspect = window.innerWidth / window.innerHeight;
    this.camera = new THREE.PerspectiveCamera(50, aspect, 0.1, 100);
    this.camera.position.set(0, 0, 10); // Sit back 10 units
    
    this.setupLighting();
    
    this.meshes = {};
    
    // Hand skeleton material
    this.jointMaterial = new THREE.MeshBasicMaterial({ color: 0x00e5ff });
    this.boneMaterial = new THREE.LineBasicMaterial({ color: 0x00e5ff, linewidth: 3, transparent: true, opacity: 0.7 });
    
    this.joints = [];
    for(let i=0; i<21; i++) {
        const mesh = new THREE.Mesh(new THREE.SphereGeometry(0.15, 8, 8), this.jointMaterial);
        mesh.visible = false;
        this.scene.add(mesh);
        this.joints.push(mesh);
    }
    
    // Lines connecting joints
    this.bones = [];
    const connections = [
        [0,1],[1,2],[2,3],[3,4], // Thumb
        [0,5],[5,6],[6,7],[7,8], // Index
        [5,9],[9,10],[10,11],[11,12], // Middle
        [9,13],[13,14],[14,15],[15,16], // Ring
        [13,17],[0,17],[17,18],[18,19],[19,20] // Pinky + Palm base
    ];
    this.connections = connections;
    for(let i=0; i<connections.length; i++) {
        const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
        const line = new THREE.Line(geo, this.boneMaterial);
        line.visible = false;
        this.scene.add(line);
        this.bones.push(line);
    }

    // Magnet Aura / Field
    this.auraMesh = new THREE.Mesh(
        new THREE.SphereGeometry(2.5, 32, 32),
        new THREE.MeshBasicMaterial({ color: 0x00e5ff, transparent: true, opacity: 0.0, wireframe: true })
    );
    this.scene.add(this.auraMesh);

    window.addEventListener('resize', this.onResize.bind(this));
  }

  setupLighting() {
    const ambient = new THREE.AmbientLight(0xffffff, 0.8); // Ambient
    this.scene.add(ambient);
    
    const dLight = new THREE.DirectionalLight(0xffffff, 2.5);
    dLight.position.set(5, 5, 5);
    this.scene.add(dLight);
    
    const fillLight = new THREE.DirectionalLight(0x4080ff, 1.5);
    fillLight.position.set(-5, 0, 5);
    this.scene.add(fillLight);
  }

  initPhysicsObjects(objectsInfo) {
    // Metal materials
    const silverMat = new THREE.MeshStandardMaterial({ 
      color: 0xcccccc, metalness: 0.9, roughness: 0.2 
    });
    const copperMat = new THREE.MeshStandardMaterial({ 
      color: 0xb87333, metalness: 0.8, roughness: 0.3 
    });
    const goldMat = new THREE.MeshStandardMaterial({ 
      color: 0xffd700, metalness: 1.0, roughness: 0.1 
    });
    const scrapMat = new THREE.MeshStandardMaterial({ 
      color: 0x4a4a4a, metalness: 0.6, roughness: 0.7 
    });
    
    const mats = [silverMat, copperMat, goldMat, scrapMat];

    objectsInfo.forEach(({ id, def }) => {
      let geo;
      if (def.shape === 'sphere') geo = new THREE.SphereGeometry(def.size[0], 32, 32);
      if (def.shape === 'box') geo = new THREE.BoxGeometry(def.size[0], def.size[1], def.size[2]);

      const mat = mats[Math.floor(Math.random() * mats.length)];
      
      const mesh = new THREE.Mesh(geo, mat);
      // add a glowing inside core or something? nah it's okay.
      this.scene.add(mesh);
      this.meshes[id] = mesh;
    });
  }

  // Convert MediaPipe [0,1] screen coordinates to 3D world space at Z=0 plane
  screenToWorld(nx, ny, nz) {
    // MediaPipe normalizes to [0,1] top-left origin.
    // Video is mirrored via CSS scaleX(-1), but MediaPipe operates on the raw
    // (un-mirrored) image, so X=0 is the left edge of the raw frame.
    // To make the 3D overlay match the mirrored video, we flip X.
    const screenX = -(nx * 2 - 1);
    const screenY = -(ny * 2 - 1);

    const vec = new THREE.Vector3(screenX, screenY, 0.5);
    vec.unproject(this.camera);
    vec.sub(this.camera.position).normalize();
    const distance = -this.camera.position.z / vec.z;
    const pos = new THREE.Vector3().copy(this.camera.position).add(vec.multiplyScalar(distance));

    // Keep Z at 0 (the projection plane). MediaPipe's z is relative depth
    // and far too noisy / small-scale to map directly into world space.
    pos.z = 0;

    return pos;
  }

  update(handResult, gesture, magnetStr, physicsData, dt) {
    // 1. Update Physics Objects
    physicsData.forEach(({ id, position, quaternion }) => {
      const mesh = this.meshes[id];
      if (mesh) {
        mesh.position.copy(position);
        mesh.quaternion.copy(quaternion);
      }
    });

    // 2. Update Hand Skeleton
    let palmPos = null;
    if (handResult && handResult.landmarks && handResult.landmarks.length > 0) {
      const landmarks = handResult.landmarks[0];
      
      // Update joint positions
      for (let i = 0; i < 21; i++) {
        const lm = landmarks[i];
        const pos = this.screenToWorld(lm.x, lm.y, lm.z);
        this.joints[i].position.copy(pos);
        this.joints[i].visible = true;

        if (i===0) palmPos = pos;
      }

      // Update bone lines
      this.connections.forEach((conn, index) => {
        const j1 = this.joints[conn[0]].position;
        const j2 = this.joints[conn[1]].position;
        this.bones[index].geometry.setFromPoints([j1, j2]);
        this.bones[index].visible = true;
      });

      // Update Aura
      if (magnetStr > 0.05) {
        this.auraMesh.position.copy(palmPos);
        this.auraMesh.visible = true;
        // Pulse animation
        const scale = 1.0 + Math.sin(performance.now() * 0.01) * 0.1 * magnetStr;
        this.auraMesh.scale.set(scale, scale, scale);
        this.auraMesh.material.opacity = magnetStr * 0.4;
        
        let c = gesture === 'FIST' ? 0x00e5ff : 0xffab00;
        this.auraMesh.material.color.setHex(c);
        this.jointMaterial.color.setHex(c);
        this.boneMaterial.color.setHex(c);
      } else {
        this.auraMesh.visible = false;
        this.jointMaterial.color.setHex(0x587090);
        this.boneMaterial.color.setHex(0x587090);
      }
    } else {
      // Hide if no hand
      this.joints.forEach(j => j.visible = false);
      this.bones.forEach(b => b.visible = false);
      this.auraMesh.visible = false;
    }

    this.renderer.render(this.scene, this.camera);
  }

  onResize() {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
  }
}
