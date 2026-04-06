"""
MagnoGlove - Gesture Detection Module  (macOS-compatible, headless)
=====================================================================
Captures webcam frames in a background thread, detects hand landmarks
using MediaPipe Hands, and classifies gestures using finger joint geometry.

macOS Note
----------
  On macOS, ALL GUI window calls (cv2.imshow, cv2.waitKey) must run on the
  MAIN thread.  Since Ursina already owns the main thread for its 3D window,
  we run the detector fully headless — no OpenCV display window.
  The gesture state is communicated entirely via the thread-safe shared_state
  dict; the Ursina HUD shows the live gesture name instead.

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
import platform


# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

THUMB_TIP       = 4
INDEX_TIP       = 8
FINGER_TIPS     = [8, 12, 16, 20]   # Index, Middle, Ring, Pinky – tips
FINGER_MCPS     = [5,  9, 13, 17]   # Corresponding MCP (knuckle) joints

PINCH_THRESHOLD = 0.07              # Normalized distance units (0–1 range)
MIN_CURL_COUNT  = 3                 # Fingers curled needed for CLOSED_FIST

# On macOS, cv2.imshow cannot be called from a background thread.
# Detect platform and disable the webcam preview window automatically.
IS_MACOS = platform.system() == "Darwin"


# ─────────────────────────────────────────────────────────────────────────────
#  Gesture State Constants
# ─────────────────────────────────────────────────────────────────────────────

class GestureState:
    OPEN_HAND   = "OPEN_HAND"
    CLOSED_FIST = "CLOSED_FIST"
    PINCH       = "PINCH"
    UNKNOWN     = "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
#  Gesture Detector Class
# ─────────────────────────────────────────────────────────────────────────────

class GestureDetector:
    """
    Runs webcam capture + hand landmark detection in a daemon thread.
    Writes the current gesture string to a thread-safe shared_state dict.

    On macOS: runs fully headless (no cv2.imshow).
    On Windows/Linux: shows an annotated webcam window.

    Usage:
        detector = GestureDetector(shared_state)
        detector.start()    # begins background thread
        ...
        detector.stop()     # releases resources
    """

    def __init__(self, shared_state: dict, camera_index: int = 0,
                 headless: bool = None):
        self.shared_state = shared_state
        self.camera_index = camera_index
        self.running      = False
        self.thread       = None
        self.cap          = None

        # Auto-detect headless mode: forced on macOS, optional elsewhere
        if headless is None:
            self.headless = IS_MACOS
        else:
            self.headless = headless

        # ── MediaPipe setup ───────────────────────────────────────
        self._mp_hands = mp.solutions.hands
        self._mp_draw  = mp.solutions.drawing_utils
        self._mp_style = mp.solutions.drawing_styles

        self._hands = self._mp_hands.Hands(
            static_image_mode        = False,
            max_num_hands            = 1,
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
                "Make sure a webcam is connected and camera permission is granted."
            )
        self.running = True
        self.thread  = threading.Thread(target=self._detection_loop, daemon=True)
        self.thread.start()

        mode = "headless (macOS)" if self.headless else "windowed"
        print(f"  → Webcam ({self.camera_index}) opened [{mode}] — detection thread started.")

        if self.headless:
            print("  → Webcam preview disabled on macOS (Ursina owns the main thread).")
            print("  → Gesture state shown live in the 3D simulation HUD instead.")

    def stop(self):
        """Signal the thread to stop and release all resources."""
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        if not self.headless:
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
        """
        Main capture-detect loop — runs in a daemon thread.

        Headless mode (macOS): purely reads frames and classifies gestures;
          never calls any cv2 display functions.
        Windowed mode (Win/Linux): additionally shows annotated webcam feed.
        """
        frame_count = 0

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue

            frame_count += 1

            # Mirror so user sees a natural reflection
            frame = cv2.flip(frame, 1)
            h, w  = frame.shape[:2]

            # MediaPipe requires RGB input
            rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)

            gesture = GestureState.UNKNOWN

            if results.multi_hand_landmarks:
                for hand_lm in results.multi_hand_landmarks:
                    gesture = self._classify(hand_lm.landmark)

                    # Draw skeleton only in windowed mode
                    if not self.headless:
                        self._mp_draw.draw_landmarks(
                            frame, hand_lm,
                            self._mp_hands.HAND_CONNECTIONS,
                            self._mp_style.get_default_hand_landmarks_style(),
                            self._mp_style.get_default_hand_connections_style(),
                        )

            # Write result to shared state (thread-safe)
            with self.shared_state['lock']:
                self.shared_state['gesture'] = gesture

            # ── Console heartbeat every 90 frames ─────────────────
            # Gives confirmation that detection is running headlessly
            if frame_count % 90 == 0:
                print(f"  [CV] frame={frame_count:5d}  gesture={gesture}")

            # ── Windowed display (non-macOS only) ─────────────────
            if not self.headless:
                self._draw_overlay(frame, gesture, w, h)
                cv2.imshow(
                    "MagnoGlove | Gesture Detection  (press Q to quit)", frame
                )
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False
                    break

        # Cleanup
        self.cap.release()
        if not self.headless:
            cv2.destroyAllWindows()

    # ─────────────── Webcam Overlay UI (windowed mode only) ──────

    @staticmethod
    def _draw_overlay(frame, gesture: str, w: int, h: int):
        """Render HUD on webcam frame (only called in windowed/non-macOS mode)."""

        _OVERLAY = {
            GestureState.CLOSED_FIST: ('ON',        (0, 255, 80),   (0, 160, 50)),
            GestureState.PINCH:       ('PRECISION',  (0, 190, 255),  (0, 130, 200)),
            GestureState.OPEN_HAND:   ('OFF',        (60, 60, 200),  (40, 40, 160)),
            GestureState.UNKNOWN:     ('---',        (60, 60, 60),   (40, 40, 40)),
        }
        label, border, badge = _OVERLAY.get(gesture, _OVERLAY[GestureState.UNKNOWN])

        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), border, 5)
        cv2.rectangle(frame, (0, 0), (320, 100), (8, 8, 22), -1)
        cv2.rectangle(frame, (0, 0), (320, 100), badge, 2)

        font  = cv2.FONT_HERSHEY_DUPLEX
        font2 = cv2.FONT_HERSHEY_SIMPLEX

        cv2.putText(frame, "MagnoGlove",           (10, 28), font,  0.75, (0, 210, 255), 1)
        cv2.putText(frame, f"Gesture : {gesture}",  (10, 56), font,  0.52, (210, 210, 210), 1)
        cv2.putText(frame, f"Magnet  : {label}",    (10, 82), font,  0.52, badge, 1)
        cv2.rectangle(frame, (0, h - 36), (w, h), (8, 8, 22), -1)
        cv2.putText(
            frame,
            "Fist = ON  |  Open = OFF  |  Pinch = Precision  |  Q = Quit",
            (10, h - 12), font2, 0.40, (130, 190, 255), 1,
        )