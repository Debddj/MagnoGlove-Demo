import { FilesetResolver, HandLandmarker } from '@mediapipe/tasks-vision';

export class HandDetector {
  constructor(videoElement) {
    this.video = videoElement;
    this.handLandmarker = null;
    this.lastVideoTime = -1;
    this.lastResults = null;

    // Per-hand gesture state: array of { gesture, landmarks, handedness }
    this.hands = [];
  }

  async initialize() {
    const vision = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.12/wasm"
    );

    const options = {
      baseOptions: {
        modelAssetPath: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`,
      },
      runningMode: "VIDEO",
      numHands: 2
    };

    // Try GPU first, fall back to CPU
    try {
      options.baseOptions.delegate = "GPU";
      this.handLandmarker = await HandLandmarker.createFromOptions(vision, options);
      console.log('[HandDetector] GPU delegate active');
    } catch (gpuErr) {
      console.warn('[HandDetector] GPU failed, falling back to CPU:', gpuErr);
      options.baseOptions.delegate = "CPU";
      this.handLandmarker = await HandLandmarker.createFromOptions(vision, options);
      console.log('[HandDetector] CPU delegate active');
    }
  }

  detect() {
    if (!this.handLandmarker || !this.video || this.video.readyState < 2) return null;

    const now = performance.now();
    if (this.video.currentTime === this.lastVideoTime) return this.lastResults;
    this.lastVideoTime = this.video.currentTime;

    const results = this.handLandmarker.detectForVideo(this.video, now);
    this.lastResults = results;
    this.processGestures(results);
    return results;
  }

  processGestures(results) {
    this.hands = [];
    if (!results || !results.landmarks || results.landmarks.length === 0) return;

    for (let h = 0; h < results.landmarks.length; h++) {
      const marks = results.landmarks[h];
      // MediaPipe handedness: "Left" means left hand in the raw image.
      // Since the video is mirrored, "Left" actually appears on the user's right side.
      // We label based on the user's perspective (mirrored).
      const rawLabel = results.handednesses[h]?.[0]?.categoryName || 'Unknown';
      // Mirror: MediaPipe "Left" = user's Right, "Right" = user's Left
      const userLabel = rawLabel === 'Left' ? 'Right' : 'Left';

      const gesture = this.classifyGesture(marks);

      this.hands.push({
        gesture,
        landmarks: marks,
        handedness: userLabel,
        index: h
      });
    }
  }

  classifyGesture(marks) {
    const thumbTip = marks[4];
    const indexTip = marks[8];
    const middleTip = marks[12];
    const ringTip = marks[16];
    const pinkyTip = marks[20];
    const palmBase = marks[0];

    // Pinch: thumb tip close to index tip
    const pinchDist = Math.hypot(thumbTip.x - indexTip.x, thumbTip.y - indexTip.y);

    // Curl detection: tip closer to wrist than MCP
    let curledCount = 0;
    const isCurled = (tip, mcp) => {
      const tipDist = Math.hypot(tip.x - palmBase.x, tip.y - palmBase.y);
      const mcpDist = Math.hypot(mcp.x - palmBase.x, mcp.y - palmBase.y);
      return tipDist < mcpDist * 1.1;
    };

    if (isCurled(indexTip, marks[5])) curledCount++;
    if (isCurled(middleTip, marks[9])) curledCount++;
    if (isCurled(ringTip, marks[13])) curledCount++;
    if (isCurled(pinkyTip, marks[17])) curledCount++;

    if (pinchDist < 0.06 && curledCount < 3) return 'PINCH';
    if (curledCount >= 3) return 'FIST';
    return 'OPEN';
  }

  /** Returns array of hand data objects */
  getHands() {
    return this.hands;
  }
}
