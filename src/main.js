import { HandDetector } from './HandDetector.js';
import { SceneVisuals } from './SceneVisuals.js';
import { MagnetPhysics } from './MagnetPhysics.js';

let video, canvas;
let detector, visuals, physics;
let isStarted = false;
let lastTime = 0;

// DOM Elements
const uiGesture = document.getElementById('ui-gesture');
const uiMagnet = document.getElementById('ui-magnet');
const uiFlux = document.getElementById('ui-flux');
const uiObjects = document.getElementById('ui-objects');
const startBtn = document.getElementById('start-btn');
const loadingOverlay = document.getElementById('loading');
const uiAiStatus = document.getElementById('ui-ai-status');

async function init() {
  canvas = document.getElementById('three-canvas');
  video = document.getElementById('webcam');

  // ── Step 1: Load AI model first (no webcam needed yet) ──
  detector = new HandDetector(video);
  try {
    await detector.initialize();
  } catch (err) {
    console.error('MediaPipe load error:', err);
    uiAiStatus.textContent = 'AI ERROR';
    uiAiStatus.className = 'v red';
    document.querySelector('.overlay h2').textContent = 'VISION AI FAILED TO LOAD';
    document.querySelector('.overlay p').textContent = err.message;
    return;
  }

  uiAiStatus.textContent = 'ONLINE';
  uiAiStatus.className = 'v green';

  // ── Step 2: Enable start button — webcam is requested on click ──
  startBtn.disabled = false;
  startBtn.textContent = 'ENGAGE AR SIMULATION';
  startBtn.addEventListener('click', onStartClick);
}

async function onStartClick() {
  startBtn.disabled = true;
  startBtn.textContent = 'REQUESTING WEBCAM...';

  // ── Step 3: Request webcam only after user clicks ──
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }
    });
    video.srcObject = stream;
    await new Promise((resolve) => {
      video.onloadeddata = () => resolve();
    });
  } catch (error) {
    console.error('Webcam Error:', error);
    startBtn.textContent = 'WEBCAM DENIED — RETRY';
    startBtn.disabled = false;
    document.querySelector('.overlay h2').textContent = 'WEBCAM ACCESS DENIED';
    document.querySelector('.overlay h2').style.color = '#ff1744';
    document.querySelector('.overlay p').textContent =
      'Please allow camera access and click the button again.';
    return;
  }

  // ── Step 4: Init physics & visuals after webcam is live ──
  physics = new MagnetPhysics();
  visuals = new SceneVisuals(canvas, video);
  visuals.initPhysicsObjects(physics.getObjectsInfo());

  loadingOverlay.style.display = 'none';
  isStarted = true;
  lastTime = performance.now(); // reset so first dt is tiny
  animate();
}

function updateHUD(gesture, magnetStr, grabbedCount) {
  let gState = 'NONE';
  let gClass = 'dim';
  let mState = 'OFF';
  let mClass = 'dim';

  if (gesture === 'FIST') {
    gState = 'FIST'; gClass = 'cyan';
    mState = 'MAX PULL'; mClass = 'cyan';
  } else if (gesture === 'PINCH') {
    gState = 'PINCH'; gClass = 'amber';
    mState = 'PRECISION'; mClass = 'amber';
  } else if (gesture === 'OPEN') {
    gState = 'OPEN'; gClass = 'dim';
    mState = 'INACTIVE'; mClass = 'dim';
  }

  uiGesture.textContent = gState;
  uiGesture.className = `val ${gClass}`;

  uiMagnet.textContent = mState;
  uiMagnet.className = `val ${mClass}`;

  const fluxT = (magnetStr * 1.85).toFixed(2);
  uiFlux.textContent = `${fluxT} T`;
  uiFlux.className = `val ${magnetStr > 0 ? (gesture === 'FIST' ? 'cyan' : 'amber') : 'dim'}`;

  uiObjects.textContent = grabbedCount;
  uiObjects.className = `val ${grabbedCount > 0 ? 'green' : 'dim'}`;
}

function animate() {
  requestAnimationFrame(animate);
  if (!isStarted) return;

  const now = performance.now();
  let dt = (now - lastTime) / 1000;
  lastTime = now;

  // Clamp dt to prevent physics explosion after tab switch / pause
  if (dt > 0.1) dt = 0.016;

  // 1. Detect Hand & Gestures
  const handResult = detector.detect();

  const gesture = detector.getCurrentGesture();
  physics.updateMagnetState(gesture);

  // Calculate 3D target for physics (palm center in physics world space)
  let palmPos3D = null;
  if (handResult && handResult.landmarks && handResult.landmarks.length > 0) {
    const lms = handResult.landmarks[0];

    // Palm center = average of wrist(0), index-mcp(5), pinky-mcp(17)
    const cx = (lms[0].x + lms[5].x + lms[17].x) / 3;
    const cy = (lms[0].y + lms[5].y + lms[17].y) / 3;
    const cz = (lms[0].z + lms[5].z + lms[17].z) / 3;

    palmPos3D = visuals.screenToWorld(cx, cy, cz);
    physics.setMagnetTarget(palmPos3D);
  } else {
    physics.setMagnetTarget(null);
  }

  // 2. Step Physics
  physics.step(dt);

  // 3. Update Visuals
  const physicsData = physics.getObjectsData();
  const magnetStr = physics.getMagnetStrength();
  visuals.update(handResult, gesture, magnetStr, physicsData, dt);

  // 4. Update HUD
  const grabbed = physics.getGrabbedCount();
  updateHUD(gesture, magnetStr, grabbed);
}

// Start everything
init();
