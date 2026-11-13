"""A compact house-shaped space habitat placed on the existing mission map.

Geometry only (plus the animations of its machines); the *rules* of what each station does live in
``Game`` (oxygen via ``astro.suit``, the lab via ``MissionState.lab_analyze``).  Every interactable has an
invisible hit-box carrying an ``obj_id`` that starts with ``hab_`` so the game's existing crosshair raycast
finds it:

    hab_door      sliding airlock door (control panels outside and inside)
    hab_analyzer  scientific analyzer machine
    hab_bed       astronaut bunk
    hab_locker    tool storage / recharge locker
    hab_o2        oxygen refill station (outside, beside the door)

Local frame: the habitat is 9 x 7, the airlock door is on the +x side.
"""
import math

from ursina import *  # noqa: F401,F403
from panda3d.core import TransparencyAttrib

from .. import config
from . import ui
from .world_shader import LIT

HULL = (0.84, 0.87, 0.92)
TRIM = (0.12, 0.16, 0.26)
ACCENT = (0.16, 0.83, 1.0)
ORANGE = (0.95, 0.5, 0.12)
WALL_T = 0.25
H = 3.2            # wall height above the floor
Y0 = 0.15          # floor top
HALF_X, HALF_Z = 4.5, 3.5
INTERACT_RANGE = 6.0


def C(rgb, a=1.0):
    return Color(rgb[0], rgb[1], rgb[2], a)


def dim(rgb, f):
    return tuple(max(0.0, min(1.0, c * f)) for c in rgb)


