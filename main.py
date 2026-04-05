"""
MagnoGlove - Main Entry Point
================================
Gesture Controlled Electromagnetic Glove Simulation

Architecture
------------
  main.py  ──────────────────────────────────────────────────────────
              │                                      │
              ▼  (background daemon thread)          ▼  (main thread)
        GestureDetector                    MagnoGloveSimulation
              │                                      │
        OpenCV + MediaPipe                      Ursina 3D Engine
              │                                      │
              └──────── shared_state dict ───────────┘
                          (thread-safe)

Run Instructions
----------------
  python main.py

  Position your hand in front of the webcam:
    ✊  Close your fist   → Electromagnet ON  (objects fly up)
    ✋  Open your hand    → Electromagnet OFF (objects drop)
    👌  Pinch thumb+index → Precision mode   (slow attraction)

  Press ESC in the 3D window to exit.
  Press Q   in the webcam window to exit.
"""

import sys
import time as pytime


# ─────────────────────────────────────────────────────────────────────────────

BANNER = r"""
  ╔══════════════════════════════════════════════════════════╗
  ║                                                          ║
  ║      ███╗   ███╗ █████╗  ██████╗ ███╗   ██╗ ██████╗    ║
  ║      ████╗ ████║██╔══██╗██╔════╝ ████╗  ██║██╔═══██╗   ║
  ║      ██╔████╔██║███████║██║  ███╗██╔██╗ ██║██║   ██║   ║
  ║      ██║╚██╔╝██║██╔══██║██║   ██║██║╚██╗██║██║   ██║   ║
  ║      ██║ ╚═╝ ██║██║  ██║╚██████╔╝██║ ╚████║╚██████╔╝   ║
  ║      ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝    ║
  ║                                                          ║
  ║          Gesture Controlled Electromagnetic Glove        ║
  ║               MVP Software Demonstration                 ║
  ║                                                          ║
  ╚══════════════════════════════════════════════════════════╝
"""


def main():
    print(BANNER)

    # ── Step 1: Shared state ──────────────────────────────────────
    print("[1/3]  Initialising thread-safe shared state...")
    from utils import create_shared_state
    shared_state = create_shared_state()
    print("       ✓ Shared state ready.\n")

    # ── Step 2: Gesture detection ─────────────────────────────────
    print("[2/3]  Starting gesture detection (webcam)...")
    from gesture_detection import GestureDetector
    try:
        detector = GestureDetector(shared_state, camera_index=0)
        detector.start()
    except RuntimeError as e:
        print(f"\n  ERROR: {e}")
        print("  Please connect a webcam and try again.")
        sys.exit(1)

    pytime.sleep(0.6)   # Allow camera to warm up
    print("       ✓ Detection thread running.\n")

    # ── Step 3: 3D simulation ─────────────────────────────────────
    print("[3/3]  Launching 3D simulation window...")
    print()
    print("  Controls:")
    print("    ✊  Closed Fist  →  Magnet ON        (full magnetic pull)")
    print("    ✋  Open Hand    →  Magnet OFF       (release objects)")
    print("    👌  Pinch        →  Precision mode   (slow, gentle pull)")
    print("    ESC             →  Exit simulation")
    print("    Q (webcam win)  →  Exit")
    print()

    try:
        from simulation_3d import MagnoGloveSimulation
        sim = MagnoGloveSimulation(shared_state)
        sim.run()   # blocks here — Ursina owns the main thread
    except Exception as exc:
        print(f"\n  Simulation error: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        # ── Cleanup ───────────────────────────────────────────────
        print("\n  Shutting down gesture detection...")
        detector.stop()
        print("  ✓ MagnoGlove session ended. Goodbye!\n")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
