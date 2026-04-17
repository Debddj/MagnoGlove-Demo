import { HandDetector } from './HandDetector.js';
import { SceneVisuals } from './SceneVisuals.js';
import { MagnetPhysics } from './MagnetPhysics.js';

let video, canvas;
let detector, visuals, physics;
let isStarted = false;
let lastTime = 0;

// DOM Elements
const uiGesture   = document.getElementById('ui-gesture');
const uiMagnet    = document.getElementById('ui-magnet');
const uiFlux      = document.getElementById('ui-flux');
const uiObjects   = document.getElementById('ui-objects');
const uiFps       = document.getElementById('ui-fps');
const uiFrameTime = document.getElementById('ui-frame-time');
const uiStability = document.getElementById('ui-stability');
const uiTrackingStatus = document.getElementById('ui-tracking-status');
const startBtn    = document.getElementById('start-btn');
const loadingOverlay = document.getElementById('loading');
const uiAiStatus  = document.getElementById('ui-ai-status');

// Real-time metrics (rolling 30s evidence window)
const METRICS_WINDOW_SEC = 30;
const metrics = {
  samples: [],
  sumDt: 0,
  anyTracked: 0,
  dualTracked: 0,
  fps: 0,
  avgFrameMs: 0,
  anyStability: 0,
  dualStability: 0
};

// ══════════════════════════════════════════════════════════════
//  INITIALIZATION
// ══════════════════════════════════════════════════════════════

async function init() {
  canvas = document.getElementById('three-canvas');
  video  = document.getElementById('webcam');

  // Step 1: Load AI model (no webcam needed yet)
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

  // Step 2: Enable start button
  startBtn.disabled = false;
  startBtn.textContent = 'ENGAGE AR SIMULATION';
  startBtn.addEventListener('click', onStartClick);
}

async function onStartClick() {
  startBtn.disabled = true;
  startBtn.textContent = 'REQUESTING WEBCAM...';

  // Step 3: Request webcam
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }
    });
    video.srcObject = stream;
    await new Promise(resolve => { video.onloadeddata = resolve; });
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

  // Step 4: Init physics & 3D visuals
  physics = new MagnetPhysics();
  visuals = new SceneVisuals(canvas, video);
  visuals.initPhysicsObjects(physics.getObjectsInfo());

  loadingOverlay.style.display = 'none';
  isStarted = true;
  lastTime = performance.now();
  animate();
}

// ══════════════════════════════════════════════════════════════
//  HUD UPDATE — shows combined status of both hands
// ══════════════════════════════════════════════════════════════

function updateHUD(handsData, magnets, grabbedCount) {
  // Determine dominant gesture (strongest active hand)
  let bestGesture = 'NONE';
  let bestStr = 0;

  ['Left', 'Right'].forEach(side => {
    const hand = handsData.find(h => h.handedness === side);
    const str = magnets[side].strength;
    if (hand && str > bestStr) {
      bestGesture = hand.gesture;
      bestStr = str;
    } else if (hand && hand.gesture !== 'OPEN' && bestGesture === 'NONE') {
      bestGesture = hand.gesture;
    }
  });

  // Count active hands
  const activeHands = handsData.filter(h => h.gesture === 'FIST' || h.gesture === 'PINCH').length;
  const handLabel = handsData.length === 2 ? 'DUAL' : handsData.length === 1 ? handsData[0].handedness.toUpperCase() : 'NONE';

  // Gesture display
  let gText, gClass;
  if (bestGesture === 'FIST')   { gText = `✊ FIST (${handLabel})`; gClass = 'cyan'; }
  else if (bestGesture === 'PINCH') { gText = `👌 PINCH (${handLabel})`; gClass = 'amber'; }
  else if (handsData.length > 0) { gText = `✋ OPEN (${handLabel})`; gClass = 'dim'; }
  else { gText = 'NO HANDS'; gClass = 'dim'; }

  uiGesture.textContent = gText;
  uiGesture.className = `val ${gClass}`;

  // Magnet state
  const maxStr = Math.max(magnets.Left.strength, magnets.Right.strength);
  let mText, mClass;
  if (maxStr > 0.5)     { mText = 'MAX POWER'; mClass = 'cyan'; }
  else if (maxStr > 0.1) { mText = 'PRECISION'; mClass = 'amber'; }
  else                   { mText = 'STANDBY'; mClass = 'dim'; }

  if (activeHands === 2) mText = '⚡ DUAL ' + mText;

  uiMagnet.textContent = mText;
  uiMagnet.className = `val ${mClass}`;

  // Flux
  const flux = (maxStr * 1.85).toFixed(2);
  uiFlux.textContent = `${flux} T`;
  uiFlux.className = `val ${maxStr > 0.1 ? (maxStr > 0.5 ? 'cyan' : 'amber') : 'dim'}`;

  // Objects
  uiObjects.textContent = `${grabbedCount} / 15`;
  uiObjects.className = `val ${grabbedCount > 0 ? 'green' : 'dim'}`;

  // Runtime evidence metrics (rolling 30s)
  uiFps.textContent = metrics.fps.toFixed(1);
  uiFrameTime.textContent = `${metrics.avgFrameMs.toFixed(1)} ms`;
  uiStability.textContent = `A${metrics.anyStability.toFixed(0)}% D${metrics.dualStability.toFixed(0)}%`;

  const perfClass = metrics.fps >= 45 ? 'green' : metrics.fps >= 24 ? 'amber' : 'red';
  const frameClass = metrics.avgFrameMs <= 22 ? 'green' : metrics.avgFrameMs <= 42 ? 'amber' : 'red';
  const stabilityClass = metrics.anyStability >= 80 ? 'green' : metrics.anyStability >= 55 ? 'amber' : 'red';
  uiFps.className = `val ${perfClass}`;
  uiFrameTime.className = `val ${frameClass}`;
  uiStability.className = `val ${stabilityClass}`;

  if (handsData.length === 2) {
    uiTrackingStatus.textContent = 'DUAL HAND';
    uiTrackingStatus.className = 'v green';
  } else if (handsData.length === 1) {
    uiTrackingStatus.textContent = 'SINGLE HAND';
    uiTrackingStatus.className = 'v amber';
  } else {
    uiTrackingStatus.textContent = 'NO HANDS';
    uiTrackingStatus.className = 'v red';
  }
}