class Habitat:
    def __init__(self, world, x, z, heading=0.0):
        self.world = world
        self.pos = (x, z)
        self.heading = heading
        self.root = Entity(position=(x, 0, z), rotation_y=heading)
        world.entities.append(self.root)
        self.door_open = False
        self._door_anim_until = 0.0
        self._lab_until = 0.0
        self._locker_until = 0.0
        self._t = 0.0
        self._o2_key = None
        self.hitboxes = {}
        self.names = {}
        self._build()

    # ------------------------------------------------------------------ helpers
    def box(self, size, pos, col=HULL, lit=True, alpha=1.0, collider=False, parent=None, tex=None, **kw):
        e = Entity(parent=parent or self.root, model=kw.pop("model", "cube"), scale=size, position=pos, color=C(col, alpha),
                   shader=LIT if lit else None, collider="box" if collider else None, **kw)
        if tex:
            t = ui.tex(tex)
            if t is not None:
                e.texture = t
        if not lit:
            e.setLightOff()
        if alpha < 1.0:
            e.setTransparency(TransparencyAttrib.MAlpha)
        return e

    def hit(self, obj_id, size, pos):
        """Invisible hit-box: blocks movement and is what the crosshair raycast finds."""
        e = Entity(parent=self.root, model="cube", scale=size, position=pos, color=Color(0, 0, 0, 0), collider="box",
                   obj_id=obj_id)
        e.setTransparency(TransparencyAttrib.MAlpha)
        self.hitboxes.setdefault(obj_id, []).append(e)
        return e

    def local(self, wx, wz):
        """World xz -> habitat-local xz."""
        dx, dz = wx - self.pos[0], wz - self.pos[1]
        a = math.radians(self.heading)
        return dx * math.cos(a) - dz * math.sin(a), dx * math.sin(a) + dz * math.cos(a)

    def inside(self, wx, wz):
        lx, lz = self.local(wx, wz)
        return abs(lx) < HALF_X - 0.2 and abs(lz) < HALF_Z - 0.2

    def distance_to(self, obj_id, wx, wz):
        """Distance (horizontal) from a world point to the nearest hit-box of a station."""
        best = 1e9
        for e in self.hitboxes.get(obj_id, []):
            p = e.world_position
            best = min(best, math.hypot(p.x - wx, p.z - wz) - max(e.world_scale.x, e.world_scale.z) * 0.5)
        return best

    # ------------------------------------------------------------------ walls with real openings
    def _wall(self, axis, fixed, lo, hi, openings, col=HULL):
        def seg(a, b, ya, yb):
            if b - a < 0.01 or yb - ya < 0.01:
                return
            cx, cy = (a + b) / 2, Y0 + (ya + yb) / 2
            if axis == "z":
                self.box((WALL_T, yb - ya, b - a), (fixed, cy, cx), col, collider=True)
            else:
                self.box((b - a, yb - ya, WALL_T), (cx, cy, fixed), col, collider=True)
        cur = lo
        for o in sorted(openings, key=lambda o: o["c"]):
            a, b = o["c"] - o["w"] / 2, o["c"] + o["w"] / 2
            seg(cur, a, 0, H)
            seg(a, b, 0, o["sill"])
            seg(a, b, o["sill"] + o["h"], H)
            cy = Y0 + o["sill"] + o["h"] / 2
            t = WALL_T + 0.07
            for (pa, pb, py, ph) in ((a, a + 0.07, cy, o["h"]), (b - 0.07, b, cy, o["h"])):
                self._trim(axis, fixed, (pa + pb) / 2, py, 0.07, ph, t)
            for py in (Y0 + o["sill"], Y0 + o["sill"] + o["h"]):
                self._trim(axis, fixed, (a + b) / 2, py, b - a, 0.07, t)
            if o.get("glass", True):
                pane = (0.04, o["h"], b - a) if axis == "z" else (b - a, o["h"], 0.04)
                pos = (fixed, cy, (a + b) / 2) if axis == "z" else ((a + b) / 2, cy, fixed)
                g = self.box(pane, pos, (0.45, 0.8, 1.0), lit=False, alpha=0.3, collider=True)
                self.glass.append(g)
            cur = b
        seg(cur, hi, 0, H)

    def _trim(self, axis, fixed, along, y, length, height, thick):
        if axis == "z":
            self.box((thick, height, length), (fixed, y, along), TRIM)
        else:
            self.box((length, height, thick), (along, y, fixed), TRIM)

    # ------------------------------------------------------------------ build
    def _build(self):
        self.glass = []
        hx, hz = HALF_X, HALF_Z
        # foundation, floor with metal plating, ceiling
        self.box((9.7, 0.2, 7.7), (0, 0.0, 0), dim(TRIM, 1.4), collider=True)
        self.box((9.0, 0.1, 7.0), (0, Y0 - 0.05, 0), (0.55, 0.6, 0.7), tex="ground_orbital.png", texture_scale=(2.2, 1.8))
        self.box((9.0, 0.12, 7.0), (0, Y0 + H + 0.06, 0), (0.78, 0.82, 0.9))
        # walls (door + windows are real openings)
        self._wall("z", hx, -hz, hz, [dict(c=0, w=1.8, sill=0, h=2.5, glass=False),
                                      dict(c=-2.5, w=1.3, sill=1.0, h=1.25), dict(c=2.5, w=1.3, sill=1.0, h=1.25)])
        self._wall("z", -hx, -hz, hz, [dict(c=0, w=2.8, sill=0.9, h=1.4)])
        self._wall("x", hz, -hx, hx, [dict(c=0.3, w=1.4, sill=1.0, h=1.2)])
        self._wall("x", -hz, -hx, hx, [dict(c=-2.2, w=1.6, sill=1.0, h=1.2), dict(c=1.9, w=1.6, sill=1.0, h=1.2)])
        # corner posts and orange safety band
        for sx in (-1, 1):
            for sz in (-1, 1):
                self.box((0.34, H + 0.2, 0.34), (sx * hx, Y0 + H / 2, sz * hz), TRIM)
        for sz in (-1, 1):
            self.box((9.1, 0.12, 0.04), (0, Y0 + 0.45, sz * (hz + 0.14)), ORANGE)
        self._roof()
        self._door()
        self._interior()
        self._exterior()

    def _roof(self):
        pitch = 1.15
        slope = math.degrees(math.atan2(pitch, hz := HALF_Z + 0.35))
        top = Y0 + H + 0.12
        for sz in (-1, 1):
            slab = Entity(parent=self.root, position=(0, top + pitch / 2, sz * hz / 2), rotation_x=sz * slope)
            self.box((9.8, 0.16, math.hypot(hz, pitch) + 0.1), (0, 0, 0), (0.72, 0.76, 0.84), parent=slab)
            if sz == 1:                                         # solar panels on one slope
                for i in range(3):
                    self.box((2.7, 0.07, 2.4), (-3.0 + i * 3.0, 0.12, 0), (0.07, 0.14, 0.4), parent=slab, tex="white_cube",
                             texture_scale=(6, 5))
                    self.box((2.85, 0.05, 0.06), (-3.0 + i * 3.0, 0.1, 1.25), (0.8, 0.82, 0.88), parent=slab)
        self.box((9.9, 0.2, 0.2), (0, top + pitch, 0), TRIM)                 # ridge beam
        verts = lambda x: [Vec3(x, top, -hz), Vec3(x, top, hz), Vec3(x, top + pitch, 0)]
        for sx in (-1, 1):                                                    # gable ends close the roof
            g = Entity(parent=self.root, model=Mesh(vertices=verts(sx * 4.62), triangles=[(0, 1, 2), (2, 1, 0)]),
                       color=C(HULL), double_sided=True, shader=LIT)
        for x in (-2.2, 1.0):                                                 # roof vents and a chimney-like scrubber
            self.box((0.5, 0.5, 0.5), (x, top + pitch + 0.35, -0.6), TRIM)
            self.box((0.34, 0.1, 0.34), (x, top + pitch + 0.65, -0.6), ACCENT, lit=False)
        self.box((0.12, 3.0, 0.12), (-3.6, top + pitch + 1.5, 1.0), (0.7, 0.72, 0.78))      # antenna mast
        self.box((0.9, 0.06, 0.06), (-3.6, top + pitch + 2.2, 1.0), (0.7, 0.72, 0.78))
        self.beacon = self.box((0.2, 0.2, 0.2), (-3.6, top + pitch + 3.05, 1.0), ui.RED, lit=False, model="sphere")

    def _door(self):
        hx = HALF_X
        # airlock frame, porch canopy, steps, status light
        self.box((0.3, 2.65, 2.1), (hx + 0.02, Y0 + 1.3, 0), dim(TRIM, 1.2))
        self.box((0.34, 0.2, 2.3), (hx + 0.04, Y0 + 2.62, 0), ACCENT, lit=False)
        self.box((2.3, 0.12, 3.4), (hx + 1.3, Y0 + 2.95, 0), (0.72, 0.76, 0.84))
        for sz in (-1, 1):
            self.box((0.14, 2.95, 0.14), (hx + 2.35, Y0 + 1.45, sz * 1.55), TRIM)
        self.box((1.6, 0.08, 3.2), (hx + 1.3, Y0 + 2.88, 0), ACCENT, lit=False, alpha=0.9)   # canopy light strip
        self.box((1.7, 0.12, 2.6), (hx + 1.15, 0.0, 0), (0.5, 0.54, 0.62), collider=True)    # step
        self.status = self.box((0.22, 0.22, 0.22), (hx + 0.2, Y0 + 2.45, 0.0), ui.RED, lit=False, model="sphere")
        # sliding leaf rides on the outside face and slides up over the header
        self.door_closed_y = Y0 + 1.25
        self.leaf = Entity(parent=self.root, position=(hx + 0.2, self.door_closed_y, 0))
        self.leaf_body = self.box((0.1, 2.5, 1.85), (0, 0, 0), (0.62, 0.66, 0.74), collider=True, parent=self.leaf)
        self.box((0.04, 0.16, 1.5), (0.07, 0.0, 0), ORANGE, parent=self.leaf, lit=False)
        self.box((0.04, 1.2, 0.08), (0.07, -0.2, 0), dim(TRIM, 1.5), parent=self.leaf)        # centre seam
        for sx_pos in (hx + 0.34, hx - 0.34):                                 # control panels (outside / inside)
            sgn = 1 if sx_pos > hx else -1
            self.box((0.12, 0.42, 0.34), (sx_pos, Y0 + 1.45, 1.45 if sgn > 0 else 1.2), TRIM)
            self.box((0.05, 0.12, 0.12), (sx_pos + sgn * 0.07, Y0 + 1.5, 1.45 if sgn > 0 else 1.2), ACCENT, lit=False)
            self.hit("hab_door", (0.5, 0.7, 0.6), (sx_pos + sgn * 0.1, Y0 + 1.45, 1.45 if sgn > 0 else 1.2))

    def _interior(self):
        # ceiling light panels and a warm floor glow so the inside reads as lived-in
        for x in (-2.8, 0.0, 2.8):
            self.box((1.6, 0.05, 0.5), (x, Y0 + H - 0.02, 0), (0.95, 0.98, 1.0), lit=False)
        self.box((8.4, 0.03, 0.04), (0, Y0 + 0.7, -HALF_Z + 0.14), ACCENT, lit=False)          # wall accent line
        # ---- scientific analyzer (back wall)
        ax, az = -3.5, -1.9
        self.box((1.0, 1.0, 1.8), (ax, Y0 + 0.5, az), (0.3, 0.33, 0.4))
        self.box((0.9, 0.12, 1.7), (ax, Y0 + 1.06, az), (0.8, 0.82, 0.88))
        self.dish = Entity(parent=self.root, position=(ax, Y0 + 1.5, az))
        self.box((0.12, 0.5, 0.12), (0, -0.2, 0), (0.6, 0.62, 0.7), parent=self.dish)
        self.box((0.7, 0.07, 0.7), (0, 0.1, 0), (0.85, 0.87, 0.92), parent=self.dish, model="sphere")
        self.box((0.14, 0.14, 0.14), (0.28, 0.2, 0), ACCENT, parent=self.dish, lit=False, model="sphere")
        self.lab_screen = self.box((0.05, 0.6, 1.2), (ax + 0.52, Y0 + 0.65, az), (0.02, 0.1, 0.12), lit=False)
        self.lab_bars = []
        for i in range(8):
            b = self.box((0.06, 0.05, 0.1), (ax + 0.56, Y0 + 0.42, az - 0.5 + i * 0.14), ui.GREEN, lit=False)
            self.lab_bars.append(b)
        self.lab_led = self.box((0.07, 0.1, 0.1), (ax + 0.55, Y0 + 0.95, az + 0.7), ui.GREEN, lit=False, model="sphere")
        self.box((0.5, 0.05, 0.5), (ax + 0.05, Y0 + 1.15, az + 0.55), (0.9, 0.9, 0.95))           # sample tray
        self.hit("hab_analyzer", (1.3, 2.0, 2.0), (ax + 0.1, Y0 + 1.0, az))
        # ---- astronaut bunk (north wall)
        bx, bz = -2.1, 2.75
        self.box((2.3, 0.28, 0.95), (bx, Y0 + 0.4, bz), TRIM)
        self.box((2.2, 0.22, 0.88), (bx, Y0 + 0.66, bz), (0.55, 0.78, 1.0))                      # mattress
        self.box((0.7, 0.14, 0.7), (bx - 0.75, Y0 + 0.84, bz), (0.97, 0.97, 1.0))                # pillow
        self.box((1.3, 0.1, 0.9), (bx + 0.35, Y0 + 0.82, bz), (0.16, 0.5, 0.75))                 # blanket
        for sx in (-1, 1):
            self.box((0.1, 0.5, 0.95), (bx + sx * 1.18, Y0 + 0.4, bz), TRIM)
        self.box((0.12, 0.12, 0.2), (bx - 1.0, Y0 + 1.5, HALF_Z - 0.18), (1.0, 0.85, 0.5), lit=False, model="sphere")  # reading lamp
        self.hit("hab_bed", (2.4, 1.2, 1.1), (bx, Y0 + 0.6, bz))
        # ---- tool locker (north wall)
        lx, lz = 2.5, 3.0
        self.box((1.0, 2.2, 0.55), (lx, Y0 + 1.1, lz), (0.28, 0.32, 0.4))
        self.locker_doors = []
        for i, sx in enumerate((-0.25, 0.25)):
            d = self.box((0.46, 2.0, 0.05), (sx, 0, -0.3), (0.6, 0.64, 0.72), parent=self.root)
            d.position = (lx + sx, Y0 + 1.1, lz - 0.3)
            self.locker_doors.append((d, lx + sx))
        self.locker_leds = []
        for i, icon in enumerate(("icon_scan", "icon_collect", "icon_analyze", "icon_repair")):
            ic = Entity(parent=self.root, model="quad", texture=ui.tex(icon + ".png"), scale=0.22,
                        position=(lx - 0.33 + i * 0.22, Y0 + 1.55, lz - 0.34), color=C(ACCENT))
            ic.setTransparency(TransparencyAttrib.MAlpha)
            ic.setLightOff()
            led = self.box((0.12, 0.05, 0.03), (lx - 0.33 + i * 0.22, Y0 + 1.35, lz - 0.34), ui.GREEN, lit=False)
            self.locker_leds.append(led)
        self.hit("hab_locker", (1.2, 2.3, 0.9), (lx, Y0 + 1.15, lz - 0.1))
        # ---- table, chair and a plant for life
        self.box((1.2, 0.08, 0.7), (0.3, Y0 + 0.78, -2.5), (0.7, 0.72, 0.78))
        self.box((0.1, 0.78, 0.1), (0.3, Y0 + 0.39, -2.5), TRIM)
        self.box((0.5, 0.08, 0.5), (0.3, Y0 + 0.46, -1.7), (0.3, 0.4, 0.6))
        self.box((0.5, 0.5, 0.08), (0.3, Y0 + 0.74, -1.46), (0.3, 0.4, 0.6))
        self.box((0.4, 0.4, 0.4), (3.6, Y0 + 0.2, -2.8), TRIM)
        self.box((0.5, 0.45, 0.5), (3.6, Y0 + 0.6, -2.8), (0.25, 0.7, 0.3), model="sphere")

    def _exterior(self):
        hx, hz = HALF_X, HALF_Z
        # ---- oxygen refill station beside the door
        sx, sz = 5.6, -2.6
        self.box((0.9, 1.5, 0.55), (sx, 0.85, sz), (0.8, 0.84, 0.9))
        self.box((0.95, 0.12, 0.6), (sx, 1.65, sz), TRIM)
        self.o2_screen = Entity(parent=self.root, model="quad", scale=(0.62, 0.34), position=(sx - 0.0, 1.15, sz - 0.29),
                                rotation_y=180)
        self.o2_screen.setLightOff()
        self._o2_face = None
        for k, off in enumerate((-0.55, 0.55)):                                  # tall oxygen tanks
            tank = self.box((0.5, 1.7, 0.5), (sx + off * 0.0 + (-0.3 if k == 0 else 0.3), 0.95, sz - 0.95),
                            (0.85, 0.9, 0.98), model="sphere")
            self.box((0.52, 0.12, 0.52), (tank.x, 0.95, tank.z), ORANGE, model="sphere")
            self.box((0.2, 0.18, 0.2), (tank.x, 1.85, tank.z), TRIM)
        for i in range(10):                                                      # hose looping from console to ground reel
            t = i / 9
            self.box((0.07, 0.07, 0.2), (sx + 0.6 + 0.35 * math.sin(t * 3.0), 1.0 - 0.8 * t + 0.1 * math.sin(t * 6), sz - 0.1 + 0.55 * t),
                     (0.1, 0.1, 0.12), rotation_y=20)
        self.o2_ring = self.box((0.7, 0.04, 0.7), (sx, 0.14, sz + 0.35), ACCENT, lit=False, model="sphere", alpha=0.55)
        self.hit("hab_o2", (1.3, 1.9, 1.3), (sx, 0.95, sz - 0.2))
        # ---- external gas tanks and pipe run on the north-east wall, floodlights at the corners
        for k in range(2):
            self.box((0.8, 1.1, 0.8), (-1.0 + k * 1.2, 0.7, hz + 0.9), (0.82, 0.86, 0.92), model="sphere")
            self.box((0.82, 0.1, 0.82), (-1.0 + k * 1.2, 0.7, hz + 0.9), ORANGE, model="sphere")
        self.box((0.1, 0.1, 1.0), (-0.4, 0.9, hz + 0.5), (0.5, 0.52, 0.58))
        for sx_, sz_ in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            self.box((0.2, 0.18, 0.2), (sx_ * (hx + 0.15), Y0 + H - 0.1, sz_ * (hz + 0.15)), (1.0, 0.97, 0.85), lit=False, model="sphere")

    # ------------------------------------------------------------------ animations driven by gameplay
    def set_door(self, opened: bool, instant=False):
        self.door_open = opened
        y = self.door_closed_y + (2.6 if opened else 0.0)
        if opened:
            self.leaf_body.collider = None
        if instant:
            self.leaf.y = y
        else:
            self.leaf.animate_y(y, 0.8, curve=curve.in_out_cubic)
        if not opened:
            invoke(setattr, self.leaf_body, "collider", "box", delay=0.1)
        self.status.color = C(ui.GREEN if opened else ui.RED)

    def play_lab(self, secs=2.2):
        self._lab_until = self._t + secs

    def play_locker(self, charges_avg=100.0):
        self._locker_until = self._t + 1.2
        for d, x0 in self.locker_doors:
            d.animate_x(x0 + (0.42 if x0 > 2.5 else -0.42), 0.35, curve=curve.out_cubic)
            invoke(d.animate_x, x0, 0.4, curve=curve.in_out_cubic, delay=1.1)

    def set_locker_leds(self, charges):
        for led, (name, v) in zip(self.locker_leds, charges.items()):
            led.color = C(ui.GREEN if v > 60 else (ui.GOLD if v > 25 else ui.RED))

    def set_o2_screen(self, pct, filling=False):
        key = (int(pct), filling)
        if key == self._o2_key:
            return
        self._o2_key = key
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (256, 140), (2, 14, 22))
        d = ImageDraw.Draw(img)
        try:
            f1 = ImageFont.truetype(str(config.ASSETS_DIR / "fonts" / "Orbitron-Bold.ttf"), 44)
            f2 = ImageFont.truetype(str(config.ASSETS_DIR / "fonts" / "Orbitron-Bold.ttf"), 18)
        except Exception:  # pragma: no cover
            f1 = f2 = ImageFont.load_default()
        col = (255, 200, 60) if filling else (60, 235, 255)
        d.rectangle([2, 2, 253, 137], outline=col, width=2)
        d.text((14, 10), "O2 STATION", font=f2, fill=col)
        d.text((240, 44), f"{int(pct)}%", font=f1, fill=col, anchor="ra")
        for i in range(10):
            x0 = 14 + i * 23
            d.rectangle([x0, 112, x0 + 18, 126], fill=col if pct > i * 10 else (10, 38, 48))
        self.o2_screen.texture = Texture(img)
        self.o2_screen.setLightOff()
        self.o2_ring.color = C(ui.GOLD if filling else ACCENT, 0.7 if filling else 0.35)

    def update(self, t, dt):
        self._t += dt
        self.beacon.color = C(ui.RED, 1.0 if int(t * 1.5) % 2 == 0 else 0.25)
        if self._t < self._lab_until:
            self.dish.rotation_y += 220 * dt
            self.lab_led.color = C(ui.GOLD if int(t * 8) % 2 else ui.WHITE)
            for b in self.lab_bars:
                b.scale_y = 0.05 + 0.5 * abs(math.sin(t * 9 + b.z * 7))
                b.y = Y0 + 0.42 + b.scale_y / 2 - 0.02
        else:
            self.dish.rotation_y += 12 * dt
            self.lab_led.color = C(ui.GREEN)
            for b in self.lab_bars:
                b.scale_y = 0.05
                b.y = Y0 + 0.42
