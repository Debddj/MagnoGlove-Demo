"""
MagnoGlove - 3D Simulation Module
====================================
Builds and runs the interactive 3D scene using the Ursina game engine.
All entities, animations, physics, and UI are defined here.

Scene Layout (world-space Y axis = up)
---------------------------------------
  y =  2.5  →  Glove / electromagnet placeholder
  y = -2.55 →  Metal sphere resting positions (on table)
  y = -3.0  →  Table surface
  y =  ↑    →  Background panel and decorative elements

Visual Effects by State
-----------------------
  Magnet ON        →  Blue expanding rings + blue glow pulse on glove
  Magnet PRECISION →  Amber smaller rings + amber glow
  Magnet OFF       →  All effects hidden, objects obey gravity

Threading Notes
---------------
  Ursina requires its app.run() on the MAIN THREAD.
  Gesture detection runs in a daemon background thread and writes to
  shared_state['gesture']. SimController.update() reads it each frame.
"""

from ursina import *
import math

from magnet_logic import MagnetController, MagnetState
from gesture_detection import GestureState


# ─────────────────────────────────────────────────────────────────────────────
#  Color Palette
# ─────────────────────────────────────────────────────────────────────────────

C_BG           = color.rgb(8,  10, 22)
C_TABLE        = color.rgb(38, 26, 14)
C_TABLE_TOP    = color.rgb(52, 36, 20)
C_GRID         = color.rgba(35, 45, 80, 75)

C_GLOVE_IDLE   = color.rgb(40, 80, 175)
C_GLOVE_ON     = color.rgb(0, 145, 255)
C_GLOVE_PREC   = color.rgb(220, 170, 0)
C_FINGER       = color.rgb(30, 65, 150)
C_COIL         = color.rgb(200, 160, 20)

C_METAL        = color.rgb(175, 180, 200)
C_METAL_PULL   = color.rgb(200, 220, 255)
C_METAL_LOCK   = color.rgb(180, 220, 255)

C_RING_ON      = (0, 160, 255)
C_RING_PREC    = (255, 200, 0)

C_PANEL_BG     = color.rgba(8, 10, 30, 235)
C_PANEL_BORDER = color.rgba(0, 175, 255, 90)

C_UI_TITLE     = color.rgb(0, 200, 255)
C_UI_ON        = color.rgb(0, 255, 120)
C_UI_PREC      = color.rgb(255, 215, 0)
C_UI_OFF       = color.rgb(255, 75, 75)
C_UI_WHITE     = color.rgb(215, 215, 225)
C_UI_DIM       = color.rgb(110, 110, 130)

C_CONSOLE      = color.rgb(18, 22, 42)
C_SCREEN       = color.rgba(0, 180, 255, 110)

# ─────────────────────────────────────────────────────────────────────────────
#  Scene / Physics Constants
# ─────────────────────────────────────────────────────────────────────────────

TABLE_Y      = -3.0          # Top surface of table (world Y)
OBJECT_Y     = -2.58         # Resting Y for metal spheres
GLOVE_POS    = Vec3(0, 2.5, 0)
ATTACH_DIST  = 0.55          # Distance at which object snaps to glove
GRAVITY      = -9.8          # World-space gravity (Y axis, units/s²)
DAMPING      = 0.87          # Velocity damping coefficient per frame
RING_COUNT   = 5             # Number of field ring layers
RING_SPEED   = {MagnetState.ON: 2.1, MagnetState.PRECISION: 1.3}


# ─────────────────────────────────────────────────────────────────────────────
#  Simulation Controller Entity
# ─────────────────────────────────────────────────────────────────────────────

