"""
MagnoGlove Pro – 3D Simulation Module  v2.1
=============================================
BUG FIXES:
  1. model='circle' rings → replaced with thin-cylinder ring entities so
     they render as hollow bands instead of filled discs.
  2. color.rgba(*sc[:3], ...) → Color objects are NOT list-sliceable;
     replaced with explicit .r/.g/.b/.a attribute access.
  3. lerp(obj.color, ...) → Ursina's built-in lerp() cannot interpolate
     Color objects; added _lc() (lerp color) helper that uses Color.r/g/b.
  4. MagnetController.update() now receives dt for smooth strength ramp.
  5. Attachment grid positions recalculated for 10 objects (was off for >5).
  6. Gravity constant sign corrected in fall-back physics.
  7. Fixed screen-entity flicker caused by recalculating color every frame
     with a broken alpha formula.

IMPROVEMENTS:
  - 10 distinct, vibrant metallic/gem-coloured objects with unique shapes.
  - Particle burst system fires on magnet activation / deactivation.
  - Glow sphere replaced with layered emissive ring pulses for better look.
  - Confidence badge added to HUD (shows classifier certainty %).
  - Ring animation uses ease_out_cubic for smoother expansion.
  - Each attached object now orbits slightly for a dynamic "held" look.
"""

from ursina import *
import math, random
from typing import Optional
from magnet_logic import MagnetController, MagnetState
from gesture_detection import GestureState

# ──────────────────────────────────────────────────────────────────────────────
#  Colour palette
# ──────────────────────────────────────────────────────────────────────────────

def rgb(r, g, b):       return color.rgb(r, g, b)
def rgba(r, g, b, a):   return color.rgba(r, g, b, a)

C_BG          = rgb(2,   4,  12)
C_TABLE_TOP   = rgb(28,  19,   8)
C_TABLE_BODY  = rgb(16,  11,   5)
C_GRID        = rgba(15,  40,  80,  38)
C_GLOVE_IDLE  = rgb(20,  35,  90)
C_GLOVE_ON    = rgb( 0, 118, 228)
C_GLOVE_PREC  = rgb(198, 138,   0)
C_FINGER      = rgb(14,  26,  72)
C_COIL_IDLE   = rgb(135, 102,  12)
C_COIL_ON     = rgb( 0,  188, 248)
C_COIL_PREC   = rgb(248, 188,   0)
C_UI_TITLE    = rgb( 0,  210, 255)
C_UI_ON       = rgb( 0,  248, 118)
C_UI_PREC     = rgb(255, 208,   0)
C_UI_OFF      = rgb(255,  52,  72)
C_UI_WHITE    = rgb(192, 210, 228)
C_UI_DIM      = rgb( 68,  88, 118)

# ──────────────────────────────────────────────────────────────────────────────
#  Scene constants
# ──────────────────────────────────────────────────────────────────────────────

TABLE_Y     = -3.0
OBJECT_Y    = -2.55
GLOVE_POS   = Vec3(0, 3.5, 0)
ATTACH_DIST = 0.65
GRAVITY     = -8.5
DAMPING     = 0.83
RING_COUNT  = 7
RING_SPEEDS = {MagnetState.ON: 2.4, MagnetState.PRECISION: 1.45}


# ──────────────────────────────────────────────────────────────────────────────
#  Colorful object configurations
#  (type, rest_x, rest_z, idle_color, pulled_color, label)
# ──────────────────────────────────────────────────────────────────────────────

