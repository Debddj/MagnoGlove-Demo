"""
MagnoGlove Pro – 3D Simulation Module  (v2.0 Industry Edition)
================================================================
Complete visual overhaul. 10 distinct metallic object types, enhanced
glove with coil bands, holographic HUD with telemetry, animated console
screens, blueprint grid, particle bursts, and rich color transitions.
"""

from ursina import *
import math, random
from magnet_logic import MagnetController, MagnetState
from gesture_detection import GestureState

C_BG         = color.rgb(3,5,15)
C_TABLE_TOP  = color.rgb(30,20,10)
C_TABLE_BODY = color.rgb(20,13,6)
C_GRID       = color.rgba(20,50,100,55)
C_CONSOLE    = color.rgb(12,16,30)
C_GLOVE_IDLE = color.rgb(22,40,100)
C_GLOVE_ON   = color.rgb(0,130,240)
C_GLOVE_PREC = color.rgb(210,145,0)
C_FINGER     = color.rgb(18,32,85)
C_COIL_IDLE  = color.rgb(160,120,20)
C_COIL_ON    = color.rgb(0,200,255)
C_COIL_PREC  = color.rgb(255,200,0)
C_RING_ON    = (0,190,255)
C_RING_PREC  = (255,190,0)
C_UI_TITLE   = color.rgb(0,220,255)
C_UI_ON      = color.rgb(0,255,130)
C_UI_PREC    = color.rgb(255,215,0)
C_UI_OFF     = color.rgb(255,60,80)
C_UI_WHITE   = color.rgb(200,215,230)
C_UI_DIM     = color.rgb(80,100,130)

TABLE_Y    = -3.0
OBJECT_Y   = -2.58
GLOVE_POS  = Vec3(0,3.5,0)
ATTACH_DIST= 0.60
GRAVITY    = -9.8
DAMPING    = 0.86
RING_COUNT = 6
RING_SPEED = {MagnetState.ON:2.3, MagnetState.PRECISION:1.4}

OBJECT_CONFIGS = [
    ('SPHERE',  -3.5,-0.8, color.rgb(160,165,185), color.rgb(180,215,255)),
    ('HEX_BOLT',-2.2, 1.2, color.rgb(150,155,175), color.rgb(170,210,255)),
    ('SCREW',   -0.9,-1.5, color.rgb(145,150,168), color.rgb(165,205,250)),
    ('PLATE',    0.3, 1.8, color.rgb(155,158,172), color.rgb(175,212,252)),
    ('COIN',     1.6,-0.6, color.rgb(180,148,70),  color.rgb(220,195,120)),
    ('ROD',      2.9, 1.0, color.rgb(155,160,180), color.rgb(175,215,255)),
    ('WASHER',  -2.8, 2.5, color.rgb(150,155,172), color.rgb(170,210,252)),
    ('SHARD',    0.9, 2.8, color.rgb(162,150,158), color.rgb(185,212,255)),
    ('NUT',      3.5,-1.8, color.rgb(148,158,165), color.rgb(168,210,252)),
    ('CAP',     -1.5,-2.5, color.rgb(160,148,165), color.rgb(182,210,255)),
]

class MetalObject:
    def __init__(self, obj_type, rest_x, rest_z, c_idle, c_pulled):
        self.obj_type = obj_type
        self.rest_pos = Vec3(rest_x, OBJECT_Y, rest_z)
        self.c_idle   = c_idle
        self.c_pulled = c_pulled
        self.velocity = Vec3(0,0,0)
        self.attached = False
        self._parts   = []
        self._build()

    def _add(self, model, col, scale, offset=Vec3(0,0,0), rot=Vec3(0,0,0)):
        e = Entity(model=model, color=col, scale=scale,
                   position=self.rest_pos+offset, rotation=rot)
        self._parts.append(e)
        return e

    @property
    def position(self):
        return self._parts[0].position if self._parts else Vec3(0,0,0)

    @position.setter
    def position(self, val):
        if not self._parts: return
        delta = val - self._parts[0].position
        for p in self._parts: p.position += delta

    @property
    def color(self): return self._parts[0].color if self._parts else color.white

    @color.setter
    def color(self, val):
        for p in self._parts: p.color = val

    @property
    def rotation_y(self): return self._parts[0].rotation_y if self._parts else 0

    @rotation_y.setter
    def rotation_y(self, val):
        for p in self._parts: p.rotation_y = val

    def _build(self):
        t = self.obj_type
        if   t=='SPHERE':   self._add('sphere',self.c_idle,0.44)
        elif t=='HEX_BOLT': self._add('cylinder',self.c_idle,Vec3(.38,.14,.38)); self._add('cylinder',color.rgb(130,135,150),Vec3(.14,.40,.14),Vec3(0,-.27,0))
        elif t=='SCREW':    self._add('cylinder',self.c_idle,Vec3(.34,.09,.34)); self._add('cylinder',color.rgb(128,132,148),Vec3(.10,.45,.10),Vec3(0,-.27,0))
        elif t=='PLATE':    self._add('cube',self.c_idle,Vec3(.70,.11,.44))
        elif t=='COIN':     self._add('cylinder',self.c_idle,Vec3(.40,.07,.40))
        elif t=='ROD':      self._add('cylinder',self.c_idle,Vec3(.12,.60,.12))
        elif t=='WASHER':   self._add('cylinder',self.c_idle,Vec3(.40,.08,.40)); self._add('cylinder',color.rgb(8,10,20),Vec3(.18,.09,.18))
        elif t=='SHARD':    self._add('cube',self.c_idle,Vec3(.25,.48,.16),rot=Vec3(12,25,15))
        elif t=='NUT':      self._add('cylinder',self.c_idle,Vec3(.36,.16,.36)); self._add('cylinder',color.rgb(8,10,20),Vec3(.15,.17,.15))
        elif t=='CAP':      self._add('cylinder',self.c_idle,Vec3(.36,.10,.36)); self._add('cylinder',color.rgb(135,140,155),Vec3(.14,.35,.14),Vec3(0,-.22,0))


