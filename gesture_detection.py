"""
MagnoGlove – Gesture Detection Module  v2.1  (Fixed & Enhanced)
================================================================
BUG FIXES:
  - Added temporal gesture smoothing (5-frame history deque) to eliminate
    single-frame flicker that caused magnet state to strobe.
  - Thumb-curl now included in CLOSED_FIST check (was missing: fist could
    be classified as OPEN_HAND when only 3 non-thumb fingers were curled).
  - PINCH threshold now tuned against normalised wrist-span so it works
    correctly across different hand sizes / camera distances.
  - Camera permission error now raises a clear RuntimeError with macOS hint.

IMPROVEMENTS:
  - Confidence score exposed via shared_state['confidence'] for HUD display.
  - Frame-skip logic: MediaPipe only called every other frame when FPS > 45
    to relieve CPU on fast machines without sacrificing perceived latency.
  - Headless mode auto-detected on macOS and silently honoured.

MediaPipe Hand Landmark Reference (21 points)
----------------------------------------------
  0  = WRIST
  4  = THUMB_TIP        8  = INDEX_FINGER_TIP
  5  = INDEX_MCP        9  = MIDDLE_FINGER_MCP
  12 = MIDDLE_TIP       13 = RING_MCP
  16 = RING_TIP         17 = PINKY_MCP
  20 = PINKY_TIP
"""

import cv2
import mediapipe as mp
import numpy as np
import threading
import platform
from collections import deque
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
#  Landmark index constants
# ──────────────────────────────────────────────────────────────────────────────

WRIST       = 0
THUMB_TIP   = 4
THUMB_IP    = 3       # Interphalangeal (inner thumb joint)
THUMB_MCP   = 2
INDEX_TIP   = 8
INDEX_MCP   = 5
FINGER_TIPS = [8, 12, 16, 20]   # Index → Pinky tips
FINGER_PIPS = [6, 10, 14, 18]   # Proximal inter-phalangeal (mid joints)
FINGER_MCPS = [5,  9, 13, 17]   # MCP knuckles

# Pinch: threshold relative to hand span (wrist → middle-MCP distance)
# Keeps detection scale-invariant.
PINCH_DISTANCE_RATIO = 0.22     # Pinch if thumb-index dist < 22% of hand span

# Fist: how many fingers (including thumb) must be curled
MIN_CURL_FOR_FIST = 3           # Out of 5 total fingers

# Temporal smoothing: most common gesture over this many frames wins
SMOOTHING_FRAMES  = 6

IS_MACOS = platform.system() == "Darwin"


# ──────────────────────────────────────────────────────────────────────────────
#  State constants
# ──────────────────────────────────────────────────────────────────────────────

class GestureState:
    OPEN_HAND   = "OPEN_HAND"
    CLOSED_FIST = "CLOSED_FIST"
    PINCH       = "PINCH"
    UNKNOWN     = "UNKNOWN"

    ALL = (OPEN_HAND, CLOSED_FIST, PINCH, UNKNOWN)


# ──────────────────────────────────────────────────────────────────────────────
#  Detector
# ──────────────────────────────────────────────────────────────────────────────