class SimController(Entity):
    """
    Custom Ursina Entity.  Its update() method is called by Ursina every frame.
    Owns all simulation logic: gesture reading, physics, visual effects, UI sync.
    """

    def __init__(self, shared_state: dict, magnet: MagnetController):
        super().__init__()
        self.shared_state = shared_state
        self.magnet       = magnet

        # Runtime state
        self.current_gesture  = GestureState.UNKNOWN
        self.current_magnet   = MagnetState.OFF
        self._ring_timer      = 0.0
        self._pulse_timer     = 0.0

        # Scene entity references (populated by MagnoGloveSimulation)
        self.glove         = None
        self.metal_objects = []    # list of Entity with extra attrs
        self.rings         = []    # field ring entities
        self.glow_sphere   = None

        # UI text references (populated by MagnoGloveSimulation)
        self.ui_gesture = None
        self.ui_magnet  = None
        self.ui_objects = None
        self.ui_fps     = None

    # ─────────────── Ursina Update (called every frame) ──────────

    def update(self):
        dt = time.dt   # Ursina's per-frame delta time (seconds)

        # 1. Read latest gesture (thread-safe)
        with self.shared_state['lock']:
            self.current_gesture = self.shared_state['gesture']

        # 2. Update electromagnet state machine
        self.current_magnet = self.magnet.update(self.current_gesture)

        # 3. Advance animation timers
        self._ring_timer  += dt
        self._pulse_timer += dt

        # 4. Visual effects
        self._update_glove_effects(dt)

        # 5. Metal object physics
        self._update_physics(dt)

        # 6. HUD
        self._update_ui()

    # ─────────────── Visual Effects ──────────────────────────────

    def _update_glove_effects(self, dt: float):
        """Drive magnetic field rings and glove glow based on magnet state."""

        if self.current_magnet == MagnetState.OFF:
            # ── No field – reset all effects ─────────────────────
            self.glove.color = C_GLOVE_IDLE
            for ring in self.rings:
                ring.scale = 0
                ring.color = color.clear
            if self.glow_sphere:
                self.glow_sphere.scale = 0
                self.glow_sphere.color = color.clear
            return

        # ── Active states (ON or PRECISION) ──────────────────────
        if self.current_magnet == MagnetState.ON:
            glove_col  = C_GLOVE_ON
            ring_rgb   = C_RING_ON
            ring_speed = RING_SPEED[MagnetState.ON]
            ring_max_s = self.magnet.ring_scale
            ring_alpha = 210
            glow_rgb   = (0, 100, 255)
            glow_a     = self.magnet.glow_alpha
        else:  # PRECISION
            glove_col  = C_GLOVE_PREC
            ring_rgb   = C_RING_PREC
            ring_speed = RING_SPEED[MagnetState.PRECISION]
            ring_max_s = self.magnet.ring_scale
            ring_alpha = 155
            glow_rgb   = (255, 185, 0)
            glow_a     = self.magnet.glow_alpha

        self.glove.color = glove_col

        # ── Expanding ring animation ──────────────────────────────
        # Each ring is offset in phase so they travel outward sequentially.
        for i, ring in enumerate(self.rings):
            phase = (self._ring_timer * ring_speed + i / RING_COUNT) % 1.0
            s     = max(0.05, phase * ring_max_s)
            a     = int(ring_alpha * (1.0 - phase))   # fade as they expand

            ring.position = self.glove.position
            ring.scale    = s
            ring.color    = color.rgba(*ring_rgb, a)

        # ── Pulsing glow sphere ───────────────────────────────────
        if self.glow_sphere:
            pulse = 1.0 + 0.22 * math.sin(self._pulse_timer * 6.5)
            self.glow_sphere.position = self.glove.position
            self.glow_sphere.scale    = 1.7 * pulse
            self.glow_sphere.color    = color.rgba(*glow_rgb, glow_a)

    # ─────────────── Physics ─────────────────────────────────────

    def _update_physics(self, dt: float):
        """
        Simulate magnetic attraction and gravity for each metal object.

        When ACTIVE:
          - Compute pull speed based on distance (inverse-distance model)
          - Move object toward glove position each frame
          - If within ATTACH_DIST, snap/orbit around glove

        When OFF:
          - Apply gravity downward until table surface
          - Smoothly slide back to resting position
        """
        for idx, obj in enumerate(self.metal_objects):
            if self.magnet.is_active():
                direction = self.glove.position - obj.position
                dist      = direction.length()

                if dist < ATTACH_DIST:
                    # ── Attached to glove ─────────────────────────
                    # Spread objects horizontally around glove underside
                    n      = len(self.metal_objects)
                    spread = (idx - n / 2) * 0.45
                    target = self.glove.position + Vec3(spread, -0.85, 0)

                    obj.position  = lerp(obj.position, target, dt * 9)
                    obj.velocity  = Vec3(0, 0, 0)
                    obj.attached  = True
                    obj.color     = C_METAL_LOCK

                    # Rotate while held (satisfying visual)
                    obj.rotation_y += 140 * dt

                else:
                    # ── Flying toward glove ───────────────────────
                    speed      = self.magnet.get_pull_speed(dist)
                    obj.velocity += direction.normalized() * speed * dt
                    obj.velocity *= DAMPING
                    obj.position += obj.velocity * dt
                    obj.attached  = False

                    # Colour shifts bluer as it approaches
                    t = max(0.0, 1.0 - dist / 5.0)
                    obj.color = color.rgb(
                        int(175 + t * 25),
                        int(180 + t * 40),
                        int(200 + t * 55),
                    )

            else:
                # ── Gravity & return to rest ──────────────────────
                obj.attached = False

                if obj.position.y > OBJECT_Y + 0.01:
                    # Still airborne – apply gravity
                    obj.velocity.y += GRAVITY * dt
                    obj.velocity   *= 0.97
                    obj.position   += obj.velocity * dt

                    if obj.position.y <= OBJECT_Y:
                        obj.position.y = OBJECT_Y
                        obj.velocity   = Vec3(0, 0, 0)
                else:
                    # On table – slide back to resting XZ position
                    obj.position.y = OBJECT_Y
                    obj.velocity   = Vec3(0, 0, 0)
                    obj.position.x = lerp(obj.position.x, obj.rest_pos.x, dt * 1.8)
                    obj.position.z = lerp(obj.position.z, obj.rest_pos.z, dt * 1.8)

                obj.color = lerp(obj.color, C_METAL, dt * 2.5) if hasattr(obj.color, '__iter__') else C_METAL

    # ─────────────── HUD Update ──────────────────────────────────

    def _update_ui(self):
        if not self.ui_gesture:
            return

        self.ui_gesture.text = f"Gesture  :  {self.current_gesture}"

        if self.current_magnet == MagnetState.ON:
            self.ui_magnet.text  = "Magnet   :  ON  ●"
            self.ui_magnet.color = C_UI_ON
        elif self.current_magnet == MagnetState.PRECISION:
            self.ui_magnet.text  = "Magnet   :  PRECISION  ◉"
            self.ui_magnet.color = C_UI_PREC
        else:
            self.ui_magnet.text  = "Magnet   :  OFF  ○"
            self.ui_magnet.color = C_UI_OFF

        attached = sum(1 for o in self.metal_objects if getattr(o, 'attached', False))
        if attached:
            self.ui_objects.text  = f"Objects  :  {attached} attracted ↑"
            self.ui_objects.color = C_UI_ON
        elif self.magnet.is_active():
            self.ui_objects.text  = "Objects  :  Approaching..."
            self.ui_objects.color = C_UI_PREC
        else:
            self.ui_objects.text  = "Objects  :  Idle"
            self.ui_objects.color = C_UI_WHITE

        safe_dt = max(time.dt, 0.001)
        self.ui_fps.text = f"FPS      :  {int(1 / safe_dt)}"