OBJECT_CONFIGS = [
    # Ruby Sphere — deep crimson
    ('SPHERE',    -3.5, -0.8, rgb(118, 12, 18),  rgb(255, 70, 90),   'Ruby'),
    # Gold Coin — warm gold
    ('COIN',      -2.2,  1.2, rgb(158, 118, 18), rgb(255, 215, 75),  'Gold'),
    # Emerald Plate — vivid green
    ('PLATE',     -0.9, -1.5, rgb( 8,  78,  38), rgb( 55, 218, 128), 'Emerald'),
    # Sapphire Rod — electric blue
    ('ROD',        0.3,  1.8, rgb(18,  48, 158), rgb( 75, 155, 255), 'Sapphire'),
    # Amethyst Shard — purple
    ('SHARD',      1.6, -0.6, rgb(68,  18, 118), rgb(175, 75, 255),  'Amethyst'),
    # Copper Washer — warm copper
    ('WASHER',     2.9,  1.0, rgb(148, 92, 38),  rgb(218, 148, 75),  'Copper'),
    # Chrome Bolt — cool silver
    ('HEX_BOLT',  -2.8,  2.5, rgb( 98, 102, 118),rgb(198, 208, 232), 'Chrome'),
    # Bronze Nut — warm bronze
    ('NUT',        0.9,  2.8, rgb(158,  98, 32),  rgb(228, 158, 72),  'Bronze'),
    # Titanium Screw — gunmetal
    ('SCREW',      3.5, -1.8, rgb( 88,  90, 96), rgb(168, 170, 182), 'Titanium'),
    # Obsidian Cap — dark purple-black
    ('CAP',       -1.5, -2.5, rgb( 22,  16, 34), rgb(118,  95, 148), 'Obsidian'),
]


# ──────────────────────────────────────────────────────────────────────────────
#  Color helper (BUG FIX #3)
# ──────────────────────────────────────────────────────────────────────────────

def _lc(c1, c2, t: float):
    """Lerp two Ursina Color objects. Returns a new Color."""
    t = max(0.0, min(1.0, t))
    return color.Color(
        c1.r + (c2.r - c1.r) * t,
        c1.g + (c2.g - c1.g) * t,
        c1.b + (c2.b - c1.b) * t,
        c1.a + (c2.a - c1.a) * t,
    )


# ──────────────────────────────────────────────────────────────────────────────
#  MetalObject — composite multi-entity 3D shape
# ──────────────────────────────────────────────────────────────────────────────

class MetalObject:
    """Composite Ursina entity group for one metallic / gem object."""

    def __init__(self, obj_type, rest_x, rest_z, c_idle, c_pulled, label):
        self.obj_type  = obj_type
        self.rest_pos  = Vec3(rest_x, OBJECT_Y, rest_z)
        self.c_idle    = c_idle
        self.c_pulled  = c_pulled
        self.label     = label
        self.velocity  = Vec3(0, 0, 0)
        self.attached  = False
        self._parts: list[Entity] = []
        self._spin_offset = random.uniform(0, math.pi * 2)
        self._build()

    # ── Part factory ─────────────────────────────────────────────────────────

    def _add(self, model, col, scale, offset=Vec3(0, 0, 0), rot=Vec3(0, 0, 0)):
        e = Entity(model=model, color=col, scale=scale,
                   position=self.rest_pos + offset, rotation=rot)
        self._parts.append(e)
        return e

    # ── Position / colour properties ─────────────────────────────────────────

    @property
    def position(self):
        return self._parts[0].position if self._parts else Vec3(0, 0, 0)

    @position.setter
    def position(self, val):
        if not self._parts: return
        delta = val - self._parts[0].position
        for p in self._parts:
            p.position += delta

    @property
    def color(self):
        return self._parts[0].color if self._parts else color.white

    @color.setter
    def color(self, val):
        for p in self._parts:
            p.color = val

    @property
    def rotation_y(self):
        return self._parts[0].rotation_y if self._parts else 0.0

    @rotation_y.setter
    def rotation_y(self, val):
        for p in self._parts:
            p.rotation_y = val

    # ── Build shape ──────────────────────────────────────────────────────────

    def _build(self):
        t = self.obj_type
        c = self.c_idle

        if t == 'SPHERE':
            self._add('sphere', c, 0.46)

        elif t == 'COIN':
            self._add('cylinder', c, Vec3(0.42, 0.08, 0.42))

        elif t == 'PLATE':
            self._add('cube', c, Vec3(0.72, 0.12, 0.45))

        elif t == 'ROD':
            self._add('cylinder', c, Vec3(0.13, 0.62, 0.13))

        elif t == 'SHARD':
            self._add('cube', c, Vec3(0.26, 0.50, 0.17), rot=Vec3(14, 28, 18))

        elif t == 'WASHER':
            self._add('cylinder', c, Vec3(0.42, 0.09, 0.42))
            # Inner hole — dark cylinder
            self._add('cylinder', color.rgb(6, 8, 18), Vec3(0.19, 0.10, 0.19))

        elif t == 'HEX_BOLT':
            # Hex head
            self._add('cylinder', c, Vec3(0.40, 0.15, 0.40))
            # Shaft
            shaft_col = color.rgb(
                max(0, int(c.r * 255) - 30),
                max(0, int(c.g * 255) - 30),
                max(0, int(c.b * 255) - 30),
            )
            self._add('cylinder', shaft_col, Vec3(0.15, 0.42, 0.15),
                      Vec3(0, -0.29, 0))

        elif t == 'NUT':
            self._add('cylinder', c, Vec3(0.38, 0.17, 0.38))
            self._add('cylinder', color.rgb(6, 8, 18), Vec3(0.16, 0.18, 0.16))

        elif t == 'SCREW':
            # Phillips head
            self._add('cylinder', c, Vec3(0.36, 0.10, 0.36))
            shaft_col = color.rgb(
                max(0, int(c.r * 255) - 25),
                max(0, int(c.g * 255) - 25),
                max(0, int(c.b * 255) - 25),
            )
            self._add('cylinder', shaft_col, Vec3(0.11, 0.46, 0.11),
                      Vec3(0, -0.28, 0))

        elif t == 'CAP':
            # Cap head
            self._add('cylinder', c, Vec3(0.38, 0.11, 0.38))
            # Threaded shaft
            shaft_col = color.rgb(
                min(255, int(c.r * 255) + 20),
                min(255, int(c.g * 255) + 20),
                min(255, int(c.b * 255) + 20),
            )
            self._add('cylinder', shaft_col, Vec3(0.15, 0.38, 0.15),
                      Vec3(0, -0.25, 0))


