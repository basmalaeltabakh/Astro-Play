"""Builds the 3D mission environments (sky dome, lit planet in the sky, horizon hills with aerial haze,
craters, boulders, drifting dust and the composed mission props).  Presentation only - no game rules."""
import math
import random

from ursina import *  # noqa: F401,F403
from ursina.prefabs.first_person_controller import FirstPersonController
from .world_shader import LIT

from panda3d.core import TransparencyAttrib

from .. import config
from . import ui
from .habitat import Habitat

# mission -> (texture, position, scale, halo colour)   texture 'sun' = glowing disc
HAB_POS = (-17.0, -3.0)          # habitat origin on every map; its airlock faces +x toward the centre of the map
KEEPOUT = (-15.0, -3.0, 9.8)      # decorative rocks/craters are cleared inside this circle


SKY_BODY = {
    "moon": ("earth.png", (-55, 38, 120), 24, (0.35, 0.6, 1.0)),
    "mars": ("sun", (70, 45, 110), 16, (1.0, 0.9, 0.7)),
    "orbital": ("earth.png", (0, 10, 215), 160, (0.3, 0.6, 1.0)),
    "europa": ("jupiter.png", (-45, 42, 130), 70, (1.0, 0.75, 0.5)),
}
SUN_DIR = {"moon": (1, -0.7, 0.5), "mars": (-0.6, -0.9, 0.7), "orbital": (0.3, -1, 0.4), "europa": (0.8, -0.6, 0.8)}
SUN_COL = {"moon": (1.0, 0.97, 0.9), "mars": (1.0, 0.85, 0.7), "orbital": (1.0, 1.0, 1.0), "europa": (0.85, 0.9, 1.0)}
AMBIENT = {"moon": (0.30, 0.32, 0.42), "mars": (0.45, 0.33, 0.28), "orbital": (0.38, 0.4, 0.5), "europa": (0.34, 0.38, 0.5)}
HAZE = {"moon": (0.07, 0.09, 0.2), "mars": (0.9, 0.55, 0.38), "orbital": (0.05, 0.1, 0.28), "europa": (0.22, 0.27, 0.5)}


def C(rgb, a=1.0):
    return Color(rgb[0], rgb[1], rgb[2], a)


def shade(rgb, f):
    return tuple(max(0.0, min(1.0, c * f)) for c in rgb)