# ─────────────────────────────────────────────────────────────────────────────
#  Main Simulation Class
# ─────────────────────────────────────────────────────────────────────────────

class MagnoGloveSimulation:
    """
    Orchestrates Ursina setup, scene construction, and the main run loop.

    Usage:
        sim = MagnoGloveSimulation(shared_state)
        sim.run()   # blocks until window is closed
    """

    def __init__(self, shared_state: dict):
        self.shared_state = shared_state
        self.magnet       = MagnetController()

        # ── Init Ursina ───────────────────────────────────────────
        self.app = Ursina(
            title     = "MagnoGlove – Electromagnetic Glove Simulation",
            borderless = False,
            fullscreen = False,
        )
        window.color = C_BG

        # Build scene and UI; wire SimController
        self._build_scene()
        self._build_ui()

    # ─────────────── Scene Construction ──────────────────────────

    def _build_scene(self):
        """Construct every 3D entity in the world."""

        # ── Camera ───────────────────────────────────────────────
        camera.position  = Vec3(0, 2.2, -14)
        camera.rotation_x = -7

        # ── Lighting ─────────────────────────────────────────────
        AmbientLight(color=color.rgba(75, 80, 110, 255))
        dl = DirectionalLight()
        dl.look_at(Vec3(1, -2, 1))

        # ── Far background panel ──────────────────────────────────
        Entity(
            model    = 'quad',
            color    = color.rgb(10, 12, 28),
            scale    = (50, 28),
            position = Vec3(0, 1, 14),
        )

        # ── Workspace Table ───────────────────────────────────────
        # Main slab
        Entity(
            model    = 'cube',
            color    = C_TABLE,
            scale    = (15, 0.22, 9),
            position = Vec3(0, TABLE_Y - 0.11, 0),
        )
        # Bright top surface
        Entity(
            model    = 'cube',
            color    = C_TABLE_TOP,
            scale    = (15, 0.04, 9),
            position = Vec3(0, TABLE_Y + 0.02, 0),
        )
        # Four legs
        for lx, lz in [(-6.8, -4.0), (6.8, -4.0), (-6.8, 4.0), (6.8, 4.0)]:
            Entity(
                model    = 'cube',
                color    = color.rgb(28, 18, 10),
                scale    = (0.18, 3.2, 0.18),
                position = Vec3(lx, TABLE_Y - 1.6, lz),
            )

        # Grid overlay on table top (tech aesthetic)
        for xi in range(-7, 8):
            Entity(model='cube', color=C_GRID,
                   scale=(0.012, 0.008, 9),
                   position=Vec3(xi, TABLE_Y + 0.065, 0))
        for zi in range(-4, 5):
            Entity(model='cube', color=C_GRID,
                   scale=(15, 0.008, 0.012),
                   position=Vec3(0, TABLE_Y + 0.065, zi))

        # ── Glove / Electromagnet ─────────────────────────────────
        glove = Entity(
            model    = 'cube',
            color    = C_GLOVE_IDLE,
            scale    = (1.5, 0.42, 0.95),
            position = GLOVE_POS,
        )

        # Finger segments
        for fx in [-0.45, -0.15, 0.15, 0.45]:
            Entity(model='cube', color=C_FINGER,
                   scale=(0.20, 0.52, 0.24),
                   position=Vec3(GLOVE_POS.x + fx,
                                 GLOVE_POS.y + 0.47,
                                 GLOVE_POS.z))
        # Thumb
        Entity(model='cube', color=C_FINGER,
               scale=(0.24, 0.19, 0.40),
               position=Vec3(GLOVE_POS.x - 0.78,
                              GLOVE_POS.y + 0.06,
                              GLOVE_POS.z))

        # Gold coil band (electromagnet winding indicator)
        Entity(model='cube', color=C_COIL,
               scale=(1.35, 0.07, 1.00),
               position=Vec3(GLOVE_POS.x, GLOVE_POS.y - 0.01, GLOVE_POS.z))

        # Thin cable going up (suspends the glove from above)
        Entity(model='cube', color=color.rgb(50, 50, 70),
               scale=(0.06, 3.5, 0.06),
               position=Vec3(GLOVE_POS.x, GLOVE_POS.y + 2.2, GLOVE_POS.z))

        # ── Magnetic Field Rings ──────────────────────────────────
        rings = []
        for _ in range(RING_COUNT):
            r = Entity(
                model    = 'circle',    # built-in Ursina flat disc
                color    = color.clear,
                scale    = 0,
                position = GLOVE_POS,
                rotation = Vec3(90, 0, 0),   # flat in XZ plane
            )
            rings.append(r)

        # ── Glow Sphere (halo around glove) ──────────────────────
        glow = Entity(
            model    = 'sphere',
            color    = color.clear,
            scale    = 0,
            position = GLOVE_POS,
        )

        # ── Metallic Objects (spheres on table) ───────────────────
        rest_positions = [
            Vec3(-3.2, OBJECT_Y, -1.0),
            Vec3(-1.6, OBJECT_Y,  1.2),
            Vec3( 0.0, OBJECT_Y, -1.8),
            Vec3( 1.4, OBJECT_Y,  0.6),
            Vec3( 3.0, OBJECT_Y, -0.6),
            Vec3(-2.2, OBJECT_Y,  2.2),
            Vec3( 2.4, OBJECT_Y,  2.0),
        ]

        metal_objects = []
        for pos in rest_positions:
            obj = Entity(
                model    = 'sphere',
                color    = C_METAL,
                scale    = 0.40,
                position = Vec3(pos),
            )
            # Extra physics attributes
            obj.rest_pos = Vec3(pos)
            obj.velocity = Vec3(0, 0, 0)
            obj.attached = False
            metal_objects.append(obj)

        # Small decorative bolts (flat cylinders, scattered)
        bolt_positions = [Vec3(-4.5, OBJECT_Y + 0.04, 0.5),
                          Vec3( 4.2, OBJECT_Y + 0.04, 1.5)]
        for bp in bolt_positions:
            Entity(model='cylinder', color=color.rgb(160, 165, 175),
                   scale=(0.15, 0.08, 0.15), position=bp)

        # ── Lab Console (back wall decoration) ───────────────────
        Entity(model='cube', color=C_CONSOLE,
               scale=(15, 2.8, 0.6),
               position=Vec3(0, TABLE_Y + 1.4, 4.2))
        # Screen panels on console
        for sx in [-4.5, 0, 4.5]:
            Entity(model='quad', color=C_SCREEN,
                   scale=(3.0, 1.2),
                   position=Vec3(sx, TABLE_Y + 1.7, 3.89))
            # Horizontal scan lines on screens
            for row in [-0.35, -0.15, 0.05, 0.25]:
                Entity(model='quad',
                       color=color.rgba(0, 200, 255, 40),
                       scale=(2.8, 0.04),
                       position=Vec3(sx, TABLE_Y + 1.7 + row, 3.88))

        # ── Wire up controller ────────────────────────────────────
        self.ctrl               = SimController(self.shared_state, self.magnet)
        self.ctrl.glove         = glove
        self.ctrl.metal_objects = metal_objects
        self.ctrl.rings         = rings
        self.ctrl.glow_sphere   = glow

    # ─────────────── HUD Construction ────────────────────────────

    def _build_ui(self):
        """Build the 2D heads-up display overlay in camera.ui space."""

        # Panel background + border
        Entity(parent=camera.ui, model='quad', color=C_PANEL_BG,
               scale=(0.40, 0.33), position=Vec3(-0.595, 0.365, 0))
        Entity(parent=camera.ui, model='quad', color=C_PANEL_BORDER,
               scale=(0.404, 0.334), position=Vec3(-0.595, 0.365, 0))

        # Title
        Text(text="⚡  MagnoGlove  ⚡",
             parent=camera.ui, scale=1.30, color=C_UI_TITLE,
             position=Vec3(-0.785, 0.475))

        Text(text="━" * 30,
             parent=camera.ui, scale=0.88,
             color=color.rgba(0, 175, 255, 100),
             position=Vec3(-0.785, 0.450))

        self.ctrl.ui_gesture = Text(
            text     = "Gesture  :  --",
            parent   = camera.ui, scale=0.92, color=C_UI_WHITE,
            position = Vec3(-0.785, 0.425))

        self.ctrl.ui_magnet = Text(
            text     = "Magnet   :  OFF  ○",
            parent   = camera.ui, scale=0.92, color=C_UI_OFF,
            position = Vec3(-0.785, 0.400))

        self.ctrl.ui_objects = Text(
            text     = "Objects  :  Idle",
            parent   = camera.ui, scale=0.92, color=C_UI_WHITE,
            position = Vec3(-0.785, 0.375))

        Text(text="━" * 30,
             parent=camera.ui, scale=0.88,
             color=color.rgba(0, 175, 255, 60),
             position=Vec3(-0.785, 0.352))

        self.ctrl.ui_fps = Text(
            text     = "FPS      :  --",
            parent   = camera.ui, scale=0.82, color=C_UI_DIM,
            position = Vec3(-0.785, 0.330))

        # Bottom instruction bar
        Text(
            text     = "✊ Fist → ON     ✋ Open → OFF     👌 Pinch → Precision",
            parent   = camera.ui, scale=0.82,
            color    = color.rgb(90, 160, 210),
            position = Vec3(-0.76, -0.465))

        Text(text="ESC to exit",
             parent=camera.ui, scale=0.75,
             color=C_UI_DIM, position=Vec3(0.58, -0.465))

    # ─────────────── Run ─────────────────────────────────────────

    def run(self):
        """Hand control to the Ursina main loop. Blocks until closed."""
        self.app.run()
