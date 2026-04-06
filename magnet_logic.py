"""
MagnoGlove – Magnet Control Logic  v3.1 (Enterprise Physics Refactor)
=============================================================
"""

from typing import Optional
from gesture_detection import GestureState


# ──────────────────────────────────────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────────────────────────────────────

STRENGTH_RAMP_UP   = 5.5   # lerp speed factor when activating
STRENGTH_RAMP_DOWN = 3.0   # lerp speed factor when deactivating


class MagnetState:
    OFF       = "OFF"
    ON        = "ON"
    PRECISION = "PRECISION"


# ── TUNED PHYSICS PRESETS ──
_PRESETS: dict[str, dict] = {
    MagnetState.OFF: {
        'target_strength': 0.00,
        'radius'         : 0.00,
        'pull_speed'     : 0.00,
        'ring_scale'     : 0.00,
        'glow_alpha'     : 0,
    },
    MagnetState.ON: {
        'target_strength': 1.00,
        'radius'         : 20.0,   # Expanded to reach all table corners
        'pull_speed'     : 280.0,  # Scaled up for proper force accumulation
        'ring_scale'     : 3.30,
        'glow_alpha'     : 60,
    },
    MagnetState.PRECISION: {
        'target_strength': 0.35,
        'radius'         : 15.0,   # Precision should still reach the table
        'pull_speed'     : 95.0,   # Slower, gentler pull
        'ring_scale'     : 1.65,
        'glow_alpha'     : 38,
    },
}

# Gesture → MagnetState mapping
_GESTURE_MAP: dict[str, str] = {
    GestureState.CLOSED_FIST: MagnetState.ON,
    GestureState.PINCH:       MagnetState.PRECISION,
    GestureState.OPEN_HAND:   MagnetState.OFF,
    GestureState.UNKNOWN:     MagnetState.OFF,   # safe default
}


# ──────────────────────────────────────────────────────────────────────────────
#  MagnetController
# ──────────────────────────────────────────────────────────────────────────────

class MagnetController:
    """
    Manages electromagnet state and provides force calculations.

    Call update(gesture, dt) every frame; the controller smoothly ramps
    strength between 0 and the preset target using exponential lerp.
    """

    def __init__(self):
        self.state          : str   = MagnetState.OFF
        self.strength       : float = 0.0   # live lerped value [0–1]
        self._target        : float = 0.0
        self.radius         : float = 0.0
        self.pull_speed     : float = 0.0
        self.ring_scale     : float = 0.0
        self.glow_alpha     : int   = 0
        self._prev_state    : Optional[str] = None

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, gesture: str, dt: float = 0.016) -> str:
        """
        Evaluate gesture, update state, smoothly lerp strength.
        """
        new_state = _GESTURE_MAP.get(gesture, MagnetState.OFF)

        if new_state != self._prev_state:
            print(f"  [Magnet] {self._prev_state or 'INIT'} -> {new_state}"
                  f"  (gesture: {gesture})")
            self._prev_state = new_state

        preset = _PRESETS[new_state]
        self.state      = new_state
        self._target    = preset['target_strength']
        self.radius     = preset['radius']
        self.pull_speed = preset['pull_speed']
        self.ring_scale = preset['ring_scale']
        self.glow_alpha = preset['glow_alpha']

        # Smooth strength ramp: faster when activating, slower when releasing
        speed = STRENGTH_RAMP_UP if self._target > self.strength else STRENGTH_RAMP_DOWN
        alpha = min(speed * dt, 1.0)
        self.strength += (self._target - self.strength) * alpha

        return self.state

    # ── Query helpers ─────────────────────────────────────────────────────────

    def is_active(self) -> bool:
        return self.strength > 0.01

    def effective_radius(self) -> float:
        """Live attraction radius."""
        return self.radius

    def get_pull_speed(self, distance: float) -> float:
        """
        Pull speed at given distance, using softened inverse-distance model.
        Returns 0 if outside effective radius or magnet is inactive.
        """
        if not self.is_active() or distance > self.radius:
            return 0.0
        # Softened inverse-square law for realistic magnetic pull
        damp = (distance * 0.5) ** 2 + 1.0
        return (self.pull_speed * self.strength) / damp

    def get_info(self) -> dict:
        """Snapshot of current live magnet parameters for debug / HUD."""
        return {
            'state'     : self.state,
            'strength'  : round(self.strength, 3),
            'radius'    : round(self.effective_radius(), 2),
            'pull_speed': round(self.pull_speed, 2),
            'glow_alpha': self.glow_alpha,
        }