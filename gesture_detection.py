"""
MagnoGlove - Gesture Detection Module
======================================
Captures webcam frames in a background thread, detects hand landmarks
using MediaPipe Hands, and classifies gestures using finger joint geometry.

Detected Gesture States
-----------------------
  OPEN_HAND   → All 4 fingers extended upward   → Magnet OFF
  CLOSED_FIST → All 4 fingers curled downward    → Magnet ON (full power)
  PINCH       → Thumb tip ≈ Index tip            → Precision Mode
  UNKNOWN     → No hand detected                 → Safe default (OFF)

MediaPipe Hand Landmark Reference (21 points)
----------------------------------------------
  0  = WRIST
  4  = THUMB_TIP       8  = INDEX_FINGER_TIP
  5  = INDEX_MCP       9  = MIDDLE_FINGER_MCP
  12 = MIDDLE_TIP      13 = RING_MCP
  16 = RING_TIP        17 = PINKY_MCP
  20 = PINKY_TIP

Classification Logic
--------------------
  1. Compute 2D Euclidean distance between THUMB_TIP and INDEX_TIP.
     If < PINCH_THRESHOLD → PINCH
  2. For each finger (Index/Middle/Ring/Pinky):
     Check if tip.y > mcp.y  (image y=0 is top → tip BELOW knuckle = curled)
  3. If ≥ 3 fingers curled → CLOSED_FIST, else OPEN_HAND
"""

import cv2
import mediapipe as mp
import numpy as np
import threading


# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

# Landmark indices
THUMB_TIP    = 4
INDEX_TIP    = 8
FINGER_TIPS  = [8, 12, 16, 20]   # Index, Middle, Ring, Pinky – tips
FINGER_MCPS  = [5,  9, 13, 17]   # Corresponding MCP (knuckle) joints

PINCH_THRESHOLD = 0.07            # Normalized distance units (0–1 range)
MIN_CURL_COUNT  = 3               # Fingers curled needed for CLOSED_FIST


# ─────────────────────────────────────────────────────────────────────────────
#  Gesture State Constants
# ─────────────────────────────────────────────────────────────────────────────

class GestureState:
    OPEN_HAND   = "OPEN_HAND"
    CLOSED_FIST = "CLOSED_FIST"
    PINCH       = "PINCH"
    UNKNOWN     = "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
#  Overlay Color Scheme
# ─────────────────────────────────────────────────────────────────────────────

