import { FilesetResolver, HandLandmarker } from '@mediapipe/tasks-vision';

export class HandDetector {
  constructor(videoElement) {
    this.video = videoElement;
    this.handLandmarker = null;
    this.currentGesture = 'OPEN'; // OPEN, FIST, PINCH
    this.lastVideoTime = -1;
  }

  async initialize() {
    const vision = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.12/wasm"
    );

    // Try GPU delegate first, fall back to CPU if unavailable
    try {
      this.handLandmarker = await HandLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`,
          delegate: "GPU"
        },
        runningMode: "VIDEO",
        numHands: 1
      });
      console.log('[HandDetector] GPU delegate active');
    } catch (gpuErr) {
      console.warn('[HandDetector] GPU delegate failed, falling back to CPU:', gpuErr);
      this.handLandmarker = await HandLandmarker.createFromOptions(vision, {
        baseOptions: {
          modelAssetPath: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`,
          delegate: "CPU"
        },
        runningMode: "VIDEO",
        numHands: 1
      });
      console.log('[HandDetector] CPU delegate active');
    }
  }

  detect() {
    if (!this.handLandmarker || !this.video) return null;

    let startTimeMs = performance.now();
    if (this.video.currentTime !== this.lastVideoTime) {
      this.lastVideoTime = this.video.currentTime;
      const results = this.handLandmarker.detectForVideo(this.video, startTimeMs);
      this.processGestures(results);
      return results;
    }
    return null;
  }

  processGestures(results) {
    if (!results || !results.landmarks || results.landmarks.length === 0) {
      this.currentGesture = 'NONE';
      return;
    }

    const marks = results.landmarks[0];
    
    // We rely on simple heuristics for now
    const thumbTip = marks[4];
    const indexTip = marks[8];
    const middleTip = marks[12];
    const ringTip = marks[16];
    const pinkyTip = marks[20];

    const palmBase = marks[0];

    // Distance between thumb tip and index tip (approx Pinch)
    const pinchDist = Math.hypot(thumbTip.x - indexTip.x, thumbTip.y - indexTip.y);

    // To detect curled fingers, see if the tip is closer to the palm base than the MCP joint
    let curledCount = 0;
    const isCurled = (tip, mcp) => {
      const tipDist = Math.hypot(tip.x - palmBase.x, tip.y - palmBase.y);
      const mcpDist = Math.hypot(mcp.x - palmBase.x, mcp.y - palmBase.y);
      return tipDist < mcpDist * 1.1; // tip is close to palm
    };

    if (isCurled(indexTip, marks[5])) curledCount++;
    if (isCurled(middleTip, marks[9])) curledCount++;
    if (isCurled(ringTip, marks[13])) curledCount++;
    if (isCurled(pinkyTip, marks[17])) curledCount++;

    if (pinchDist < 0.05 && curledCount < 3) {
      this.currentGesture = 'PINCH';
    } else if (curledCount >= 3) {
      this.currentGesture = 'FIST';
    } else {
      this.currentGesture = 'OPEN';
    }
  }

  getCurrentGesture() {
    return this.currentGesture;
  }
}
