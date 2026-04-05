"""
MagnoGlove - Magnet Control Logic
====================================
Translates hand gesture states into electromagnet behavior parameters.
Implements a simple physics model for magnetic attraction force.

System Flow
-----------
  Gesture (from CV module)
      ↓
  MagnetController.update(gesture)   ← sets state / strength / radius
      ↓
  MagnetController.attraction_force(obj_pos, magnet_pos)
      ↓
  Object velocity += force           ← applied each simulation frame

Magnet Presets
--------------
  OFF       → strength 0.0, radius 0.0  — electromagnet deactivated
  ON        → strength 1.0, radius 8.0  — full electromagnetic pull
  PRECISION → strength 0.35, radius 3.5 — reduced field (pinch mode)
"""

from gesture_detection import GestureState


# ─────────────────────────────────────────────────────────────────────────────
#  Magnet State Constants
# ─────────────────────────────────────────────────────────────────────────────

class MagnetState:
    OFF       = "OFF"
    ON        = "ON"
    PRECISION = "PRECISION"


# ─────────────────────────────────────────────────────────────────────────────
#  Magnet Presets (tunable)
# ─────────────────────────────────────────────────────────────────────────────

_PRESETS = {
    MagnetState.OFF: {
        'strength'    : 0.00,   # Force multiplier  [0 – 1]
        'radius'      : 0.00,   # Attraction radius (world units)
        'pull_speed'  : 0.00,   # Object move speed toward magnet
        'ring_scale'  : 0.00,   # Field ring max visual scale
        'glow_alpha'  : 0,      # Glow sphere transparency
    },
    MagnetState.ON: {
        'strength'    : 1.00,
        'radius'      : 9.00,
        'pull_speed'  : 7.00,
        'ring_scale'  : 3.20,
        'glow_alpha'  : 55,
    },
    MagnetState.PRECISION: {
        'strength'    : 0.35,
        'radius'      : 3.80,
        'pull_speed'  : 2.20,
        'ring_scale'  : 1.60,
        'glow_alpha'  : 35,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  MagnetController
# ─────────────────────────────────────────────────────────────────────────────

class MagnetController:
    """
    Manages electromagnet state and provides force calculations.

    Gesture → State Mapping:
      CLOSED_FIST  →  ON         (glove electromagnet fully activated)
      PINCH        →  PRECISION  (reduced field, fine manipulation)
      OPEN_HAND    →  OFF        (electromagnet deactivated, objects drop)
      UNKNOWN      →  OFF        (safe default)

    Physics Model:
      F = strength × pull_speed / (distance + damping)
      Simplified inverse-distance (not full inverse-square) for stability.
    """

    def __init__(self):
        self.state      : str   = MagnetState.OFF
        self.strength   : float = 0.0
        self.radius     : float = 0.0
        self.pull_speed : float = 0.0
        self.ring_scale : float = 0.0
        self.glow_alpha : int   = 0
        self._prev_state        = None

    # ─────────────── State Update ────────────────────────────────

    def update(self, gesture: str) -> str:
        """
        Evaluate gesture and update all magnet parameters.

        Args:
            gesture: GestureState constant string

        Returns:
            New MagnetState constant string
        """
        # Gesture → state mapping
        if gesture == GestureState.CLOSED_FIST:
            new_state = MagnetState.ON
        elif gesture == GestureState.PINCH:
            new_state = MagnetState.PRECISION
        else:
            new_state = MagnetState.OFF

        # Log transitions
        if new_state != self._prev_state:
            print(f"  [Magnet] {self._prev_state or 'INIT'} → {new_state}  "
                  f"(gesture: {gesture})")
            self._prev_state = new_state

        # Apply preset parameters
        preset          = _PRESETS[new_state]
        self.state      = new_state
        self.strength   = preset['strength']
        self.radius     = preset['radius']
        self.pull_speed = preset['pull_speed']
        self.ring_scale = preset['ring_scale']
        self.glow_alpha = preset['glow_alpha']

        return self.state

    # ─────────────── Query Helpers ───────────────────────────────

    def is_active(self) -> bool:
        """True when electromagnet has any pull force."""
        return self.state != MagnetState.OFF

    def get_pull_speed(self, distance: float) -> float:
        """
        Compute object pull speed at a given distance.
        Uses softened inverse-distance: speed = pull_speed / (d*0.4 + 0.6)
        The soft damping constant prevents infinite force at zero distance.

        Args:
            distance: Current distance from object to magnet (world units)

        Returns:
            Scalar speed value for this frame
        """
        if not self.is_active() or distance > self.radius:
            return 0.0
        damp = distance * 0.4 + 0.6
        return self.pull_speed / damp

    def get_info(self) -> dict:
        """Return a snapshot of current magnet parameters (for debug/UI)."""
        return {
            'state'     : self.state,
            'strength'  : self.strength,
            'radius'    : self.radius,
            'pull_speed': self.pull_speed,
        }
