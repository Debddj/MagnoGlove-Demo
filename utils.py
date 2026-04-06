"""
MagnoGlove – Utility Functions  v2.1
======================================
Shared state management and helper math utilities.

CHANGES:
  - shared_state now includes 'confidence' key so the 3D HUD can show
    how certain the gesture classifier is.
  - Added vec3_lerp helper for smooth 3D position interpolation.
  - Added ease_out_cubic for ring animation easing.
"""

import threading
import math


# ──────────────────────────────────────────────────────────────────────────────
#  Shared State
# ──────────────────────────────────────────────────────────────────────────────

def create_shared_state() -> dict:
    """
    Thread-safe shared state dict bridging gesture detection → 3D sim.

    Keys
    ----
      lock       : threading.Lock  – acquire before any read or write
      gesture    : str             – current GestureState constant
      confidence : float           – classifier confidence 0.0–1.0
    """
    return {
        'lock'      : threading.Lock(),
        'gesture'   : 'UNKNOWN',
        'confidence': 0.0,
    }


# ──────────────────────────────────────────────────────────────────────────────
#  Math helpers
# ──────────────────────────────────────────────────────────────────────────────

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def remap(value: float,
          in_lo: float, in_hi: float,
          out_lo: float, out_hi: float) -> float:
    """Linearly remap value from [in_lo, in_hi] → [out_lo, out_hi]."""
    t = clamp((value - in_lo) / (in_hi - in_lo + 1e-9), 0.0, 1.0)
    return out_lo + t * (out_hi - out_lo)


def smooth_lerp(current: float, target: float, speed: float, dt: float) -> float:
    """Frame-rate-independent exponential smooth-step lerp."""
    return current + (target - current) * clamp(speed * dt, 0.0, 1.0)


def ease_out_cubic(t: float) -> float:
    """CSS-style ease-out cubic: fast start, slow end. Input/output 0–1."""
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_sine(t: float) -> float:
    """Smooth sinusoidal ease-in-out for animation loops."""
    return -(math.cos(math.pi * t) - 1.0) / 2.0