def mixc(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


class World:
    """Holds everything created for one mission so it can be updated and destroyed together."""

    def __init__(self, mission):
        self.mission = mission
        self.entities = []
        self.lights = []
        self.markers = {}
        self.dust = []
        self.planet = None
        self.player = None
        self.habitat = None
        self._rng = random.Random(mission.id)
        self._build()

    # -- helpers
    def ent(self, **k):
        k.setdefault("shader", LIT)
        e = Entity(**k)
        self.entities.append(e)
        return e

    def _build(self):
        m, rng = self.mission, self._rng
        gcol = C(m.ground_color)
        haze = HAZE[m.id]
        # -- sky dome with painted stars / milky way
        sky = Sky(texture=ui.tex(f"sky/sky_{m.id}.png"))
        self.entities.append(sky)
        # -- lights
        sun = DirectionalLight(shadows=config.SHADOWS, shadow_map_resolution=Vec2(2048, 2048), color=C(SUN_COL[m.id]))
        sun.look_at(Vec3(*SUN_DIR[m.id]))
        if config.SHADOWS:                                   # shadows cover the playable area around the lander/habitat
            area = Entity(position=(-3, 0, -4), scale=(70, 12, 62), visible=False)
            self.entities.append(area)
            sun.update_bounds(area)
        amb = AmbientLight(color=Color(*AMBIENT[m.id], 1))
        self.lights = [sun, amb]
        # -- ground
        gname = f"ground_{m.id}.png"
        rich = (config.ASSETS_DIR / "ui" / gname).exists()
        self.ent(model="plane", scale=(140, 1, 140), texture=ui.tex(gname if rich else "ground.png"),
                 texture_scale=((12, 12) if rich else (30, 30)), color=(Color(1.12, 1.12, 1.12, 1) if rich else gcol), collider="box")
        if (config.ASSETS_DIR / "ui" / f"detail_{m.id}.png").exists():      # crisp pebbles/grain for close range
            dt_ = self.ent(model="plane", scale=(140, 1, 140), y=0.008, shader=None, texture=ui.tex(f"detail_{m.id}.png"),
                           texture_scale=(46, 46), color=color.white)
            dt_.setTransparency(TransparencyAttrib.MAlpha)
        if (config.ASSETS_DIR / "ui" / f"mottle_{m.id}.png").exists():      # big soft patches hide the tiling
            mt = self.ent(model="plane", scale=(140, 1, 140), y=0.012, shader=None, texture=ui.tex(f"mottle_{m.id}.png"),
                          color=color.white)
            mt.setTransparency(TransparencyAttrib.MAlpha)
        self._craters(rng, m)
        # -- sky body with halo and terminator shading
        tname, spos, ssc, halo = SKY_BODY[m.id]
        if tname == "sun":
            h = self.ent(model="quad", shader=None, billboard=True, texture=ui.tex("sky/sun.png"), position=spos,
                         scale=ssc * 3.2, color=C((1, 1, 1), 1))
            h.setTransparency(TransparencyAttrib.MAlpha)
        else:
            self.planet = self.ent(model="sphere", shader=None, unlit=True, texture=ui.tex(f"sky/{tname}"),
                                   position=spos, scale=ssc, rotation_y=rng.uniform(0, 360))
            h = self.ent(model="quad", shader=None, billboard=True, texture=ui.tex("glow.png"), position=spos,
                         scale=ssc * 2.3, color=C(halo, 0.40))
            h.setTransparency(TransparencyAttrib.MAlpha)
            sh = self.ent(model="quad", shader=None, billboard=True, texture=ui.tex("planet_shade.png"),
                          position=(spos[0] * 0.995, spos[1], spos[2] * 0.995 - 0.5), scale=ssc * 1.02,
                          color=color.white)
            sh.setTransparency(TransparencyAttrib.MAlpha)
        # -- horizon hills fade toward the haze colour with distance (aerial perspective)
        for i in range(34):
            a = i / 34 * 6.283 + rng.uniform(-0.1, 0.1)
            d, hh, w = rng.uniform(78, 98), rng.uniform(9, 28), rng.uniform(22, 40)
            base = shade(m.ground_color, rng.uniform(0.45, 0.7))
            self.ent(model="sphere", position=(d * math.cos(a), -2, d * math.sin(a)), scale=(w, hh * 1.5, w),
                     color=C(mixc(base, haze, 0.45)))
        # -- boulders: textured, tinted, some angular slabs; clusters gather around the props
        for _ in range(60):
            sz = rng.uniform(0.5, 2.6)
            x, z = rng.uniform(-58, 58), rng.uniform(-58, 58)
            if abs(x) < 17 and abs(z) < 17:
                continue
            self._rock(x, z, sz, m.ground_color, rng, slab=rng.random() < 0.3)
        for o in m.objects:                                # pebble fields around every point of interest
            for _ in range(10):
                a = rng.uniform(0, 6.283)
                if abs(a - 4.712) < 0.9:                   # keep the approach from the lander clear of clutter
                    continue
                d = rng.uniform(max(o.size[0], o.size[2]) * 0.8, 6.5)
                self._rock(o.pos[0] + d * math.cos(a), o.pos[1] + d * math.sin(a), rng.uniform(0.18, 0.55), m.ground_color, rng,
                           slab=rng.random() < 0.35)
        for _ in range(140):
            sz = rng.uniform(0.1, 0.38)
            x, z = rng.uniform(-34, 34), rng.uniform(-34, 34)
            self.ent(model="sphere", scale=(sz * 1.4, sz * 0.7, sz), position=(x, sz * 0.15, z), texture=ui.tex("rock.png"),
                     color=C(shade(m.ground_color, rng.uniform(0.6, 1.1))))
        self._world_flavour(rng, m)
        self._clear_keepout()
        self.habitat = Habitat(self, HAB_POS[0], HAB_POS[1])
        self.shadow(HAB_POS[0], HAB_POS[1], 10.6, 8.2, 0.55, 1.6)
        self.shadow(HAB_POS[0] + 5.6, HAB_POS[1] - 2.6, 1.4, 1.4, 0.4)
        self.shadow(0, -25, 4.6, 4.6, 0.5, 1.4)
        self._footprints(rng, m)
        # -- lander + props
        self._lander()
        for o in m.objects:
            self.shadow(o.pos[0], o.pos[1], o.size[0] * 1.1, max(o.size[2], 1.4) * 1.1, 0.5, 1.4)
            self._prop(o)
            mk = self.ent(model="diamond", shader=None, unlit=True, scale=(0.5, 0.8, 0.5), color=C(ui.GOLD),
                          position=(o.pos[0], o.size[1] + 1.6, o.pos[1]), enabled=False)
            self.markers[o.id] = mk
        # -- floating dust motes near the player
        for _ in range(70):
            e = self.ent(model="quad", shader=None, billboard=True, texture=ui.tex("speck.png"),
                         position=(rng.uniform(-22, 22), rng.uniform(0.4, 7), rng.uniform(-30, 14)),
                         scale=rng.uniform(0.05, 0.14), color=C(mixc(haze, (1, 1, 1), 0.6), rng.uniform(0.25, 0.6)))
            e.setTransparency(TransparencyAttrib.MAlpha)
            e._ph = rng.uniform(0, 6.28)
            e._sp = rng.uniform(0.15, 0.5)
            self.dust.append(e)
        self.player = FirstPersonController(position=(0, 2, -18), speed=7)
        self.player.cursor.enabled = False
        self.entities.append(self.player)

    def decal(self, texture, x, z, size, heading=0.0, col=None, y=0.03, alpha=1.0):
        """Flat textured quad lying on the ground, rotated about the vertical axis."""
        root = Entity(position=(x, y, z), rotation_y=heading)
        self.entities.append(root)
        q = Entity(parent=root, model="quad", texture=ui.tex(texture), rotation_x=90, shader=None,
                   scale=size if isinstance(size, tuple) else (size, size), color=col or Color(1, 1, 1, alpha))
        q.setTransparency(TransparencyAttrib.MAlpha)
        return root

    def shadow(self, x, z, w, d, strength=0.45, length=1.0):
        """Soft contact shadow cast away from the sun (cheap, works on every graphics card)."""
        if not (config.ASSETS_DIR / "ui" / "blob_shadow.png").exists():
            return
        sx, _, sz = SUN_DIR[self.mission.id]
        n = math.hypot(sx, sz) or 1.0
        off = (w + d) * 0.28 * length
        heading = math.degrees(math.atan2(sx, sz))
        self.decal("blob_shadow.png", x + sx / n * off, z + sz / n * off, (w * 1.3 + off * 0.8, d * 1.2), heading,
                   y=0.02, col=Color(0, 0, 0, strength))

    def _rock(self, x, z, sz, base, rng, slab=False):
        """A boulder: rough textured ellipsoid or an angular slab, tilted, tinted and slightly sunk in the ground."""
        tint = shade(base, rng.uniform(1.5, 2.1))
        if sz > 0.3:
            self.shadow(x, z, sz * 1.4, sz * 1.2, 0.4)
        if slab:
            return self.ent(model="cube", scale=(sz * rng.uniform(1.2, 2.0), sz * rng.uniform(0.35, 0.7), sz * rng.uniform(0.9, 1.4)),
                            position=(x, sz * 0.18, z), rotation=(rng.uniform(-14, 14), rng.uniform(0, 360), rng.uniform(-14, 14)),
                            texture=ui.tex("rock.png"), texture_scale=(1.5, 1.5), color=C(tint), collider="box" if sz >= 0.9 else None)
        return self.ent(model="sphere", scale=(sz * rng.uniform(1.0, 1.5), sz * rng.uniform(0.6, 0.95), sz * rng.uniform(0.9, 1.3)),
                        position=(x, sz * 0.22, z), rotation=(rng.uniform(-10, 10), rng.uniform(0, 360), rng.uniform(-10, 10)),
                        texture=ui.tex("rock.png"), texture_scale=(2, 2), color=C(tint), collider="box" if sz >= 0.9 else None)

    def _craters(self, rng, m):
        has_decal = (config.ASSETS_DIR / "ui" / "crater.png").exists()
        for _ in range(30):
            r = rng.uniform(2.0, 8.5)
            x, z = rng.uniform(-62, 62), rng.uniform(-62, 62)
            if abs(x) < 15 and abs(z) < 20:
                continue
            if has_decal:
                self.decal("crater.png", x, z, r * 2.7, rng.uniform(0, 360), y=0.035)
            else:  # old flat discs
                self.ent(model="circle", shader=None, rotation_x=90, position=(x, 0.03, z), scale=r * 2,
                         color=C(shade(m.ground_color, 0.62), 0.9))
            if r > 4.2:                                    # raised rim: a ring of rocks and a mound of debris
                for k in range(int(r * 2.2)):
                    a = k / (r * 2.2) * 6.283 + rng.uniform(-0.1, 0.1)
                    rr = r * rng.uniform(1.0, 1.12)
                    self._rock(x + rr * math.cos(a), z + rr * math.sin(a), rng.uniform(0.25, 0.7), m.ground_color, rng,
                               slab=rng.random() < 0.4)
        # a scattered crater chain gives the horizon some history
        for _ in range(8):
            x, z = rng.uniform(-60, 60), rng.uniform(-60, 60)
            if abs(x) > 16 or abs(z) > 22:
                self.decal("crater.png", x, z, rng.uniform(1.2, 2.4), rng.uniform(0, 360), y=0.036)

    def _clear_keepout(self):
        """Remove scattered decoration (rocks, craters, decals) from the habitat's plot before it is built."""
        kx, kz, kr = KEEPOUT
        keep = []
        for e in self.entities:
            try:
                p = e.position
                near = math.hypot(p.x - kx, p.z - kz) < kr and p.y < 3 and not isinstance(e, (Sky, FirstPersonController))
                big = max(e.scale_x, e.scale_z) > 60 if hasattr(e, "scale_x") else False      # ground planes etc.
            except Exception:
                near, big = False, False
            if near and not big:
                destroy(e)
            else:
                keep.append(e)
        self.entities = keep

    def _world_flavour(self, rng, m):
        """Per-world environmental details."""
        gc = m.ground_color
        if m.id == "mars":                                  # long wind-carved dunes and red dust patches
            for _ in range(14):
                x, z = rng.uniform(-60, 60), rng.uniform(-60, 60)
                if abs(x) < 16 and abs(z) < 22:
                    continue
                self.ent(model="sphere", scale=(rng.uniform(9, 20), rng.uniform(0.5, 1.1), rng.uniform(3, 6)),
                         position=(x, 0.0, z), rotation_y=rng.uniform(0, 40), color=C(shade(gc, rng.uniform(0.9, 1.15))))
        elif m.id == "europa":                              # translucent ice shards and cracked plates
            for _ in range(28):
                x, z = rng.uniform(-55, 55), rng.uniform(-55, 55)
                if abs(x) < 15 and abs(z) < 20:
                    continue
                h = rng.uniform(0.8, 3.2)
                for k in range(rng.randint(2, 4)):
                    sh = self.ent(model="diamond", shader=None, scale=(rng.uniform(0.3, 0.6), h * rng.uniform(0.5, 1.0), rng.uniform(0.3, 0.6)),
                                  position=(x + rng.uniform(-0.6, 0.6), h * 0.3, z + rng.uniform(-0.6, 0.6)),
                                  rotation=(rng.uniform(-18, 18), rng.uniform(0, 360), rng.uniform(-18, 18)),
                                  color=Color(0.75, 0.9, 1.0, 0.85))
                    sh.setTransparency(TransparencyAttrib.MAlpha)
        elif m.id == "orbital":                             # drifted hull debris: panels and pipes
            for _ in range(22):
                x, z = rng.uniform(-55, 55), rng.uniform(-55, 55)
                if abs(x) < 16 and abs(z) < 22:
                    continue
                self.ent(model="cube", scale=(rng.uniform(1.2, 3), 0.12, rng.uniform(0.8, 2)), position=(x, 0.1 + rng.uniform(0, 0.4), z),
                         rotation=(rng.uniform(-12, 12), rng.uniform(0, 360), rng.uniform(-12, 12)),
                         color=C(shade((0.7, 0.72, 0.78), rng.uniform(0.6, 1.0))), collider="box")
                self.ent(model="cube", scale=(0.1, 0.1, rng.uniform(1.5, 4)), position=(x + 1, 0.12, z),
                         rotation_y=rng.uniform(0, 360), color=C((0.45, 0.48, 0.55)))
        else:                                               # moon: bright ejecta rays of small rocks
            for _ in range(5):
                a = rng.uniform(0, 6.283)
                for k in range(14):
                    d = rng.uniform(20, 55)
                    x, z = d * math.cos(a) + rng.uniform(-2, 2), d * math.sin(a) + rng.uniform(-2, 2)
                    s_ = rng.uniform(0.15, 0.4)
                    self.ent(model="sphere", scale=(s_ * 1.4, s_ * 0.6, s_), position=(x, s_ * 0.12, z), texture=ui.tex("rock.png"),
                             color=C(shade(gc, rng.uniform(1.1, 1.5))))

    def _footprints(self, rng, m):
        """Boot-print trails from the lander to every point of interest (they hint at where to go)."""
        if not (config.ASSETS_DIR / "ui" / "footprint.png").exists():
            return
        start = (0.0, -22.5)
        targets = [(o.pos[0], o.pos[1] - (o.size[2] * 0.9 + 1.5)) for o in m.objects]
        targets.append((HAB_POS[0] + 8.2, HAB_POS[1]))                  # the airlock
        for tx, tz in targets:
            dx, dz = tx - start[0], tz - start[1]
            dist = math.hypot(dx, dz)
            heading = math.degrees(math.atan2(dx, dz))
            n = int(dist / 1.15)
            for i in range(2, n):
                f = i / n
                wob = math.sin(f * 7 + rng.random()) * 0.6
                x = start[0] + dx * f + wob * dz / dist
                z = start[1] + dz * f - wob * dx / dist
                side = 0.22 if i % 2 else -0.22
                px, pz = x + side * dz / dist, z - side * dx / dist
                self.decal("footprint.png", px, pz, (0.2, 0.38), heading + rng.uniform(-6, 6), y=0.045, alpha=0.55)

    def _lander(self):
        ent = self.ent
        w = (0.86, 0.88, 0.92)
        ent(model="cube", scale=(4, 2.4, 4), position=(0, 3.0, -25), color=C(w), collider="box")
        ent(model="cube", scale=(4.4, 0.4, 4.4), position=(0, 1.7, -25), color=C(shade(w, 0.7)))
        for sx in (-1, 1):
            for sz in (-1, 1):
                ent(model="cube", scale=(0.25, 2.6, 0.25), position=(sx * 2.4, 1.0, -25 + sz * 2.4),
                    rotation=(sz * 14, 0, -sx * 14), color=C(shade(w, 0.55)))
                ent(model="cube", scale=(1, 0.18, 1), position=(sx * 2.8, 0.1, -25 + sz * 2.8), color=C(shade(w, 0.5)))
        ent(model="cube", scale=(1.2, 1.4, 0.1), position=(0, 2.7, -22.97), color=C((0.1, 0.15, 0.3)))
        ent(model="sphere", shader=None, unlit=True, scale=0.35, position=(0, 5.6, -25), color=C(ui.CYAN))
        ent(model="cube", scale=(0.1, 1.6, 0.1), position=(0, 4.9, -25), color=C(shade(w, 0.6)))

    def _prop(self, o):
        ent, rng = self.ent, self._rng
        x, z = o.pos
        w, h, d = o.size
        base = o.color
        ent(model="cube", shader=None, color=Color(0, 0, 0, 0), position=(x, h / 2, z), scale=(w, h, d),
            collider="box", obj_id=o.id)                              # invisible hit-box
        light = lambda col, y, sx=0.0, sz=0.0: ent(model="sphere", shader=None, unlit=True, scale=0.3,
                                                   position=(x + sx, y, z + sz), color=C(col))
        if o.id == "solar_array":
            for dx in (-w * 0.25, w * 0.25):
                ent(model="cube", scale=(0.18, h * 0.6, 0.18), position=(x + dx * 1.6, h * 0.3, z), color=C((0.5, 0.5, 0.55)))
            ent(model="cube", scale=(w, h * 0.7, 0.14), position=(x, h * 0.62, z), rotation_x=-14,
                texture="white_cube", texture_scale=(8, 3), color=C((0.12, 0.25, 0.7)))
            ent(model="cube", scale=(w + 0.2, h * 0.75, 0.1), position=(x, h * 0.62, z + 0.08), rotation_x=-14,
                color=C((0.7, 0.72, 0.78)))
        elif o.id in ("regolith", "clay_rock", "salt_ice"):
            for _ in range(6):
                s = rng.uniform(0.5, 1.0) * w * 0.55
                ent(model="sphere", scale=(s, s * rng.uniform(0.6, 0.9), s),
                    position=(x + rng.uniform(-w * 0.4, w * 0.4), s * 0.3, z + rng.uniform(-d * 0.4, d * 0.4)),
                    color=C(shade(base, rng.uniform(0.8, 1.15))))
            if o.id == "clay_rock":
                for k in range(3):
                    ent(model="cube", scale=(w * (0.9 - k * 0.2), 0.18, d * (0.9 - k * 0.2)),
                        position=(x, 0.4 + k * 0.5, z), color=C(shade(base, 1.2 - k * 0.15)))
            if o.id == "salt_ice":
                for k in range(4):
                    ent(model="cube", scale=(0.12, 0.9, 0.4), position=(x - 1 + k * 0.7, 0.9, z + 0.6),
                        rotation_z=rng.uniform(-15, 15), color=C((0.6, 0.35, 0.25)))
        elif o.id in ("riverbed", "ice_ridge"):
            n = 9 if o.id == "riverbed" else 6
            for k in range(n):
                t = (k / (n - 1) - 0.5) * w * 0.9
                s = rng.uniform(0.7, 1.2)
                if o.id == "riverbed":
                    ent(model="sphere", scale=(s * 1.2, s * 0.55, s), position=(x + t, 0.25, z + rng.uniform(-d * 0.3, d * 0.3)),
                        color=C(shade(base, rng.uniform(0.7, 1.2))))
                else:
                    ent(model="cube", scale=(0.9, h * rng.uniform(0.7, 1.3), 0.7), position=(x + t, h * 0.4, z),
                        rotation=(0, rng.uniform(-20, 20), rng.uniform(-18, 18)), color=C(shade(base, rng.uniform(0.85, 1.1))))
        elif o.id == "rover":
            ent(model="cube", scale=(w, 0.8, d * 0.85), position=(x, 1.0, z), color=C((0.85, 0.85, 0.88)))
            ent(model="cube", scale=(w * 0.8, 0.12, d * 0.8), position=(x, 1.5, z), color=C((0.25, 0.3, 0.45)))
            for sx in (-1, 0, 1):
                for sz in (-1, 1):
                    ent(model="cube", scale=(0.55, 0.55, 0.28), position=(x + sx * w * 0.38, 0.32, z + sz * d * 0.5),
                        color=C((0.12, 0.12, 0.14)))
            ent(model="cube", scale=(0.1, 1.1, 0.1), position=(x + w * 0.3, 1.9, z), color=C((0.6, 0.6, 0.65)))
            ent(model="cube", scale=(0.4, 0.25, 0.25), position=(x + w * 0.3, 2.5, z), color=C((0.2, 0.2, 0.25)))
            light(ui.RED, 1.65, w * 0.4, 0)
        elif o.id == "plant_rack":
            for k in range(3):
                ent(model="cube", scale=(w, 0.12, d), position=(x, 0.6 + k * 1.0, z), color=C((0.75, 0.78, 0.85)))
                for j in range(4):
                    ent(model="sphere", scale=0.5, position=(x - w * 0.35 + j * w * 0.23, 0.95 + k * 1.0, z),
                        color=C(shade(base, rng.uniform(0.8, 1.2))))
            for sx in (-1, 1):
                ent(model="cube", scale=(0.1, h, 0.1), position=(x + sx * w * 0.48, h / 2, z - d * 0.4), color=C((0.5, 0.5, 0.55)))
        elif o.id == "earth_window":
            ent(model="cube", scale=(w, h, d), position=(x, h / 2, z), color=C((0.3, 0.32, 0.38)))
            ent(model="cube", shader=None, unlit=True, scale=(0.06, h * 0.7, d * 0.8), position=(x - w / 2 - 0.02, h / 2, z),
                color=C((0.2, 0.5, 0.95)))
            ent(model="cube", shader=None, unlit=True, scale=(0.07, h * 0.15, d * 0.4), position=(x - w / 2 - 0.03, h * 0.6, z + 0.5),
                color=C((0.95, 0.97, 1.0)))
        else:                                                         # machines: relay, scrubber, drill
            ent(model="cube", scale=(w * 1.3, 0.3, d * 1.3), position=(x, 0.15, z), color=C((0.25, 0.27, 0.33)))
            ent(model="cube", scale=(w * 0.8, h * 0.8, d * 0.8), position=(x, h * 0.5, z), color=C(base))
            for k in range(4):
                ent(model="cube", scale=(w * 0.82, 0.07, d * 0.82), position=(x, h * 0.25 + k * 0.4, z), color=C(shade(base, 0.6)))
            ent(model="cube", scale=(0.08, 1.4, 0.08), position=(x, h + 0.7, z), color=C((0.7, 0.7, 0.75)))
            light(ui.RED, h + 1.5)
            if o.id == "drill":
                ent(model="diamond", scale=(0.5, 1.4, 0.5), position=(x, 0.9, z + d * 0.8), rotation_x=180, color=C((0.7, 0.7, 0.75)))

    # -- per-frame ambience
    def update(self, t, dt):
        if self.habitat is not None:
            self.habitat.update(t, dt)
        if self.planet is not None and not self.planet.is_empty():
            self.planet.rotation_y += 1.2 * dt
        for e in self.dust:
            if e.is_empty():
                continue
            e.y += math.sin(t * e._sp + e._ph) * 0.15 * dt
            e.x += math.cos(t * e._sp * 0.7 + e._ph) * 0.2 * dt

    def destroy(self):
        for e in self.entities + self.lights:
            try:
                destroy(e)
            except Exception:
                pass
        self.entities, self.lights, self.markers, self.dust, self.planet, self.player = [], [], {}, [], None, None