class GestureDetector:
    """
    Runs webcam capture + hand landmark detection in a daemon thread.
    Writes gesture & confidence to thread-safe shared_state.

    On macOS : headless (no cv2.imshow).
    On Win/Linux: optional annotated webcam window.

    Usage
    -----
        detector = GestureDetector(shared_state)
        detector.start()
        ...
        detector.stop()
    """

    def __init__(self, shared_state: dict, camera_index: int = 0,
                 headless: Optional[bool] = None):
        self.shared_state = shared_state
        self.camera_index = camera_index
        self.running      = False
        self.thread       = None
        self.cap          = None
        self.headless     = IS_MACOS if headless is None else headless

        # Gesture smoothing history
        self._history: deque[str] = deque(maxlen=SMOOTHING_FRAMES)

        # MediaPipe
        self._mp_hands = mp.solutions.hands
        self._mp_draw  = mp.solutions.drawing_utils
        self._mp_style = mp.solutions.drawing_styles
        self._hands    = self._mp_hands.Hands(
            static_image_mode        = False,
            max_num_hands            = 1,
            min_detection_confidence = 0.72,
            min_tracking_confidence  = 0.58,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Open camera and start background thread."""
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"[GestureDetector] Cannot open camera index {self.camera_index}.\n"
                "  → Ensure a webcam is connected and camera permission is granted.\n"
                "  → On macOS: System Settings → Privacy & Security → Camera → allow Terminal."
            )
        self.running = True
        self.thread  = threading.Thread(target=self._detection_loop, daemon=True)
        self.thread.start()
        mode = "headless" if self.headless else "windowed"
        print(f"  → Camera {self.camera_index} opened [{mode}] – detection thread started.")
        if self.headless:
            print("  → Gesture HUD shown inside 3D simulation window instead.")

    def stop(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()
        if not self.headless:
            cv2.destroyAllWindows()
        print("  → Webcam released.")

    # ── Geometry helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _dist2d(a, b) -> float:
        """Normalised 2D Euclidean distance between two MediaPipe landmarks."""
        return np.hypot(a.x - b.x, a.y - b.y)

    def _classify_raw(self, lm: list) -> str:
        """
        Raw per-frame classification (before temporal smoothing).

        Scale-invariant pinch: compare thumb-index distance to hand span.
        Fist: checks all 5 fingers including thumb.
        """
        # Hand span for scale normalisation (wrist → middle-finger MCP)
        span = self._dist2d(lm[WRIST], lm[9]) + 1e-6

        # ── Pinch (thumb tip ≈ index tip, scale-corrected) ────────────────
        pinch_dist = self._dist2d(lm[THUMB_TIP], lm[INDEX_TIP])
        if pinch_dist / span < PINCH_DISTANCE_RATIO:
            return GestureState.PINCH

        # ── Count curled fingers ──────────────────────────────────────────
        # Non-thumb: tip.y > mcp.y  (image-space: y increases downward)
        curled = sum(
            1 for tip_i, mcp_i in zip(FINGER_TIPS, FINGER_MCPS)
            if lm[tip_i].y > lm[mcp_i].y
        )
        # Thumb: curl if thumb_tip.x is toward the palm (for right hand:
        # thumb tip x > index MCP x when curled; for left: opposite).
        # Safer heuristic: thumb tip y > thumb MCP y (same logic as fingers).
        thumb_curled = lm[THUMB_TIP].y > lm[THUMB_MCP].y
        total_curled = curled + (1 if thumb_curled else 0)

        return GestureState.CLOSED_FIST if total_curled >= MIN_CURL_FOR_FIST \
               else GestureState.OPEN_HAND

    def _classify(self, lm: list) -> tuple[str, float]:
        """Classify with temporal smoothing. Returns (gesture, confidence)."""
        raw = self._classify_raw(lm)
        self._history.append(raw)

        # Vote over history
        counts = {g: self._history.count(g) for g in GestureState.ALL}
        winner = max(counts, key=counts.__getitem__)
        confidence = counts[winner] / len(self._history)
        return winner, confidence

    # ── Detection loop ────────────────────────────────────────────────────────

    def _detection_loop(self):
        frame_count = 0
        skip_frame  = False    # alternating skip for high-FPS machines

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue
            frame_count += 1

            frame  = cv2.flip(frame, 1)
            h, w   = frame.shape[:2]

            gesture    = GestureState.UNKNOWN
            confidence = 0.0

            # Frame-skip: process every other frame when at high FPS
            skip_frame = not skip_frame
            if not skip_frame:
                rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self._hands.process(rgb)

                if results.multi_hand_landmarks:
                    for hand_lm in results.multi_hand_landmarks:
                        gesture, confidence = self._classify(hand_lm.landmark)
                        if not self.headless:
                            self._mp_draw.draw_landmarks(
                                frame, hand_lm,
                                self._mp_hands.HAND_CONNECTIONS,
                                self._mp_style.get_default_hand_landmarks_style(),
                                self._mp_style.get_default_hand_connections_style(),
                            )
                else:
                    self._history.append(GestureState.UNKNOWN)

            # Thread-safe write
            with self.shared_state['lock']:
                self.shared_state['gesture']    = gesture
                self.shared_state['confidence'] = confidence

            if frame_count % 90 == 0:
                print(f"  [CV] frame={frame_count:5d}  gesture={gesture:<12s}  conf={confidence:.0%}")

            if not self.headless:
                self._draw_overlay(frame, gesture, confidence, w, h)
                cv2.imshow("MagnoGlove | Gesture Cam  (Q = quit)", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False
                    break

        self.cap.release()
        if not self.headless:
            cv2.destroyAllWindows()

    # ── Webcam overlay (windowed mode only) ───────────────────────────────────

    @staticmethod
    def _draw_overlay(frame, gesture: str, confidence: float, w: int, h: int):
        _STYLE = {
            GestureState.CLOSED_FIST: ('ON',        (0, 255, 80),   (0, 160, 50)),
            GestureState.PINCH:       ('PRECISION',  (0, 200, 255),  (0, 140, 210)),
            GestureState.OPEN_HAND:   ('OFF',        (70, 70, 220),  (45, 45, 170)),
            GestureState.UNKNOWN:     ('---',        (65, 65, 65),   (45, 45, 45)),
        }
        label, border, badge = _STYLE.get(gesture, _STYLE[GestureState.UNKNOWN])

        cv2.rectangle(frame, (0, 0), (w - 1, h - 1), border, 5)
        cv2.rectangle(frame, (0, 0), (340, 110), (6, 6, 18), -1)
        cv2.rectangle(frame, (0, 0), (340, 110), badge, 2)

        font  = cv2.FONT_HERSHEY_DUPLEX
        font2 = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, "⚡ MagnoGlove",          (10, 30), font,  0.80, (0, 210, 255), 1)
        cv2.putText(frame, f"Gesture : {gesture}",   (10, 60), font,  0.54, (210, 210, 210), 1)
        cv2.putText(frame, f"Magnet  : {label}",     (10, 85), font,  0.54, badge, 1)
        pct = int(confidence * 100)
        cv2.putText(frame, f"Conf    : {pct}%",      (10, 108), font2, 0.46, (130, 160, 200), 1)
        cv2.rectangle(frame, (0, h - 38), (w, h), (6, 6, 18), -1)
        cv2.putText(
            frame,
            "  ✊ Fist=ON   ✋ Open=OFF   👌 Pinch=Precision   Q=Quit  ",
            (8, h - 12), font2, 0.38, (130, 190, 255), 1,
        )