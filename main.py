"""
MagnoGlove – Main Entry Point  v2.1
======================================
Gesture Controlled Electromagnetic Glove – MVP Software Demo

CHANGES:
  - dt is now passed to MagnetController.update() for smooth strength lerp.
  - Startup wait for camera warm-up extended to 0.8 s (was 0.6 s) to prevent
    false UNKNOWN gesture on first frame.
  - Ctrl-C now triggers a clean shutdown via KeyboardInterrupt handler.
  - Added Python version check for MediaPipe (requires ≤ 3.11).

Run
---
  python main.py

Controls
--------
  ✊  Closed Fist  →  Magnet ON        (full pull)
  ✋  Open Hand    →  Magnet OFF       (release)
  👌  Pinch        →  Precision mode   (gentle pull)
  ESC              →  Exit 3D window
  Q   (webcam win) →  Exit
"""

import sys
import time as _time

BANNER = r"""
  ╔══════════════════════════════════════════════════════════╗
  ║                                                          ║
  ║   ███╗   ███╗  █████╗  ██████╗ ███╗   ██╗  ██████╗     ║
  ║   ████╗ ████║ ██╔══██╗██╔════╝ ████╗  ██║ ██╔═══██╗    ║
  ║   ██╔████╔██║ ███████║██║  ███╗██╔██╗ ██║ ██║   ██║    ║
  ║   ██║╚██╔╝██║ ██╔══██║██║   ██║██║╚██╗██║ ██║   ██║    ║
  ║   ██║ ╚═╝ ██║ ██║  ██║╚██████╔╝██║ ╚████║ ╚██████╔╝    ║
  ║   ╚═╝     ╚═╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝  ╚═════╝    ║
  ║                                                          ║
  ║       Gesture Controlled Electromagnetic Glove           ║
  ║            MVP Software Demonstration  v2.1              ║
  ║                                                          ║
  ╚══════════════════════════════════════════════════════════╝
"""


def _check_python_version():
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 9):
        print(f"  ERROR: Python 3.9+ required (found {major}.{minor})")
        sys.exit(1)
    if major == 3 and minor > 11:
        print(f"  WARNING: MediaPipe may not support Python {major}.{minor}.")
        print("           If import fails, use Python 3.9–3.11.")


def main():
    print(BANNER)
    _check_python_version()

    # ── 1. Shared state ───────────────────────────────────────────────────────
    print("[1/3]  Initialising thread-safe shared state ...")
    from utils import create_shared_state
    shared_state = create_shared_state()
    print("       ✓ Shared state ready.\n")

    # ── 2. Gesture detection ──────────────────────────────────────────────────
    print("[2/3]  Starting gesture detection (webcam) ...")
    from gesture_detection import GestureDetector
    try:
        detector = GestureDetector(shared_state, camera_index=0)
        detector.start()
    except RuntimeError as exc:
        print(f"\n  ✗  {exc}")
        print("  Tip: connect a webcam and try again.\n")
        sys.exit(1)

    _time.sleep(0.8)   # camera warm-up
    print("       ✓ Detection thread running.\n")

    # ── 3. 3D Simulation ──────────────────────────────────────────────────────
    print("[3/3]  Launching 3D simulation window ...")
    print()
    print("  Controls:")
    print("    ✊  Closed Fist  →  Magnet ON        (full magnetic pull)")
    print("    ✋  Open Hand    →  Magnet OFF       (objects drop)")
    print("    👌  Pinch        →  Precision mode   (slow gentle pull)")
    print("    ESC             →  Exit simulation")
    print()

    try:
        from simulation_3d import MagnoGloveSimulation
        sim = MagnoGloveSimulation(shared_state)
        sim.run()   # blocks here – Ursina owns the main thread
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
    except Exception as exc:
        print(f"\n  Simulation error: {exc}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n  Shutting down gesture detection ...")
        detector.stop()
        print("  ✓ MagnoGlove session ended. Goodbye!\n")


if __name__ == "__main__":
    main()