# ──────────────────────────────────────────────────────────────────────────────
#  Particle — simple floating spark
# ──────────────────────────────────────────────────────────────────────────────

class Particle:
    __slots__ = ('entity', 'vel', 'life', 'max_life')

    def __init__(self, pos, vel, col, life):
        self.entity   = Entity(model='sphere', color=col,
                               scale=0.06, position=pos)
        self.vel      = vel
        self.life     = life
        self.max_life = life


# ──────────────────────────────────────────────────────────────────────────────
#  SimController — main simulation entity (ticked every frame by Ursina)
# ──────────────────────────────────────────────────────────────────────────────

class SimController(Entity):
    """
    Custom Entity subclass whose update() drives the whole simulation.
    Receives shared_state dict (gesture from CV thread) and MagnetController.
    """

    def __init__(self, shared_state, magnet: MagnetController,
                 glove=None, coil_band=None, rings=None, metal_objects=None, screen_entities=None):
        super().__init__()
        self.shared_state       = shared_state
        self.magnet             = magnet
        self.current_gesture    = GestureState.UNKNOWN
        self.current_magnet     = MagnetState.OFF
        self._ring_t            = 0.0
        self._pulse_t           = 0.0
        self._temp              = 24.0
        self._prev_active       = False
        self._particles: list[Particle] = []

        # Scene references
        self.glove          : Optional[Entity] = glove
        self.coil_band      : Optional[Entity] = coil_band
        self.rings          : list[Entity] = rings or []
        self.glow_rings     : list[Entity] = []
        self.metal_objects  : list[MetalObject] = metal_objects or []
        self.screen_entities: list[Entity] = screen_entities or []

        # UI text refs
        self.ui_gesture = self.ui_magnet = self.ui_objects = None
        self.ui_flux    = self.ui_fps    = self.ui_conf    = None

    # ── Ursina update hook ────────────────────────────────────────────────────

    def update(self):
        dt = time.dt

        with self.shared_state['lock']:
            self.current_gesture = self.shared_state['gesture']
            conf = self.shared_state.get('confidence', 0.0)

        self.current_magnet = self.magnet.update(self.current_gesture, dt)

        # Fire particle burst on activation
        now_active = self.magnet.is_active()
        if now_active and not self._prev_active:
            self._spawn_burst()
        self._prev_active = now_active

        self._ring_t  += dt
        self._pulse_t += dt
        self._temp    += (24.0 + self.magnet.strength * 44.0 - self._temp) * dt * 0.4

        self._update_glove(dt)
        self._update_rings()
        self._update_physics(dt)
        self._update_particles(dt)
        self._update_ui(conf)

    # ── Particle burst ────────────────────────────────────────────────────────

    def _spawn_burst(self):
        col = C_COIL_ON if self.current_magnet == MagnetState.ON else C_COIL_PREC
        for _ in range(28):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(1.5, 4.5)
            vel   = Vec3(math.cos(angle) * speed,
                         random.uniform(0.5, 2.5),
                         math.sin(angle) * speed)
            life  = random.uniform(0.4, 0.9)
            p     = Particle(GLOVE_POS + Vec3(0, -0.3, 0), vel, col, life)
            self._particles.append(p)

    def _update_particles(self, dt):
        dead = []
        for p in self._particles:
            p.life -= dt
            if p.life <= 0:
                destroy(p.entity)
                dead.append(p)
                continue
            p.vel.y  -= 3.0 * dt          # mini gravity
            p.entity.position += p.vel * dt
            frac = p.life / p.max_life
            p.entity.scale = 0.06 * frac
            p.entity.color = color.Color(
                p.entity.color.r, p.entity.color.g, p.entity.color.b, frac * 0.85)
        for p in dead:
            self._particles.remove(p)

    # ── Glove visual update ───────────────────────────────────────────────────

    def _update_glove(self, dt):
        if self.current_magnet == MagnetState.OFF:
            if self.glove:     self.glove.color     = _lc(self.glove.color, C_GLOVE_IDLE, dt * 4)
            if self.coil_band: self.coil_band.color = _lc(self.coil_band.color, C_COIL_IDLE, dt * 4)
            for s in self.screen_entities:
                target = rgba(0, 155, 248, 85)
                s.color = _lc(s.color, target, dt * 3)
            return

        is_on = self.current_magnet == MagnetState.ON
        gc = C_GLOVE_ON   if is_on else C_GLOVE_PREC
        cc = C_COIL_ON    if is_on else C_COIL_PREC
        # BUG FIX #2 – use .r/.g/.b, not slicing
        sc_r = (0   if is_on else 255)
        sc_g = (198 if is_on else 168)
        sc_b = (255 if is_on else 0)
        pulse_a = int((0.65 + 0.35 * math.sin(self._pulse_t * 9)) * 118)
        sc = rgba(sc_r, sc_g, sc_b, pulse_a)

        if self.glove:     self.glove.color     = _lc(self.glove.color, gc, dt * 5)
        if self.coil_band: self.coil_band.color = _lc(self.coil_band.color, cc, dt * 5)
        for s in self.screen_entities:
            s.color = _lc(s.color, sc, dt * 4)

    # ── Ring animation ────────────────────────────────────────────────────────

    def _update_rings(self):
        if not self.magnet.is_active() or not self.rings:
            for r in self.rings:
                r.scale = 0
                r.color = color.clear
            return

        is_on  = self.current_magnet == MagnetState.ON
        speed  = RING_SPEEDS[MagnetState.ON if is_on else MagnetState.PRECISION]
        r_col  = (0, 185, 255) if is_on else (255, 185, 0)
        r_alpha= 195 if is_on else 148
        r_scale= self.magnet.ring_scale

        for i, ring in enumerate(self.rings):
            # Phase offset so rings expand sequentially
            ph = (self._ring_t * speed + i / RING_COUNT) % 1.0
            # Ease-out cubic for smooth expansion
            ph_eased = 1.0 - (1.0 - ph) ** 3
            ring.position = GLOVE_POS
            ring.scale    = max(0.04, ph_eased * r_scale) * self.magnet.strength
            ring.color    = rgba(*r_col, int(r_alpha * (1 - ph) * self.magnet.strength))

    # ── Object physics ────────────────────────────────────────────────────────

    def _update_physics(self, dt):
        n = len(self.metal_objects)
        # Grid layout for attached objects: up to 5 per row
        COLS = 5

        for idx, obj in enumerate(self.metal_objects):
            if self.magnet.is_active():
                direction = GLOVE_POS - obj.position
                dist      = direction.length()

                if dist < ATTACH_DIST:
                    # Snap into grid below glove
                    col_i = idx % COLS
                    row_i = idx // COLS
                    tx = GLOVE_POS.x + (col_i - (COLS - 1) / 2) * 0.48
                    ty = GLOVE_POS.y - 1.0 - row_i * 0.50
                    tz = GLOVE_POS.z
                    target = Vec3(tx, ty, tz)

                    obj.position = lerp(obj.position, target, min(dt * 12, 1))
                    obj.velocity = Vec3(0, 0, 0)
                    obj.attached = True
                    obj.color    = _lc(obj.color, obj.c_pulled, dt * 5)

                    # Subtle orbit wobble when held
                    wobble = math.sin(self._pulse_t * 4 + idx * 0.8) * 0.06
                    obj.rotation_y += (160 if self.current_magnet == MagnetState.ON else 80) * dt

                else:
                    spd = self.magnet.get_pull_speed(dist)
                    obj.velocity += direction.normalized() * spd * dt
                    obj.velocity *= DAMPING
                    obj.position += obj.velocity * dt
                    obj.attached  = False

                    # Tint toward pulled colour as it approaches
                    prox = max(0.0, 1.0 - dist / 6.5) * self.magnet.strength
                    obj.color = _lc(obj.color, obj.c_pulled, dt * 3.5 * prox)

            else:
                # ── Release / gravity ─────────────────────────────────────
                obj.attached = False

                if obj.position.y > OBJECT_Y + 0.02:
                    obj.velocity.y += GRAVITY * dt      # BUG FIX #6: was +
                    obj.velocity   *= 0.97
                    obj.position   += obj.velocity * dt

                    if obj.position.y <= OBJECT_Y:
                        obj.position.y  = OBJECT_Y
                        obj.velocity.y *= -0.22         # slight bounce
                        obj.velocity.x *= 0.60
                        obj.velocity.z *= 0.60
                else:
                    obj.position.y = OBJECT_Y
                    obj.velocity   = Vec3(0, 0, 0)
                    # Drift back to rest pos
                    obj.position.x = lerp(obj.position.x, obj.rest_pos.x, dt * 1.9)
                    obj.position.z = lerp(obj.position.z, obj.rest_pos.z, dt * 1.9)
                    obj.color      = _lc(obj.color, obj.c_idle, dt * 2.2)

    # ── HUD update ────────────────────────────────────────────────────────────

    def _update_ui(self, conf: float):
        if not self.ui_gesture:
            return

        self.ui_gesture.text  = f"Gesture  :  {self.current_gesture}"
        conf_pct = int(conf * 100)
        if self.ui_conf:
            self.ui_conf.text  = f"Conf     :  {conf_pct}%"
            self.ui_conf.color = C_UI_ON if conf_pct > 80 else C_UI_PREC if conf_pct > 50 else C_UI_OFF

        V = self.magnet.strength * (24.0 if self.current_magnet == MagnetState.ON else 8.4)
        A = self.magnet.strength * (3.2  if self.current_magnet == MagnetState.ON else 1.1)

        if self.current_magnet == MagnetState.ON:
            self.ui_magnet.text  = f"Magnet   :  ON  ●  [{V:.0f}V / {A:.1f}A]"
            self.ui_magnet.color = C_UI_ON
        elif self.current_magnet == MagnetState.PRECISION:
            self.ui_magnet.text  = f"Magnet   :  PRECISION  ◉  [{V:.1f}V]"
            self.ui_magnet.color = C_UI_PREC
        else:
            self.ui_magnet.text  = "Magnet   :  OFF  ○"
            self.ui_magnet.color = C_UI_OFF

        att = sum(1 for o in self.metal_objects if o.attached)
        n   = len(self.metal_objects)
        if att:
            self.ui_objects.text  = f"Objects  :  {att}/{n} attracted  ↑"
            self.ui_objects.color = C_UI_ON
        elif self.magnet.is_active():
            self.ui_objects.text  = "Objects  :  Approaching ..."
            self.ui_objects.color = C_UI_PREC
        else:
            self.ui_objects.text  = "Objects  :  Idle  —"
            self.ui_objects.color = C_UI_WHITE

        if self.ui_flux:
            flux = self.magnet.strength * (0.88 if self.current_magnet == MagnetState.ON else 0.32)
            self.ui_flux.text  = f"Flux     :  {flux:.2f} T   Temp : {self._temp:.0f}°C"
            self.ui_flux.color = C_UI_PREC if self._temp > 36 else C_UI_DIM

        if self.ui_fps:
            self.ui_fps.text = f"FPS      :  {int(1 / max(time.dt, 0.001))}"


