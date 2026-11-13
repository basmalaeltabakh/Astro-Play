"""First-person view model: the astronaut's suited arms and gloved hands, the four tools held in the right
hand (with equip and use animations), and the digital oxygen wristwatch on the left wrist.

Everything is parented to the camera, so it moves with the player's view.  It has no colliders (it never
blocks raycasts) and no game rules: ``Game`` calls ``equip``, ``play_use`` and ``set_oxygen``.
"""
import math
import random

from ursina import *  # noqa: F401,F403
from ursina.shaders import basic_lighting_shader as LIT
from panda3d.core import TransparencyAttrib

from .. import config
from . import ui

METAL = (0.55, 0.58, 0.64)
DARK = (0.12, 0.14, 0.2)
GLOVE = (0.86, 0.88, 0.92)
GLOVE_SHADE = (0.7, 0.73, 0.8)


def C(rgb, a=1.0):
    return Color(rgb[0], rgb[1], rgb[2], a)


def dim(rgb, f):
    return tuple(max(0.0, min(1.0, c * f)) for c in rgb)


def box(parent, size, pos=(0, 0, 0), col=METAL, rot=(0, 0, 0), model="cube", lit=True, alpha=1.0, **kw):
    e = Entity(parent=parent, model=model, scale=size, position=pos, rotation=rot, color=C(col, alpha),
               shader=LIT if lit else None, **kw)
    if not lit:
        e.unlit = True
    if alpha < 1.0:
        e.setTransparency(TransparencyAttrib.MAlpha)
    return e


class WatchFace:
    """Renders the digital watch display (oxygen %, status colour, segment bar) into a texture."""

    COLORS = {"ok": (60, 235, 255), "low": (255, 190, 40), "critical": (255, 70, 70), "empty": (255, 70, 70)}

    def __init__(self):
        from PIL import ImageFont
        self._cache = {}
        try:
            self.big = ImageFont.truetype(str(config.ASSETS_DIR / "fonts" / "Orbitron-Bold.ttf"), 64)
            self.small = ImageFont.truetype(str(config.ASSETS_DIR / "fonts" / "Orbitron-Bold.ttf"), 22)
        except Exception:  # pragma: no cover
            self.big = self.small = ImageFont.load_default()

    def texture(self, pct: int, status: str, blink: bool):
        key = (pct, status, blink)
        if key not in self._cache:
            from PIL import Image, ImageDraw
            col = self.COLORS.get(status, self.COLORS["ok"])
            img = Image.new("RGB", (256, 128), (2, 14, 22))
            d = ImageDraw.Draw(img)
            d.rectangle([2, 2, 253, 125], outline=tuple(int(c * 0.45) for c in col), width=2)
            show = blink or status in ("ok",)
            d.text((14, 8), "O2", font=self.small, fill=col if show else tuple(int(c * 0.35) for c in col))
            txt = f"{pct}%"
            d.text((240, 34), txt, font=self.big, fill=col if show else tuple(int(c * 0.35) for c in col), anchor="ra")
            segs = 10
            for i in range(segs):
                x0 = 14 + i * 23
                on = pct > i * 10
                d.rectangle([x0, 104, x0 + 18, 118], fill=col if (on and show) else (10, 38, 48))
            self._cache[key] = Texture(img)
            if len(self._cache) > 400:
                self._cache.pop(next(iter(self._cache)))
        return self._cache[key]