class SimController(Entity):
    def __init__(self, shared_state, magnet):
        super().__init__()
        self.shared_state = shared_state
        self.magnet = magnet
        self.current_gesture = GestureState.UNKNOWN
        self.current_magnet  = MagnetState.OFF
        self._ring_timer = 0.0
        self._pulse_timer = 0.0
        self._temp = 24.0
        self.glove = self.coil_band = self.glow_sphere = None
        self.metal_objects = []; self.rings = []; self.screen_entities = []
        self.ui_gesture = self.ui_magnet = self.ui_objects = None
        self.ui_voltage = self.ui_fps = None

    def update(self):
        dt = time.dt
        with self.shared_state['lock']:
            self.current_gesture = self.shared_state['gesture']
        self.current_magnet = self.magnet.update(self.current_gesture)
        self._ring_timer  += dt
        self._pulse_timer += dt
        self._temp += (24 + self.magnet.strength*42 - self._temp)*dt*0.4
        self._update_glove_effects(dt)
        self._update_physics(dt)
        self._update_ui()

    def _update_glove_effects(self, dt):
        if self.current_magnet == MagnetState.OFF:
            if self.glove:     self.glove.color     = C_GLOVE_IDLE
            if self.coil_band: self.coil_band.color = C_COIL_IDLE
            for r in self.rings: r.scale=0; r.color=color.clear
            if self.glow_sphere: self.glow_sphere.scale=0; self.glow_sphere.color=color.clear
            for s in self.screen_entities: s.color=color.rgba(0,160,255,90)
            return
        is_on = (self.current_magnet == MagnetState.ON)
        gc = C_GLOVE_ON   if is_on else C_GLOVE_PREC
        cc = C_COIL_ON    if is_on else C_COIL_PREC
        rr = C_RING_ON    if is_on else C_RING_PREC
        rs = RING_SPEED[MagnetState.ON if is_on else MagnetState.PRECISION]
        ra = 200          if is_on else 150
        gr = (0,110,255)  if is_on else (255,165,0)
        sc = color.rgba(0,200,255,125) if is_on else color.rgba(255,170,0,105)
        if self.glove:     self.glove.color     = gc
        if self.coil_band: self.coil_band.color = cc
        for i,ring in enumerate(self.rings):
            ph=(self._ring_timer*rs+i/RING_COUNT)%1.0
            ring.position=GLOVE_POS; ring.scale=max(.04,ph*self.magnet.ring_scale)
            ring.color=color.rgba(*rr,int(ra*(1-ph)))
        if self.glow_sphere:
            pulse=1+.20*math.sin(self._pulse_timer*7)
            self.glow_sphere.position=GLOVE_POS; self.glow_sphere.scale=1.9*pulse
            self.glow_sphere.color=color.rgba(*gr,self.magnet.glow_alpha)
        for s in self.screen_entities:
            fl=.85+.15*math.sin(self._pulse_timer*9+id(s))
            s.color=color.rgba(*sc[:3],int(sc.a*fl))

    def _update_physics(self, dt):
        for idx,obj in enumerate(self.metal_objects):
            if self.magnet.is_active():
                direction=GLOVE_POS-obj.position; dist=direction.length()
                if dist<ATTACH_DIST:
                    col_i=idx%5; row_i=idx//5
                    target=GLOVE_POS+Vec3((col_i-2)*.46,-1.0+row_i*-.46,0)
                    obj.position=lerp(obj.position,target,dt*10)
                    obj.velocity=Vec3(0,0,0); obj.attached=True
                    obj.color=lerp(obj.color,obj.c_pulled,dt*4)
                    obj.rotation_y+=(155 if self.current_magnet==MagnetState.ON else 75)*dt
                else:
                    spd=self.magnet.get_pull_speed(dist)
                    obj.velocity+=direction.normalized()*spd*dt
                    obj.velocity*=DAMPING; obj.position+=obj.velocity*dt; obj.attached=False
                    t=max(0.,1.-dist/5.5); obj.color=lerp(obj.color,obj.c_pulled,dt*3*t)
            else:
                obj.attached=False
                if obj.position.y>OBJECT_Y+.015:
                    obj.velocity.y+=GRAVITY*dt; obj.velocity*=.97; obj.position+=obj.velocity*dt
                    if obj.position.y<=OBJECT_Y:
                        obj.position.y=OBJECT_Y; obj.velocity.y*=-.25; obj.velocity.x*=.65; obj.velocity.z*=.65
                else:
                    obj.position.y=OBJECT_Y; obj.velocity=Vec3(0,0,0)
                    obj.position.x=lerp(obj.position.x,obj.rest_pos.x,dt*1.8)
                    obj.position.z=lerp(obj.position.z,obj.rest_pos.z,dt*1.8)
                    obj.color=lerp(obj.color,obj.c_idle,dt*2.0)

    def _update_ui(self):
        if not self.ui_gesture: return
        self.ui_gesture.text = f"Gesture  :  {self.current_gesture}"
        V=self.magnet.strength*(24. if self.current_magnet==MagnetState.ON else 8.4)
        A=self.magnet.strength*(3.2 if self.current_magnet==MagnetState.ON else 1.1)
        if self.current_magnet==MagnetState.ON:
            self.ui_magnet.text=f"Magnet   :  ON  ●  [{V:.0f}V / {A:.1f}A]"; self.ui_magnet.color=C_UI_ON
        elif self.current_magnet==MagnetState.PRECISION:
            self.ui_magnet.text=f"Magnet   :  PRECISION  ◉  [{V:.1f}V]"; self.ui_magnet.color=C_UI_PREC
        else:
            self.ui_magnet.text="Magnet   :  OFF  ○"; self.ui_magnet.color=C_UI_OFF
        att=sum(1 for o in self.metal_objects if o.attached)
        if att:   self.ui_objects.text=f"Objects  :  {att}/{len(self.metal_objects)} attracted  ↑"; self.ui_objects.color=C_UI_ON
        elif self.magnet.is_active(): self.ui_objects.text="Objects  :  Approaching..."; self.ui_objects.color=C_UI_PREC
        else:     self.ui_objects.text="Objects  :  Idle  —"; self.ui_objects.color=C_UI_WHITE
        if self.ui_voltage:
            flux=self.magnet.strength*(0.85 if self.current_magnet==MagnetState.ON else 0.30)
            self.ui_voltage.text=f"Flux     :  {flux:.2f} T   Temp : {self._temp:.0f}°C"
            self.ui_voltage.color=C_UI_PREC if self._temp>35 else C_UI_DIM
        self.ui_fps.text=f"FPS      :  {int(1/max(time.dt,.001))}"


