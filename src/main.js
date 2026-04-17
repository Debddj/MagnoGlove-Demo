import { HandDetector } from './HandDetector.js';
import { SceneVisuals } from './SceneVisuals.js';
import { MagnetPhysics } from './MagnetPhysics.js';
import { GeometryOverlay } from './GeometryOverlay.js';
import { AudioGuide } from './AudioGuide.js';

let video, canvas;
let detector, visuals, physics, geometry, audioGuide;
let isStarted = false;
let lastTime = 0;
let currentMode = 'magnet'; // 'magnet' | 'geometry'

// DOM Elements
const uiGesture   = document.getElementById('ui-gesture');
const uiMode      = document.getElementById('ui-mode');
const uiFlux      = document.getElementById('ui-flux');
const uiObjects   = document.getElementById('ui-objects');
const startBtn    = document.getElementById('start-btn');
const loadingOverlay = document.getElementById('loading');
const uiAiStatus  = document.getElementById('ui-ai-status');

const modeMagnetBtn   = document.getElementById('mode-magnet');
const modeGeometryBtn = document.getElementById('mode-geometry');
const panelMagnet     = document.getElementById('panel-magnet');
const panelGeometry   = document.getElementById('panel-geometry');

const audioToggleBtn = document.getElementById('audio-toggle');
const audioSkipBtn   = document.getElementById('audio-skip');
const subtitleBar    = document.getElementById('subtitle-bar');
const subtitleText   = document.getElementById('subtitle-text');
const subtitleProgress = document.getElementById('subtitle-progress');

// ══════════════════════════════════════════════════════════════
//  MODE SWITCHING
// ══════════════════════════════════════════════════════════════

function setMode(mode) {
  currentMode = mode;

  // Update button states
  modeMagnetBtn.classList.toggle('active', mode === 'magnet');
  modeGeometryBtn.classList.toggle('active', mode === 'geometry');

  // Toggle panels
  panelMagnet.classList.toggle('hidden', mode !== 'magnet');
  panelGeometry.classList.toggle('hidden', mode !== 'geometry');

  // Toggle 3D canvas visibility (hide physics objects in geometry mode)
  if (canvas) {
    canvas.style.display = mode === 'magnet' ? 'block' : 'none';
  }

  // Update HUD
  uiMode.textContent = mode === 'magnet' ? '🧲 MAGNET' : '📐 GEOMETRY';
  uiMode.className = `val ${mode === 'magnet' ? 'cyan' : 'amber'}`;

  console.log(`[Mode] Switched to ${mode.toUpperCase()}`);
}

// Mode button events
modeMagnetBtn.addEventListener('click', () => setMode('magnet'));
modeGeometryBtn.addEventListener('click', () => setMode('geometry'));

// ══════════════════════════════════════════════════════════════
//  AUDIO GUIDE
// ══════════════════════════════════════════════════════════════

function setupAudioGuide() {
  audioGuide = new AudioGuide();

  audioGuide.onStepChange = (step, idx) => {
    subtitleBar.classList.remove('hidden');
    subtitleText.textContent = step.subtitle;
    subtitleProgress.textContent = audioGuide.getProgress();
  };

  audioToggleBtn.addEventListener('click', () => {
    if (!audioGuide.isSpeaking() && !audioGuide.isMuted()) {
      // First click → start narration
      audioGuide.start();
      audioToggleBtn.textContent = '🔊';
      audioToggleBtn.classList.remove('muted');
    } else {
      const muted = audioGuide.toggleMute();
      audioToggleBtn.textContent = muted ? '🔇' : '🔊';
      audioToggleBtn.classList.toggle('muted', muted);
      if (muted) {
        subtitleBar.classList.add('hidden');
      }
    }
  });

  audioSkipBtn.addEventListener('click', () => {
    audioGuide.next();
  });
}

// ══════════════════════════════════════════════════════════════
//  INITIALIZATION
// ══════════════════════════════════════════════════════════════

