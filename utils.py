"""
MagnoGlove - Utility Functions
================================
Shared state management and helper math utilities used across all modules.
Thread-safe state dictionary acts as the communication bus between the
gesture detection thread and the Ursina simulation main thread.
"""

import threading


# ─────────────────────────────────────────────────────────────────────────────
#  Shared State Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_shared_state() -> dict:
    """
    Create a thread-safe shared state dictionary.

    This dictionary is the communication bridge between:
      - gesture_detection.py  (writer, background thread)
      - simulation_3d.py      (reader, Ursina main thread)

    Returns:
        dict: {
            'lock'    : threading.Lock  – must be held for any read/write
            'gesture' : str             – current GestureState constant
        }
    """
    return {
        'lock'   : threading.Lock(),
        'gesture': 'UNKNOWN',
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Math Helpers
# ─────────────────────────────────────────────────────────────────────────────

def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def remap(value: float,
          in_min: float, in_max: float,
          out_min: float, out_max: float) -> float:
    """
    Linearly remap a value from one range to another.
    Example: remap(0.5, 0, 1, 0, 100) → 50.0
    """
    t = clamp((value - in_min) / (in_max - in_min + 1e-9), 0.0, 1.0)
    return out_min + t * (out_max - out_min)


def smooth_lerp(current: float, target: float, speed: float, dt: float) -> float:
    """
    Exponential smooth approach (frame-rate independent lerp).
    Feels more natural than linear lerp for physics objects.
    """
    return current + (target - current) * clamp(speed * dt, 0.0, 1.0)