class MagnoGloveSimulation:
    def __init__(self, shared_state):
        self.shared_state=shared_state; self.magnet=MagnetController()
        self.app=Ursina(title="MagnoGlove Pro – Electromagnetic Glove Simulation  v2.0",borderless=False,fullscreen=False)
        window.color=C_BG
        self._build_scene(); self._build_ui()

    def _build_scene(self):
        camera.position=Vec3(0,2.5,-16); camera.rotation_x=-7
        AmbientLight(color=color.rgba(60,70,105,255))
        dl=DirectionalLight(); dl.look_at(Vec3(1,-2,1))
        Entity(model='quad',color=color.rgb(3,5,15),scale=(60,35),position=Vec3(0,2,16))
        Entity(model='cube',color=C_TABLE_BODY,scale=(18,.24,10),position=Vec3(0,TABLE_Y-.12,0))
        Entity(model='cube',color=C_TABLE_TOP,scale=(18,.05,10),position=Vec3(0,TABLE_Y+.02,0))
        Entity(model='cube',color=color.rgba(0,120,200,55),scale=(18,.02,.04),position=Vec3(0,TABLE_Y+.05,-5.0))
        for lx,lz in [(-8.2,-4.5),(8.2,-4.5),(-8.2,4.5),(8.2,4.5)]:
            Entity(model='cube',color=color.rgb(18,12,6),scale=(.2,3.5,.2),position=Vec3(lx,TABLE_Y-1.75,lz))
        for xi in range(-9,10):
            Entity(model='cube',color=C_GRID,scale=(.012,.008,10),position=Vec3(xi,TABLE_Y+.065,0))
        for zi in range(-5,6):
            Entity(model='cube',color=C_GRID,scale=(18,.008,.012),position=Vec3(0,TABLE_Y+.065,zi))
        glove=Entity(model='cube',color=C_GLOVE_IDLE,scale=(1.6,.45,1.0),position=GLOVE_POS)
        for fx in [-.48,-.16,.16,.48]:
            Entity(model='cube',color=C_FINGER,scale=(.22,.55,.25),position=Vec3(GLOVE_POS.x+fx,GLOVE_POS.y+.50,GLOVE_POS.z))
        Entity(model='cube',color=C_FINGER,scale=(.25,.20,.42),position=Vec3(GLOVE_POS.x-.85,GLOVE_POS.y+.05,GLOVE_POS.z))
        coil_band=Entity(model='cube',color=C_COIL_IDLE,scale=(1.45,.06,1.05),position=Vec3(GLOVE_POS.x,GLOVE_POS.y,GLOVE_POS.z))
        Entity(model='cube',color=color.rgb(35,40,65),scale=(.07,4.5,.07),position=Vec3(GLOVE_POS.x,GLOVE_POS.y+2.6,GLOVE_POS.z))
        rings=[Entity(model='circle',color=color.clear,scale=0,position=GLOVE_POS,rotation=Vec3(90,0,0)) for _ in range(RING_COUNT)]
        glow=Entity(model='sphere',color=color.clear,scale=0,position=GLOVE_POS)
        metal_objects=[MetalObject(*cfg) for cfg in OBJECT_CONFIGS]
        Entity(model='cube',color=C_CONSOLE,scale=(18,3.2,.7),position=Vec3(0,TABLE_Y+1.6,5.0))
        screen_entities=[]
        for sx in [-6,-2,2,6]:
            s=Entity(model='quad',color=color.rgba(0,160,255,90),scale=(2.8,1.2),position=Vec3(sx,TABLE_Y+1.9,4.64))
            screen_entities.append(s)
            for ry in [-.35,-.15,.05,.25]:
                Entity(model='quad',color=color.rgba(0,200,255,28),scale=(2.6,.035),position=Vec3(sx,TABLE_Y+1.9+ry,4.63))
        self.ctrl=SimController(self.shared_state,self.magnet)
        self.ctrl.glove=glove; self.ctrl.coil_band=coil_band
        self.ctrl.metal_objects=metal_objects; self.ctrl.rings=rings
        self.ctrl.glow_sphere=glow; self.ctrl.screen_entities=screen_entities

    def _build_ui(self):
        Entity(parent=camera.ui,model='quad',color=color.rgba(5,8,22,240),scale=(.50,.40),position=Vec3(-.575,.375,0))
        Entity(parent=camera.ui,model='quad',color=color.rgba(0,160,255,65),scale=(.502,.402),position=Vec3(-.575,.375,0))
        Text(text="⚡  MagnoGlove Pro  ⚡",parent=camera.ui,scale=1.35,color=C_UI_TITLE,position=Vec3(-.795,.490))
        Text(text="━"*32,parent=camera.ui,scale=.85,color=color.rgba(0,170,255,85),position=Vec3(-.795,.465))
        self.ctrl.ui_gesture=Text(text="Gesture  :  --",parent=camera.ui,scale=.90,color=C_UI_WHITE,position=Vec3(-.795,.440))
        self.ctrl.ui_magnet=Text(text="Magnet   :  OFF  ○",parent=camera.ui,scale=.90,color=C_UI_OFF,position=Vec3(-.795,.414))
        self.ctrl.ui_objects=Text(text="Objects  :  Idle  —",parent=camera.ui,scale=.90,color=C_UI_WHITE,position=Vec3(-.795,.388))
        self.ctrl.ui_voltage=Text(text="Flux     :  0.00 T   Temp : 24°C",parent=camera.ui,scale=.88,color=C_UI_DIM,position=Vec3(-.795,.362))
        Text(text="━"*32,parent=camera.ui,scale=.85,color=color.rgba(0,170,255,50),position=Vec3(-.795,.340))
        self.ctrl.ui_fps=Text(text="FPS      :  --",parent=camera.ui,scale=.82,color=C_UI_DIM,position=Vec3(-.795,.318))
        Text(text="  ✊ Fist=ON     ✋ Open=OFF     👌 Pinch=Precision     ESC=Exit  ",parent=camera.ui,scale=.80,color=color.rgb(75,145,200),position=Vec3(-.77,-.468))

    def run(self):
        self.app.run()