async function init() {
  canvas = document.getElementById('three-canvas');
  video  = document.getElementById('webcam');

  setupAudioGuide();

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

  // Step 4: Init all subsystems
  physics  = new MagnetPhysics();
  visuals  = new SceneVisuals(canvas, video);
  geometry = new GeometryOverlay();
  visuals.initPhysicsObjects(physics.getObjectsInfo());

  loadingOverlay.style.display = 'none';
  isStarted = true;
  lastTime = performance.now();

  // Auto-start audio guide after a short delay
  setTimeout(() => {
    audioGuide.start();
    audioToggleBtn.textContent = '🔊';
  }, 1500);

  animate();
}

// ══════════════════════════════════════════════════════════════
//  HUD UPDATE
// ══════════════════════════════════════════════════════════════

function updateHUD(handsData, magnets, grabbedCount) {
  // Gesture display
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

  const handLabel = handsData.length === 2 ? 'DUAL' : handsData.length === 1 ? handsData[0].handedness.toUpperCase() : 'NONE';

  let gText, gClass;
  if (bestGesture === 'FIST')        { gText = `✊ FIST (${handLabel})`; gClass = 'cyan'; }
  else if (bestGesture === 'PINCH')  { gText = `👌 PINCH (${handLabel})`; gClass = 'amber'; }
  else if (handsData.length > 0)     { gText = `✋ OPEN (${handLabel})`; gClass = 'dim'; }
  else                               { gText = 'NO HANDS'; gClass = 'dim'; }

  uiGesture.textContent = gText;
  uiGesture.className = `val ${gClass}`;

  // Flux & objects (magnet mode specific but always updated)
  const maxStr = Math.max(magnets.Left.strength, magnets.Right.strength);
  const flux = (maxStr * 1.85).toFixed(2);
  uiFlux.textContent = currentMode === 'magnet' ? `${flux} T` : '—';
  uiFlux.className = `val ${currentMode === 'magnet' && maxStr > 0.1 ? (maxStr > 0.5 ? 'cyan' : 'amber') : 'dim'}`;

  uiObjects.textContent = currentMode === 'magnet' ? `${grabbedCount} / 15` : '—';
  uiObjects.className = `val ${currentMode === 'magnet' && grabbedCount > 0 ? 'green' : 'dim'}`;

  // Subtitle update
  if (audioGuide && audioGuide.isSpeaking()) {
    const sub = audioGuide.getCurrentSubtitle();
    if (sub) {
      subtitleBar.classList.remove('hidden');
      subtitleText.textContent = sub;
      subtitleProgress.textContent = audioGuide.getProgress();
    }
  } else if (!audioGuide || !audioGuide.isMuted()) {
    subtitleBar.classList.add('hidden');
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
  if (dt > 0.1) dt = 0.016;

  // 1. Detect hands
  const handResult = detector.detect();
  const handsData = detector.getHands();

  // 2. Build world positions for each hand
  const handsWithWorld = handsData.map(h => {
    const lms = h.landmarks;
    const cx = (lms[0].x + lms[5].x + lms[17].x) / 3;
    const cy = (lms[0].y + lms[5].y + lms[17].y) / 3;
    const palmWorld = visuals.screenToWorld(cx, cy);
    return { ...h, palmWorld };
  });

  if (currentMode === 'magnet') {
    // ── MAGNET MODE ──
    physics.updateFromHands(handsWithWorld);
    physics.step(dt);

    const physicsData = physics.getObjectsData();
    const magnets = physics.getMagnets();
    visuals.update(handResult, handsWithWorld, magnets, physicsData, dt);

    // Clear geometry canvas
    geometry.update([]);

    updateHUD(handsWithWorld, magnets, physics.getGrabbedCount());

  } else {
    // ── GEOMETRY MODE ──
    // Still update physics minimally (objects at rest)
    const magnets = physics.getMagnets();

    // Update geometry overlay with raw hand data
    geometry.update(handsData);

    // Render scene with hands only (no magnet effects)
    physics.updateFromHands([]); // no magnetic force
    physics.step(dt);
    visuals.update(handResult, handsWithWorld, magnets, physics.getObjectsData(), dt);

    updateHUD(handsWithWorld, magnets, 0);
  }
}

// Start
init();