class ViewModel(Entity):
    def __init__(self, suit_rgb=(0.95, 0.95, 1.0)):
        super().__init__(parent=camera)
        self.suit = suit_rgb
        self._t = 0.0
        self._busy_until = 0.0
        self.current = None
        self._walk_blend = 0.0
        self.bob = Entity(parent=self)
        self.face = WatchFace()
        self._watch_key = None
        self._build_right_arm()
        self._build_left_arm()
        self.tools = {
            "scanner": self._build_scanner(),
            "sampler": self._build_sampler(),
            "analyzer": self._build_analyzer(),
            "wrench": self._build_wrench(),
        }
        for t in self.tools.values():
            t.enabled = False

    # ------------------------------------------------------------------ construction
    def _glove(self, parent, left=False):
        """A gloved hand: palm, four fingers curled forward and a thumb."""
        g = Entity(parent=parent)
        box(g, (0.105, 0.05, 0.115), (0, -0.01, 0.0), GLOVE)
        box(g, (0.11, 0.03, 0.04), (0, -0.01, -0.07), dim(self.suit, 0.55))          # cuff ring
        for i in range(4):
            x = -0.039 + i * 0.026
            box(g, (0.023, 0.032, 0.075 - 0.006 * (i in (0, 3))), (x, 0.0, 0.092), GLOVE_SHADE)
            box(g, (0.021, 0.03, 0.04), (x, -0.028, 0.12), GLOVE_SHADE)               # curled tips
        side = -1 if left else 1
        box(g, (0.03, 0.032, 0.07), (side * 0.062, -0.01, 0.035), GLOVE_SHADE, (0, side * 25, 0))   # thumb
        return g

    def _sleeve(self, parent, length=0.52):
        s = Entity(parent=parent)
        box(s, (0.135, 0.125, length), (0, 0, length / 2 - 0.1), self.suit)
        box(s, (0.145, 0.135, 0.05), (0, 0, length - 0.13), dim(self.suit, 0.6))          # elbow-side panel line
        box(s, (0.03, 0.12, length * 0.9), (0.071, 0.0, length / 2 - 0.1), dim(self.suit, 0.82))   # seam shading
        return s

    def _build_right_arm(self):
        self.rig_r = Entity(parent=self.bob, position=(0.31, -0.41, 0.2))
        self.rest_r = Vec3(0.31, -0.41, 0.2)
        self.arm_r = Entity(parent=self.rig_r, rotation=(-22, -7, 0))
        self._sleeve(self.arm_r)
        self.hand_r = Entity(parent=self.arm_r, position=(0, 0.0, 0.5))
        self._glove(self.hand_r)
        self.mount = Entity(parent=self.hand_r, position=(0, 0.045, 0.05))      # tools sit in the fingers

    def _build_left_arm(self):
        self.rig_l = Entity(parent=self.bob, position=(-0.30, -0.37, 0.2))
        self.arm_l = Entity(parent=self.rig_l, rotation=(-32, 10, 0))
        self._sleeve(self.arm_l, 0.46)
        self.hand_l = Entity(parent=self.arm_l, position=(0, 0.0, 0.44))
        self._glove(self.hand_l, left=True)
        # wristwatch on the back of the left wrist
        wr = Entity(parent=self.arm_l, position=(0, 0.075, 0.33))
        box(wr, (0.15, 0.025, 0.12), (0, -0.04, 0), DARK)                              # strap
        box(wr, (0.135, 0.032, 0.105), (0, 0.0, 0), (0.18, 0.2, 0.27))                 # case
        screen = Entity(parent=wr, model="quad", scale=(0.112, 0.056), position=(0, 0.019, 0), rotation=(90, 0, 0),
                        texture=self.face.texture(100, "ok", True), color=color.white)
        screen.setLightOff()
        box(wr, (0.012, 0.014, 0.014), (0.072, 0.0, 0.03), (0.6, 0.65, 0.7))          # crown
        self.watch = wr
        self.watch_screen = screen

    def _scanner_parts(self):
        t = Entity(parent=self.mount)
        box(t, (0.1, 0.045, 0.17), (0, 0.005, 0.06), (0.2, 0.23, 0.3))                  # body
        box(t, (0.082, 0.012, 0.11), (0, 0.032, 0.06), (0.02, 0.1, 0.14))               # screen bezel
        scr = Entity(parent=t, model="quad", scale=(0.075, 0.1), position=(0, 0.039, 0.06), rotation=(90, 0, 0),
                     texture=ui.tex("pulse_ring.png"), color=C(ui.CYAN, 0.95))
        scr.setLightOff()
        scr.setTransparency(TransparencyAttrib.MAlpha)
        box(t, (0.025, 0.025, 0.1), (0, 0.012, 0.19), METAL)                            # emitter barrel
        em = box(t, (0.04, 0.04, 0.012), (0, 0.012, 0.248), ui.CYAN, lit=False)         # emitter lens (glows)
        box(t, (0.012, 0.012, 0.08), (0.035, 0.045, 0.02), METAL)                       # antenna
        box(t, (0.014, 0.014, 0.014), (0.035, 0.045, -0.02), ui.RED, lit=False)
        ring = Entity(parent=t, model="quad", texture=ui.tex("pulse_ring.png"), scale=0.05, position=(0, 0.012, 0.26),
                      color=C(ui.CYAN, 0.0))
        ring.setLightOff()
        ring.setTransparency(TransparencyAttrib.MAlpha)
        beam = box(t, (0.02, 0.02, 0.01), (0, 0.012, 0.26), ui.CYAN, lit=False, alpha=0.0)
        t._screen, t._emitter, t._ring, t._beam = scr, em, ring, beam
        return t

    def _build_scanner(self):
        return self._scanner_parts()

    def _build_sampler(self):
        t = Entity(parent=self.mount)
        box(t, (0.03, 0.03, 0.30), (0, 0.0, 0.1), (0.35, 0.37, 0.42))                   # handle / pole
        box(t, (0.036, 0.036, 0.07), (0, 0.0, -0.02), DARK)                             # grip
        scoop = Entity(parent=t, position=(0, -0.005, 0.27))
        box(scoop, (0.09, 0.03, 0.08), (0, -0.015, 0.0), (0.7, 0.72, 0.78))             # scoop bowl
        box(scoop, (0.09, 0.05, 0.015), (0, 0.0, 0.04), (0.78, 0.8, 0.85))              # lip
        for sx in (-1, 1):
            box(scoop, (0.012, 0.045, 0.08), (sx * 0.048, 0.0, 0.0), (0.6, 0.62, 0.68))
        vial = box(t, (0.03, 0.03, 0.12), (0.0, 0.058, 0.16), (0.6, 0.9, 1.0), alpha=0.45)  # sample vial
        fill = box(t, (0.022, 0.022, 0.06), (0.0, 0.058, 0.135), ui.GREEN, lit=False, alpha=0.0)
        box(t, (0.034, 0.034, 0.015), (0.0, 0.058, 0.225), DARK)
        t._scoop, t._vial_fill = scoop, fill
        return t

    def _build_analyzer(self):
        t = Entity(parent=self.mount)
        box(t, (0.1, 0.075, 0.15), (0, 0.015, 0.05), (0.22, 0.26, 0.2))                 # housing
        box(t, (0.075, 0.05, 0.1), (0, 0.025, 0.145), (0.3, 0.32, 0.36))
        lens = box(t, (0.06, 0.06, 0.03), (0, 0.025, 0.215), (0.05, 0.1, 0.12))         # sensor head
        glow = box(t, (0.04, 0.04, 0.01), (0, 0.025, 0.233), ui.GREEN, lit=False)
        scr = box(t, (0.08, 0.008, 0.07), (0, 0.056, 0.03), (0.01, 0.06, 0.05))
        bars = []
        for i in range(6):
            b = box(t, (0.008, 0.01, 0.04), (-0.03 + i * 0.012, 0.062, 0.03), ui.GREEN, lit=False)
            bars.append(b)
        led = box(t, (0.014, 0.014, 0.014), (0.04, 0.056, 0.095), ui.GOLD, lit=False)
        t._glow, t._bars, t._led = glow, bars, led
        return t

    def _build_wrench(self):
        t = Entity(parent=self.mount)
        box(t, (0.032, 0.02, 0.26), (0, 0.0, 0.1), (0.66, 0.68, 0.72))                  # shaft
        box(t, (0.04, 0.026, 0.08), (0, 0.0, 0.0), (0.9, 0.5, 0.12))                    # grip sleeve
        head = Entity(parent=t, position=(0, 0, 0.255))
        box(head, (0.09, 0.022, 0.05), (0, 0, 0.0), (0.7, 0.72, 0.76))                  # head block
        for sx in (-1, 1):                                                              # open-end jaws
            box(head, (0.025, 0.022, 0.06), (sx * 0.042, 0, 0.045), (0.7, 0.72, 0.76))
        box(head, (0.02, 0.03, 0.04), (0, 0.0, 0.0), (0.95, 0.55, 0.15), lit=False)
        t._head = head
        return t

    # ------------------------------------------------------------------ tools and animation
    def equip(self, tool: str, animate: bool = True):
        for name, m in self.tools.items():
            m.enabled = name == tool
        self.current = tool
        if animate:
            self.rig_r.position = self.rest_r + Vec3(0.05, -0.38, -0.05)
            self.rig_r.animate_position(self.rest_r, 0.28, curve=curve.out_back)
            self.rig_r.rotation_x = 25
            self.rig_r.animate("rotation_x", 0, 0.28, curve=curve.out_cubic)

    def _lock(self, secs):
        import time as _t
        self._busy_until = _t.time() + secs

    def play_use(self, tool: str, ok: bool = True):
        """Tool-specific use animation.  ok=False plays a short refusal shake instead."""
        m = self.tools.get(tool)
        if m is None:
            return
        r = self.rig_r
        if not ok:
            for i, dx in enumerate((0.02, -0.02, 0.012, 0.0)):
                invoke(setattr, r, "x", self.rest_r.x + dx, delay=0.04 * i)
            return
        if tool == "scanner":
            r.animate("rotation_x", -9, 0.12, curve=curve.out_cubic)
            invoke(r.animate, "rotation_x", 0, 0.3, curve=curve.in_out_cubic, delay=0.2)
            m._ring.scale, m._ring.color = 0.05, C(ui.CYAN, 0.95)
            m._ring.animate_scale(0.62, 0.6, curve=curve.out_expo)
            m._ring.animate_color(C(ui.CYAN, 0.0), 0.6, curve=curve.linear)
            m._ring.animate_z(1.4, 0.6, curve=curve.linear)
            invoke(setattr, m._ring, "z", 0.26, delay=0.62)
            m._beam.color = C(ui.CYAN, 0.55)
            m._beam.scale = (0.012, 0.012, 0.01)
            m._beam.animate_scale((0.012, 0.012, 1.5), 0.25, curve=curve.out_expo)
            m._beam.animate_color(C(ui.CYAN, 0.0), 0.5, curve=curve.linear)
            m._emitter.color = C(color.white)
            invoke(setattr, m._emitter, "color", C(ui.CYAN), delay=0.5)
        elif tool == "sampler":
            r.animate_position(self.rest_r + Vec3(0, -0.06, 0.2), 0.22, curve=curve.out_cubic)
            r.animate("rotation_x", 28, 0.22, curve=curve.out_cubic)
            sc = m._scoop
            invoke(sc.animate, "rotation_x", -38, 0.18, curve=curve.in_out_cubic, delay=0.24)
            invoke(r.animate_position, self.rest_r, 0.32, curve=curve.in_out_cubic, delay=0.45)
            invoke(r.animate, "rotation_x", 0, 0.32, curve=curve.in_out_cubic, delay=0.45)
            invoke(sc.animate, "rotation_x", 0, 0.2, curve=curve.in_out_cubic, delay=0.5)
            m._vial_fill.color = C(ui.GREEN, 0.0)
            invoke(m._vial_fill.animate_color, C(ui.GREEN, 0.95), 0.3, delay=0.45)
        elif tool == "analyzer":
            r.animate_position(self.rest_r + Vec3(-0.03, 0.06, 0.04), 0.2, curve=curve.out_cubic)
            invoke(r.animate_position, self.rest_r, 0.3, curve=curve.in_out_cubic, delay=0.8)
            for k in range(14):                                                        # spectrum bars dance
                for b in m._bars:
                    invoke(setattr, b, "scale_z", random.uniform(0.01, 0.06), delay=0.05 * k)
            for b in m._bars:
                invoke(setattr, b, "scale_z", 0.04, delay=0.78)
            for k in range(4):
                invoke(setattr, m._led, "color", C(ui.WHITE if k % 2 else ui.GOLD), delay=0.2 * k)
            m._glow.color = C(color.white)
            invoke(setattr, m._glow, "color", C(ui.GREEN), delay=0.8)
        elif tool == "wrench":
            r.animate_position(self.rest_r + Vec3(0, 0.0, 0.12), 0.15, curve=curve.out_cubic)
            for k in range(3):                                                         # turn the bolt back and forth
                invoke(m.animate, "rotation_z", -38, 0.1, curve=curve.in_out_cubic, delay=0.15 + k * 0.28)
                invoke(m.animate, "rotation_z", 0, 0.1, curve=curve.in_out_cubic, delay=0.27 + k * 0.28)
            invoke(r.animate_position, self.rest_r, 0.25, curve=curve.in_out_cubic, delay=1.0)
        self._lock(0.9)

    # ------------------------------------------------------------------ per-frame motion and the watch
    def update_motion(self, dt, moving, mouse_vel_x=0.0):
        self._t += dt
        self._walk_blend += ((1.0 if moving else 0.0) - self._walk_blend) * min(1.0, dt * 6)
        w = self._walk_blend
        self.bob.y = math.sin(self._t * 9.0) * 0.013 * w + math.sin(self._t * 1.6) * 0.0035   # step bob + breathing
        self.bob.x = math.cos(self._t * 4.5) * 0.009 * w
        target = max(-7.0, min(7.0, -mouse_vel_x * 220))
        self.bob.rotation_y += (target - self.bob.rotation_y) * min(1.0, dt * 8)
        self.bob.rotation_z = math.sin(self._t * 4.5) * 1.2 * w

    def set_oxygen(self, pct: float, status: str, t: float):
        """Update the wristwatch from the real oxygen level (flashes when low)."""
        p = int(max(0, min(100, math.ceil(pct))))
        blink = True if status == "ok" else int(t * (4 if status in ("critical", "empty") else 2)) % 2 == 0
        key = (p, status, blink)
        if key != self._watch_key:
            self._watch_key = key
            self.watch_screen.texture = self.face.texture(p, status, blink)
            self.watch_screen.setLightOff()

    def right_hand_visible(self):
        return self.rig_r.enabled and self.hand_r.enabled and self.hand_l.enabled and self.current is not None

    def watch_text(self):
        """What the watch currently shows (used by tests)."""
        return self._watch_key