function updateRuntimeMetrics(dt, handsCount, nowMs) {
  const stampSec = nowMs * 0.001;
  const hasAny = handsCount > 0;
  const hasDual = handsCount === 2;

  const sample = { t: stampSec, dt, hasAny, hasDual };
  metrics.samples.push(sample);
  metrics.sumDt += dt;
  if (hasAny) metrics.anyTracked += 1;
  if (hasDual) metrics.dualTracked += 1;

  while (metrics.samples.length > 0 && (stampSec - metrics.samples[0].t) > METRICS_WINDOW_SEC) {
    const old = metrics.samples.shift();
    metrics.sumDt -= old.dt;
    if (old.hasAny) metrics.anyTracked -= 1;
    if (old.hasDual) metrics.dualTracked -= 1;
  }

  const n = metrics.samples.length;
  if (n > 0) {
    const avgDt = metrics.sumDt / n;
    metrics.avgFrameMs = avgDt * 1000;
    metrics.fps = avgDt > 0 ? (1 / avgDt) : 0;
    metrics.anyStability = (metrics.anyTracked / n) * 100;
    metrics.dualStability = (metrics.dualTracked / n) * 100;
  } else {
    metrics.avgFrameMs = 0;
    metrics.fps = 0;
    metrics.anyStability = 0;
    metrics.dualStability = 0;
  }
}

// ══════════════════════════════════════════════════════════════
//  ANIMATION LOOP
// ══════════════════════════════════════════════════════════════

function animate() {
  requestAnimationFrame(animate);
  if (!isStarted) return;

  const now = performance.now();
  let dt = (now - lastTime) / 1000;
  lastTime = now;
  if (dt > 0.1) dt = 0.016; // clamp

  // 1. Detect hands
  const handResult = detector.detect();
  const handsData = detector.getHands();
  updateRuntimeMetrics(dt, handsData.length, now);

  // 2. Build per-hand physics data with world positions
  const handsWithWorld = handsData.map(h => {
    const lms = h.landmarks;
    // Palm center from wrist(0), index-mcp(5), pinky-mcp(17)
    const cx = (lms[0].x + lms[5].x + lms[17].x) / 3;
    const cy = (lms[0].y + lms[5].y + lms[17].y) / 3;
    const palmWorld = visuals.screenToWorld(cx, cy);
    return { ...h, palmWorld };
  });

  // 3. Update physics
  physics.updateFromHands(handsWithWorld);
  physics.step(dt);

  // 4. Render
  const physicsData = physics.getObjectsData();
  const magnets = physics.getMagnets();
  visuals.update(handResult, handsWithWorld, magnets, physicsData, dt);

  // 5. HUD
  updateHUD(handsWithWorld, magnets, physics.getGrabbedCount());
}

// Start
init();