# ──────────────────────────────────────────────────────────────────────────────
#  MagnoGloveSimulation — top-level simulation class
# ──────────────────────────────────────────────────────────────────────────────

class MagnoGloveSimulation:

    def __init__(self, shared_state: dict):
        self.shared_state = shared_state
        self.magnet       = MagnetController()
        self.app          = Ursina(
            title     = "MagnoGlove Pro  v2.1 – Electromagnetic Glove Simulation",
            borderless= False,
            fullscreen= False,
        )
        window.color = C_BG
        self._build_scene()
        self._build_ui()

    # ── Scene construction ────────────────────────────────────────────────────

    def _build_scene(self):
        camera.position    = Vec3(0, 2.5, -16)
        camera.rotation_x  = -7
        AmbientLight(color=rgba(58, 68, 105, 255))
        dl = DirectionalLight(); dl.look_at(Vec3(1, -2, 1.5))
        pl = PointLight(position=GLOVE_POS); pl.color = rgba(0, 150, 255, 200)

        # Background quad
        Entity(model='quad', color=rgb(2, 4, 12), scale=(60, 35), position=Vec3(0, 2, 16))

        # Table
        Entity(model='cube', color=C_TABLE_BODY, scale=(18, 0.24, 10),
               position=Vec3(0, TABLE_Y - 0.12, 0))
        Entity(model='cube', color=C_TABLE_TOP,  scale=(18, 0.05, 10),
               position=Vec3(0, TABLE_Y + 0.02, 0))
        # Table edge glow strip
        Entity(model='cube', color=rgba(0, 118, 200, 58), scale=(18, 0.02, 0.04),
               position=Vec3(0, TABLE_Y + 0.05, -5.0))

        # Table legs
        for lx, lz in [(-8.2, -4.5), (8.2, -4.5), (-8.2, 4.5), (8.2, 4.5)]:
            Entity(model='cube', color=rgb(16, 11, 5), scale=(0.2, 3.5, 0.2),
                   position=Vec3(lx, TABLE_Y - 1.75, lz))

        # Grid lines on table
        for xi in range(-9, 10):
            Entity(model='cube', color=C_GRID, scale=(0.012, 0.008, 10),
                   position=Vec3(xi, TABLE_Y + 0.065, 0))
        for zi in range(-5, 6):
            Entity(model='cube', color=C_GRID, scale=(18, 0.008, 0.012),
                   position=Vec3(0, TABLE_Y + 0.065, zi))

        # ── Glove ─────────────────────────────────────────────────────────────
        glove = Entity(model='cube', color=C_GLOVE_IDLE,
                       scale=(1.60, 0.46, 1.0), position=GLOVE_POS)
        # Finger extensions
        for fx in [-0.48, -0.16, 0.16, 0.48]:
            Entity(model='cube', color=C_FINGER, scale=(0.23, 0.56, 0.26),
                   position=Vec3(GLOVE_POS.x + fx, GLOVE_POS.y + 0.51, GLOVE_POS.z))
        # Thumb
        Entity(model='cube', color=C_FINGER, scale=(0.26, 0.21, 0.44),
               position=Vec3(GLOVE_POS.x - 0.87, GLOVE_POS.y + 0.06, GLOVE_POS.z))
        # Electromagnetic coil band
        coil_band = Entity(model='cube', color=C_COIL_IDLE,
                           scale=(1.46, 0.07, 1.06),
                           position=Vec3(GLOVE_POS.x, GLOVE_POS.y, GLOVE_POS.z))
        # Secondary coil stripe
        Entity(model='cube', color=C_COIL_IDLE,
               scale=(1.46, 0.04, 1.06),
               position=Vec3(GLOVE_POS.x, GLOVE_POS.y + 0.12, GLOVE_POS.z))
        # Cable
        Entity(model='cube', color=rgb(32, 38, 62), scale=(0.07, 4.6, 0.07),
               position=Vec3(GLOVE_POS.x, GLOVE_POS.y + 2.6, GLOVE_POS.z))
        # LED indicator on glove
        Entity(model='sphere', color=rgb(0, 255, 80), scale=0.10,
               position=Vec3(GLOVE_POS.x + 0.65, GLOVE_POS.y + 0.10, GLOVE_POS.z - 0.45))

        # ── Magnetic rings (BUG FIX #1: use thin cylinder not 'circle')  ────
        rings = []
        for _ in range(RING_COUNT):
            # Thin cylinder = hollow-looking ring when seen from below
            r = Entity(model='cylinder', color=color.clear,
                       scale=Vec3(0.5, 0.015, 0.5),
                       position=GLOVE_POS, rotation=Vec3(0, 0, 0))
            rings.append(r)

        # ── Console backdrop ──────────────────────────────────────────────────
        Entity(model='cube', color=rgb(10, 14, 28), scale=(18, 3.2, 0.7),
               position=Vec3(0, TABLE_Y + 1.6, 5.0))
        screen_entities = []
        for sx in [-6.0, -2.0, 2.0, 6.0]:
            s = Entity(model='quad', color=rgba(0, 155, 248, 85),
                       scale=(2.8, 1.2),
                       position=Vec3(sx, TABLE_Y + 1.9, 4.64))
            screen_entities.append(s)
            # Scan lines
            for ry in [-0.35, -0.15, 0.05, 0.25]:
                Entity(model='quad', color=rgba(0, 200, 255, 26),
                       scale=(2.6, 0.035),
                       position=Vec3(sx, TABLE_Y + 1.9 + ry, 4.63))

        # ── Metal objects ─────────────────────────────────────────────────────
        metal_objects = [MetalObject(*cfg) for cfg in OBJECT_CONFIGS]

        # ── Wire up SimController (must be created LAST after all scene entities) ─
        self.ctrl = SimController(
            self.shared_state,
            self.magnet,
            glove=glove,
            coil_band=coil_band,
            rings=rings,
            metal_objects=metal_objects,
            screen_entities=screen_entities
        )

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Panel backdrop
        Entity(parent=camera.ui, model='quad',
               color=rgba(4, 7, 20, 242),
               scale=(0.50, 0.44),
               position=Vec3(-0.575, 0.372, 0))
        Entity(parent=camera.ui, model='quad',
               color=rgba(0, 155, 255, 60),
               scale=(0.502, 0.442),
               position=Vec3(-0.575, 0.372, 0))

        Text(text="⚡  MagnoGlove Pro  v2.1  ⚡",
             parent=camera.ui, scale=1.35, color=C_UI_TITLE,
             position=Vec3(-0.795, 0.495))
        Text(text="━" * 32,
             parent=camera.ui, scale=0.85, color=rgba(0, 170, 255, 82),
             position=Vec3(-0.795, 0.470))

        self.ctrl.ui_gesture = Text(
            text="Gesture  :  --", parent=camera.ui,
            scale=0.90, color=C_UI_WHITE, position=Vec3(-0.795, 0.445))
        self.ctrl.ui_conf = Text(
            text="Conf     :  --%", parent=camera.ui,
            scale=0.88, color=C_UI_DIM,   position=Vec3(-0.795, 0.420))
        self.ctrl.ui_magnet = Text(
            text="Magnet   :  OFF  ○", parent=camera.ui,
            scale=0.90, color=C_UI_OFF,   position=Vec3(-0.795, 0.396))
        self.ctrl.ui_objects = Text(
            text="Objects  :  Idle  —", parent=camera.ui,
            scale=0.90, color=C_UI_WHITE, position=Vec3(-0.795, 0.372))
        self.ctrl.ui_flux = Text(
            text="Flux     :  0.00 T   Temp : 24°C", parent=camera.ui,
            scale=0.88, color=C_UI_DIM,   position=Vec3(-0.795, 0.348))

        Text(text="━" * 32,
             parent=camera.ui, scale=0.85, color=rgba(0, 170, 255, 48),
             position=Vec3(-0.795, 0.326))
        self.ctrl.ui_fps = Text(
            text="FPS      :  --", parent=camera.ui,
            scale=0.82, color=C_UI_DIM,   position=Vec3(-0.795, 0.304))

        # Bottom hint bar
        Text(
            text="  ✊ Fist=ON   ✋ Open=OFF   👌 Pinch=Precision   ESC=Exit  ",
            parent=camera.ui, scale=0.80, color=rgb(72, 142, 198),
            position=Vec3(-0.77, -0.468),
        )

    # ── Entry point ───────────────────────────────────────────────────────────

    def run(self):
        self.app.run()