_OVERLAY = {
    GestureState.CLOSED_FIST: {
        'label': "ON",
        'border': (0, 255, 80),
        'badge' : (0, 160, 50),
    },
    GestureState.PINCH: {
        'label': "PRECISION",
        'border': (0, 190, 255),
        'badge' : (0, 130, 200),
    },
    GestureState.OPEN_HAND: {
        'label': "OFF",
        'border': (60, 60, 200),
        'badge' : (40, 40, 160),
    },
    GestureState.UNKNOWN: {
        'label': "---",
        'border': (60, 60, 60),
        'badge' : (40, 40, 40),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  Gesture Detector Class
# ─────────────────────────────────────────────────────────────────────────────

class GestureDetector:
    """
    Runs webcam capture + hand landmark detection in a daemon thread.
    Writes the current gesture string to a thread-safe shared_state dict.

    Usage:
        detector = GestureDetector(shared_state)
        detector.start()          # begins background thread
        ...
        detector.stop()           # releases resources
    """

    def __init__(self, shared_state: dict, camera_index: int = 0):
        self.shared_state  = shared_state
        self.camera_index  = camera_index
        self.running       = False
        self.thread        = None
        self.cap           = None

        # ── MediaPipe setup ───────────────────────────────────────
        self._mp_hands = mp.solutions.hands
        self._mp_draw  = mp.solutions.drawing_utils
        self._mp_style = mp.solutions.drawing_styles

        self._hands = self._mp_hands.Hands(
            static_image_mode        = False,
            max_num_hands            = 1,          # track one hand for performance
            min_detection_confidence = 0.75,
            min_tracking_confidence  = 0.60,
        )

    # ─────────────── Public API ───────────────────────────────────

    def start(self):
        """Open the camera and launch the background detection thread."""
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"[GestureDetector] Cannot open camera index {self.camera_index}. "
                "Make sure a webcam is connected."
            )
        self.running = True
        self.thread  = threading.Thread(target=self._detection_loop, daemon=True)
        self.thread.start()
        print(f"  → Webcam ({self.camera_index}) opened — detection thread started.")

    def stop(self):
        """Signal the thread to stop and release all resources."""
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        cv2.destroyAllWindows()
        print("  → Webcam released.")

    # ─────────────── Gesture Classification ──────────────────────

    @staticmethod
    def _dist2d(a, b) -> float:
        """Normalized 2D Euclidean distance between two MediaPipe landmarks."""
        return np.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)

    def _classify(self, lm: list) -> str:
        """
        Classify hand landmark list into a GestureState string.

        Args:
            lm: list of 21 NormalizedLandmark objects from MediaPipe

        Returns:
            GestureState constant string
        """
        # Step 1 – Pinch: thumb tip close to index tip
        if self._dist2d(lm[THUMB_TIP], lm[INDEX_TIP]) < PINCH_THRESHOLD:
            return GestureState.PINCH

        # Step 2 – Count curled fingers
        # In image coordinates: y=0 top, y=1 bottom
        # A finger is curled when its tip sits lower (higher y) than its MCP joint
        curled = sum(
            1 for tip_i, mcp_i in zip(FINGER_TIPS, FINGER_MCPS)
            if lm[tip_i].y > lm[mcp_i].y
        )

        return GestureState.CLOSED_FIST if curled >= MIN_CURL_COUNT else GestureState.OPEN_HAND

    # ─────────────── Detection Loop (background thread) ──────────

    def _detection_loop(self):
        """Main capture-detect-display loop — runs in daemon thread."""
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue

            # Mirror so user sees a natural reflection
            frame = cv2.flip(frame, 1)
            h, w  = frame.shape[:2]

            # MediaPipe requires RGB input
            rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)

            gesture = GestureState.UNKNOWN

            if results.multi_hand_landmarks:
                for hand_lm in results.multi_hand_landmarks:
                    # Draw skeleton on frame
                    self._mp_draw.draw_landmarks(
                        frame, hand_lm,
                        self._mp_hands.HAND_CONNECTIONS,
                        self._mp_style.get_default_hand_landmarks_style(),
                        self._mp_style.get_default_hand_connections_style(),
                    )
                    gesture = self._classify(hand_lm.landmark)

            # Write result to shared state (thread-safe)
            with self.shared_state['lock']:
                self.shared_state['gesture'] = gesture

            # Render overlay and show window
            self._draw_overlay(frame, gesture, w, h)
            cv2.imshow("MagnoGlove | Gesture Detection  (press Q to quit)", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False
                break

        self.cap.release()
        cv2.destroyAllWindows()

    # ─────────────── Webcam Overlay UI ───────────────────────────

    @staticmethod
    def _draw_overlay(frame, gesture: str, w: int, h: int):
        """
        Render an informational HUD on top of the webcam frame.
        Shows gesture name, magnet state, and instructions.
        """
        cfg = _OVERLAY.get(gesture, _OVERLAY[GestureState.UNKNOWN])
        border = cfg['border']
        badge  = cfg['badge']
        label  = cfg['label']

        # ── Coloured border to signal state at a glance ───────────
        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), border, 5)

        # ── Info panel (top-left) ─────────────────────────────────
        cv2.rectangle(frame, (0, 0), (320, 100), (8, 8, 22), -1)
        cv2.rectangle(frame, (0, 0), (320, 100), badge, 2)

        font  = cv2.FONT_HERSHEY_DUPLEX
        font2 = cv2.FONT_HERSHEY_SIMPLEX

        cv2.putText(frame, "MagnoGlove",          (10, 28),  font,  0.75, (0, 210, 255), 1)
        cv2.putText(frame, f"Gesture : {gesture}", (10, 56),  font,  0.52, (210, 210, 210), 1)
        cv2.putText(frame, f"Magnet  : {label}",   (10, 82),  font,  0.52, badge, 1)

        # ── Instruction bar (bottom) ──────────────────────────────
        cv2.rectangle(frame, (0, h - 36), (w, h), (8, 8, 22), -1)
        cv2.putText(
            frame,
            "Fist = ON  |  Open = OFF  |  Pinch = Precision  |  Q = Quit",
            (10, h - 12), font2, 0.40, (130, 190, 255), 1,
        )
