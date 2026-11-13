"""Ursina presentation layer. All rules live in astro.missions / progression / session; this module only
draws screens, plays audio and routes input.  Fully bilingual (English / Arabic, with RTL mirroring)."""
import math
import random
import threading
import time as pytime

from ursina import *  # noqa: F401,F403
from ursina.models.procedural.quad import Quad
from panda3d.core import TransparencyAttrib

from .. import config, i18n, session
from ..audio import AudioManager, SuitSounds
from ..suit import Suit, TOOL_COST
from ..db import AGE_GROUPS
from ..missions import TOOLS, TOOL_ORDER, get_missions, deep_dive
from ..progression import ACHIEVEMENTS, TIER_SETTINGS, level_from_xp, tier_from_skill, xp_for_level
from ..quiz import SUGGESTED, quiz_for
from ..settings import Settings
from . import ui
from .ui import rgba
from .habitat import INTERACT_RANGE
from .outpost_ui import OutpostUI
from .viewmodel import ViewModel
from .world import World

SUITS = [("Nova", (0.95, 0.95, 1.0)), ("Orbit", (1.0, 0.65, 0.2)), ("Comet", (0.35, 0.85, 1.0)),
         ("Nebula", (0.75, 0.45, 1.0)), ("Rocket", (1.0, 0.35, 0.4)), ("Terra", (0.4, 0.9, 0.55))]
VISORS = [("Cyan", (0.2, 0.85, 1.0)), ("Gold", (1.0, 0.8, 0.2)), ("Rose", (1.0, 0.45, 0.7)), ("Lime", (0.6, 1.0, 0.3))]
TOOL_ICON = {"scanner": "icon_scan", "sampler": "icon_collect", "analyzer": "icon_analyze", "wrench": "icon_repair"}
TIER_COLOR = {"easy": ui.GREEN, "normal": ui.CYAN, "hard": ui.GOLD}
QUIZ_XP = 10


class Game(Entity):
    def __init__(self, db, assistant, settings=None, audio=None):
        super().__init__()
        ui.setup_fonts()
        self.db, self.assistant = db, assistant
        self.settings = settings or Settings.load()
        i18n.set_lang(self.settings.lang)
        if audio is None:
            try:
                audio = AudioManager(self.settings, application.base.loader)
            except Exception:
                audio = AudioManager(self.settings, None)
        self.audio = audio
        ui.set_sfx_hook(lambda name, **kw: self.audio.sfx(name, **kw))
        self.ui = []
        self.layers = []            # (entity, scroll speed) parallax layers
        self.twinkle = []
        self.pulses = []            # (entity, base alpha, speed, phase)
        self.topbar = []
        self.mode = "splash"
        self.profile = None
        self.state = None
        self.world = None
        self.panel = None
        self.panel_kind = None
        self.panel_ui = []
        self.hud = []
        self.slots = []
        self.tool_index = 0
        self.toast_t = 0.0
        self.t0 = 0.0
        self._rebuild = None
        self._answer = None
        self._asking = False
        self._shoot_t = pytime.time() + 3
        self._draft = {"name": "", "age": "mid", "suit": 0, "visor": 0}
        self._quiz = None
        self.fade = Entity(parent=camera.ui, model="quad", scale=(3, 2), color=rgba(ui.NAVY, 0), z=-8)
        self.outpost = OutpostUI(self)      # Outpost Command (its own screens; never part of MISSIONS)
        self.build_topbar()
        self.show_splash()

    # ------------------------------------------------------------------ small helpers
    @property
    def rtl(self):
        return i18n.is_rtl()

    @property
    def lang(self):
        return i18n.get_lang()

    @property
    def age(self):
        return self.profile["age_group"] if self.profile else "mid"

    def missions(self):
        return get_missions(self.lang, self.age)

    def mx(self, x):
        return -x if self.rtl else x

    def T(self, key, **kw):
        return i18n.t(key, **kw)

    def add(self, e):
        self.ui.append(e)
        return e

    def clear(self):
        for e in self.ui:
            if not e.is_empty():
                destroy(e)
        self.ui, self.layers, self.twinkle, self.pulses = [], [], [], []

    def _safe_destroy(self, e):
        if e is not None and not e.is_empty():
            destroy(e)

    def label(self, text, pos=(0, 0), scale=1.0, col=ui.WHITE, align="center", alpha=1.0, kind="body",
              mirror=True, wrap=None, valign="center", z=-0.03, parent=None, track=True):
        x, y = pos
        ox = {"start": -0.5, "center": 0, "end": 0.5}[align]
        if mirror and self.rtl:
            x, ox = -x, -ox
        oy = {"center": 0, "top": 0.5, "bottom": -0.5}[valign]
        if wrap:
            text = i18n.wrap(text, wrap)
        e = ui.label(parent or camera.ui, text, (x, y), scale, col, (ox, oy), z, alpha, kind)
        if track:
            self.add(e)
        return e

    def btn(self, text, pos, cb, size=(0.34, 0.075), style="primary", mirror=True, **kw):
        x = -pos[0] if (mirror and self.rtl) else pos[0]
        b = ui.button(camera.ui, text, (x, pos[1]), size, cb, style, **kw)
        self.add(b)
        self.add(b._glow_ent)
        return b

    def box(self, pos, size, mirror=True, **kw):
        x = -pos[0] if (mirror and self.rtl) else pos[0]
        return self.add(ui.panel(camera.ui, (x, pos[1]), size, **kw))

    def img(self, name, pos, scale, col=None, z=1, mirror=True, **kw):
        x = -pos[0] if (mirror and self.rtl) else pos[0]
        return self.add(ui.image(camera.ui, name, (x, pos[1]), scale, col, z, **kw))

    def fade_in(self, t=0.45):
        self.fade.color = rgba(ui.NAVY, 1)
        self.fade.animate_color(rgba(ui.NAVY, 0), duration=t, curve=curve.linear)

    # ------------------------------------------------------------------ persistent top bar (audio + language)
    def build_topbar(self):
        for e in self.topbar:
            if not e.is_empty():
                destroy(e)
        mx = self.mx
        self.btn_music = ui.icon_button(camera.ui, "icon_music_on", (mx(0.838), 0.452), 0.064, self.toggle_music)
        self.btn_sfx = ui.icon_button(camera.ui, "icon_sfx_on", (mx(0.763), 0.452), 0.064, self.toggle_sfx)
        other = "\u0627\u0644\u0639\u0631\u0628\u064a\u0629" if self.lang == "en" else "EN"
        self.btn_lang = ui.button(camera.ui, other, (mx(0.66), 0.452), (0.125, 0.058), self.toggle_language,
                                  "secondary", z=-0.05, text_scale=0.85, font="Cairo-Bold.ttf")
        self.topbar = [self.btn_music, self.btn_music._glow_ent, self.btn_sfx, self.btn_sfx._glow_ent,
                       self.btn_lang, self.btn_lang._glow_ent]
        self.refresh_topbar()

    def refresh_topbar(self):
        self.btn_music.set_icon("icon_music_on" if self.settings.music else "icon_music_off")
        self.btn_sfx.set_icon("icon_sfx_on" if self.settings.sfx else "icon_sfx_off")
        in_mission = self.mode == "mission"
        self.btn_lang.enabled = not in_mission
        self.btn_lang._glow_ent.enabled = not in_mission

    def toggle_music(self):
        on = self.audio.toggle_music()
        self.refresh_topbar()
        if self.mode == "mission":
            self.toast(self.T("music") + ": " + self.T("on" if on else "off"))

    def toggle_sfx(self):
        on = self.audio.toggle_sfx()
        self.refresh_topbar()
        if on:
            self.audio.sfx("click")

    def toggle_language(self):
        self.set_language("ar" if self.lang == "en" else "en")

    def set_language(self, code):
        self.settings.lang = code
        self.settings.save()
        i18n.set_lang(code)
        self.build_topbar()
        if self._rebuild:
            self._rebuild()

    # ------------------------------------------------------------------ backdrop shared by all 2D screens
    def screen(self, mode, music="menu", horizon=True, nebula=1.0):
        self.clear()
        self.mode = mode
        window.color = rgba(ui.NAVY)
        mouse.locked = False
        Z = camera.ui
        self.add(Entity(parent=Z, model="quad", scale=(2.8, 1.6), color=rgba(ui.NAVY), z=10))

        def layer(name, z, alpha, speed):
            e = ui.image(Z, name, (0, 0), (2.0, 1.125), rgba(ui.WHITE, alpha), z=z)
            self.add(e)
            self.layers.append((e, speed))

        layer("nebula_a.png", 9.6, 0.8 * nebula, 0.0030)
        layer("nebula_b.png", 9.5, 0.75 * nebula, -0.0045)
        layer("stars_0.png", 9.2, 0.9, 0.0040)
        layer("stars_1.png", 9.1, 1.0, 0.0080)
        layer("stars_2.png", 9.0, 1.0, 0.0140)
        if horizon:
            self.add(ui.image(Z, "horizon.png", (0, -0.5 + 0.145), (2.0, 0.58), rgba(ui.WHITE, 0.9), z=8))
        self.add(ui.image(Z, "vignette.png", (0, 0), (1.9, 1.07), z=6))
        for _ in range(26):
            s = random.uniform(0.012, 0.028)
            e = ui.image(Z, "sparkle.png", (random.uniform(-0.88, 0.88), random.uniform(-0.45, 0.5)), (s, s),
                         rgba(random.choice([ui.WHITE, ui.CYAN, ui.GOLD]), 0.5), z=7)
            self.add(e)
            self.twinkle.append((e, random.uniform(0, 6.28), random.uniform(1.0, 2.6)))
        if music:
            self.audio.play_music(music)
        self.refresh_topbar()
        self.fade_in()

    def pulse_glow(self, name, pos, scale, col, base=0.3, speed=1.6, mirror=True):
        e = self.img(name, pos, scale, rgba(col, base), z=6.5, mirror=mirror)
        self.pulses.append((e, base, speed, random.uniform(0, 6.28)))
        return e

    def _shoot(self):
        x, y = random.uniform(-0.8, 0.1), random.uniform(0.15, 0.5)
        e = ui.image(camera.ui, "glow.png", (x, y), (0.24, 0.012), rgba(ui.WHITE, 0.95), z=7)
        e.rotation_z = -22
        e.animate_position((x + 0.55, y - 0.24, 7), 0.9, curve=curve.linear)
        e.animate_color(rgba(ui.WHITE, 0), 0.9, curve=curve.linear)
        invoke(self._safe_destroy, e, delay=1.0)

    def ambient_update(self):
        t = pytime.time()
        for e, sp in self.layers:
            if not e.is_empty():
                e.texture_offset = ((t * sp) % 1.0, 0)
        for e, ph, sp in self.twinkle:
            if not e.is_empty():
                e.alpha = 0.25 + 0.6 * (0.5 + 0.5 * math.sin(t * sp + ph))
        for e, base, sp, ph in self.pulses:
            if not e.is_empty():
                e.alpha = base * (0.65 + 0.35 * math.sin(t * sp + ph))
        if t > self._shoot_t:
            self._shoot()
            self._shoot_t = t + random.uniform(5, 10)

    def logo(self, pos, height):
        tx = ui.logo_texture()
        if tx is not None:
            return self.add(Entity(parent=camera.ui, model="quad", texture=tx, scale=(height, height),
                                   position=(pos[0], pos[1], 0)))
        self.label("ASTRO PLAY", pos, 2.4, ui.CYAN, kind="display")
        return None

    # ------------------------------------------------------------------ splash & menu
    def show_splash(self):
        self._rebuild = None
        self.screen("splash", horizon=False)
        lg = self.logo((0, 0.06), 0.62)
        self.pulse_glow("glow.png", (0, 0.06), (1.3, 1.3), ui.CYAN, 0.35, 1.3, mirror=False)
        if lg is not None:
            lg.scale = (0.3, 0.3)
            lg.animate_scale((0.62, 0.62), 1.0, curve=curve.out_back)
        self.label(self.T("tagline"), (0, -0.30), 0.95, ui.CYAN, kind="display", mirror=False)
        bg, fill = ui.progress_bar(camera.ui, (0, -0.38), 0.4, 0.012, 1.0)
        self.add(bg)
        self.add(fill)
        fill.scale_x = 0.001
        fill.animate_scale_x(0.4 * 0.96, 2.4, curve=curve.linear)
        self.label(self.T("loading"), (0, -0.42), 0.6, ui.WHITE, alpha=0.5, mirror=False)
        invoke(self._leave_splash, delay=2.6)

    def _leave_splash(self):
        if self.mode == "splash":
            self.show_menu()

    def show_menu(self):
        self._rebuild = self.show_menu
        self.screen("menu")
        cx = -0.34
        self.pulse_glow("glow.png", (cx, 0.0), (1.55, 1.55), ui.CYAN, 0.3, 1.2)
        self.pulse_glow("glow.png", (cx + 0.08, -0.05), (1.1, 1.1), ui.PURPLE, 0.25, 0.9)
        lg = self.logo((self.mx(cx), 0.02), 0.96)
        if lg is not None:
            lg.animate_y(lg.y + 0.014, 2.6, curve=curve.in_out_sine, loop=True)
        self.label(self.T("tagline"), (0.47, 0.25), 1.0, ui.CYAN, kind="display")
        self.btn(self.T("new_game"), (0.47, 0.11), self.start_new_game, size=(0.4, 0.088), text_scale=1.15)
        has = bool(self.db.list_profiles())
        c = self.btn(self.T("continue"), (0.47, 0.0), self.show_continue, size=(0.4, 0.088), style="secondary", text_scale=1.15)
        if not has:
            c.disabled = True
            c.alpha = 0.45
            c._glow_ent.enabled = False
        self.btn(self.T("op_ui_menu"), (0.47, -0.11), self.outpost.enter, size=(0.4, 0.088), style="gold", text_scale=1.15)
        self.btn(self.T("quit"), (0.47, -0.22), application.quit, size=(0.4, 0.088), style="danger", text_scale=1.15)
        llm = self.assistant.llm_label
        self.label(f"{self.T('assistant_backend', backend=self.assistant.backend)}     {self.T('assistant_llm', llm=llm)}",
                   (-0.86, -0.475), 0.55, ui.WHITE, align="start", alpha=0.4)

    def show_continue(self):
        self._rebuild = self.show_continue
        self.screen("continue", horizon=False)
        self.label(self.T("continue"), (0, 0.4), 1.9, ui.CYAN, kind="display", mirror=False)
        profiles = self.db.list_profiles()[:6]
        for i, p in enumerate(profiles):
            y = 0.24 - i * 0.12
            lvl = level_from_xp(p["xp"])
            self.btn(f"{p['name']}   -   {self.T('level', n=lvl)}   -   {p['xp']} XP", (0, y),
                     lambda pid=p["id"]: self.load_profile(pid), size=(0.9, 0.092), style="secondary", mirror=False)
        self.btn(self.T("back"), (0, -0.42), self.show_menu, size=(0.3, 0.07), style="secondary", mirror=False)

    # ------------------------------------------------------------------ profile creation
    def start_new_game(self):
        self._draft = {"name": "", "age": "mid", "suit": 0, "visor": 0}
        self.show_profile_creation()

    def _sync_default_name(self):
        defaults = (i18n.t("default_name", "en"), i18n.t("default_name", "ar"), "")
        if self._draft["name"] in defaults:
            self._draft["name"] = ""

    def show_profile_creation(self):
        self._rebuild = self.show_profile_creation
        self._sync_default_name()
        self.screen("profile", horizon=True)
        self.box((0, 0.02), (1.25, 0.8), alpha=0.8, brackets=True)
        self.label(self.T("create_profile"), (0, 0.3), 1.7, ui.CYAN, kind="display", mirror=False)
        self.label(self.T("astro_name"), (-0.55, 0.19), 0.8, ui.WHITE, align="start", alpha=0.85)
        self.name_box = ui.TextBox(camera.ui, (0, 0.115), (1.1, 0.085), text=self._draft["name"],
                                   placeholder=self.T("type_name"), max_len=18, on_submit=self._profile_next)
        self.add(self.name_box)
        self.label(self.T("age_hint"), (-0.55, 0.01), 0.8, ui.WHITE, align="start", alpha=0.85, wrap=60)
        self.age_btns = {}
        for i, ag in enumerate(AGE_GROUPS):
            x = (i - 1) * 0.37
            b = self.btn(self.T("age_" + ag), (x, -0.09), lambda a=ag: self._pick_age(a), size=(0.34, 0.085),
                         style="primary" if ag == self._draft["age"] else "secondary", mirror=False, text_scale=0.95)
            self.age_btns[ag] = b
        self.btn(self.T("next"), (0, -0.26), self._profile_next, size=(0.42, 0.09), style="success", mirror=False,
                 text_scale=1.2)
        self.btn(self.T("back"), (0, -0.4), self.show_menu, size=(0.26, 0.062), style="secondary", mirror=False,
                 text_scale=0.9)

    def _pick_age(self, ag):
        self._draft["age"] = ag
        self._draft["name"] = self.name_box.value
        for k, b in self.age_btns.items():
            ui.restyle(b, "primary" if k == ag else "secondary")

    def _profile_next(self):
        name = self.name_box.value.strip() or self.T("default_name")
        self._draft["name"] = name
        self.show_customization()

    def show_customization(self):
        self._rebuild = self.show_customization
        self.screen("customize", horizon=True)
        d = self._draft
        self.label(self.T("suit_up", name=d["name"]), (0, 0.4), 1.7, ui.CYAN, kind="display", mirror=False, wrap=36)
        self.box((-0.4, -0.02), (0.55, 0.74), alpha=0.75, brackets=True)
        self.rig = None
        self._draw_rig()
        self.label(self.T("suit_color"), (0.07, 0.25), 0.9, ui.WHITE, align="start")
        self.suit_btns = []
        for i, (nm, col) in enumerate(SUITS):
            x = 0.18 + (i % 3) * 0.2
            y = 0.16 - (i // 3) * 0.13
            b = self.btn("", (x, y), lambda k=i: self._pick_suit(k), size=(0.15, 0.1), style="secondary", mirror=True)
            b.color = rgba(col)
            b.highlight_color = rgba(col).tint(0.2)
            self.suit_btns.append(b)
        self.label(self.T("visor_color"), (0.07, -0.15), 0.9, ui.WHITE, align="start")
        self.visor_btns = []
        for i, (nm, col) in enumerate(VISORS):
            b = self.btn("", (0.17 + i * 0.15, -0.24), lambda k=i: self._pick_visor(k), size=(0.12, 0.09), style="secondary")
            b.color = rgba(col)
            b.highlight_color = rgba(col).tint(0.2)
            self.visor_btns.append(b)
        self.btn(self.T("launch_map"), (0.34, -0.38), self._create_profile, size=(0.62, 0.09), style="success", text_scale=1.05)
        self.btn(self.T("back"), (-0.62, -0.43), self.show_profile_creation, size=(0.22, 0.06), style="secondary", text_scale=0.85)

    def _pick_suit(self, k):
        self._draft["suit"] = k
        self._draw_rig()

    def _pick_visor(self, k):
        self._draft["visor"] = k
        self._draw_rig()

    def _draw_rig(self):
        if getattr(self, "rig", None) is not None and not self.rig.is_empty():
            self.ui.remove(self.rig) if self.rig in self.ui else None
            destroy(self.rig)
        self.rig = self.add(Entity(parent=camera.ui, z=0, position=(self.mx(-0.4), 0.02)))
        suit = SUITS[self._draft["suit"]][1]
        visor = VISORS[self._draft["visor"]][1]
        P = self.rig
        P.scale = 0.78

        def q(**k):
            sc = k.get("scale", 1)
            if "model" not in k:
                w, h = (sc, sc) if not isinstance(sc, tuple) else sc
                k["model"] = Quad(radius=0.3, aspect=w / h)
            return Entity(parent=P, **k)
        q(model="circle", scale=0.62, color=rgba(visor, 0.12), z=2)
        q(scale=(0.2, 0.26), position=(0, -0.08), color=rgba(suit), z=-0.01)             # torso
        q(scale=(0.07, 0.2), position=(-0.15, -0.07), color=rgba(suit).tint(-0.12), z=-0.01)   # arms
        q(scale=(0.07, 0.2), position=(0.15, -0.07), color=rgba(suit).tint(-0.12), z=-0.01)
        q(scale=(0.075, 0.2), position=(-0.055, -0.27), color=rgba(suit).tint(-0.2), z=-0.01)  # legs
        q(scale=(0.075, 0.2), position=(0.055, -0.27), color=rgba(suit).tint(-0.2), z=-0.01)
        q(model="circle", scale=0.27, position=(0, 0.1), color=rgba(suit), z=-0.02)            # helmet
        q(scale=(0.19, 0.145), position=(0, 0.105), color=rgba(ui.NAVY), z=-0.03)               # visor frame
        q(scale=(0.17, 0.12), position=(0, 0.105), color=rgba(visor, 0.75), z=-0.035)            # visor glass
        q(model="circle", scale=0.03, position=(-0.04, 0.13), color=rgba(ui.WHITE, 0.85), z=-0.04)

    def _create_profile(self):
        d = self._draft
        pid = self.db.create_profile(d["name"], d["age"], SUITS[d["suit"]][0], VISORS[d["visor"]][0])
        self.load_profile(pid)

    # ------------------------------------------------------------------ galaxy map
    def load_profile(self, pid):
        self.profile = self.db.get_profile(pid)
        self.show_galaxy_map()

    def planet_art(self, parent_pos, size, col, locked=False, mirror=True):
        x = -parent_pos[0] if (mirror and self.rtl) else parent_pos[0]
        base = tuple(c * (0.35 if locked else 1.0) for c in col)
        P = self.add(Entity(parent=camera.ui, position=(x, parent_pos[1], 0)))
        Entity(parent=P, model="quad", texture=ui.tex("glow.png"), scale=size * 1.9, color=rgba(base, 0.45), z=0.02).setTransparency(TransparencyAttrib.MAlpha)
        Entity(parent=P, model="circle", scale=size, color=rgba(base), z=0)
        sh = Entity(parent=P, model="quad", texture=ui.tex("planet_shade.png"), scale=size * 1.02, color=color.white, z=-0.01)
        sh.setTransparency(TransparencyAttrib.MAlpha)
        Entity(parent=P, model="circle", scale=size * 0.28, position=(-size * 0.17, size * 0.12, -0.012), color=rgba(base).tint(-0.12))
        Entity(parent=P, model="circle", scale=size * 0.15, position=(size * 0.15, -size * 0.17, -0.012), color=rgba(base).tint(-0.1))
        Entity(parent=P, model="circle", scale=size * 1.04, color=rgba(ui.WHITE, 0.0), z=-0.02)
        return P

    def show_galaxy_map(self, notice=None):
        self._rebuild = self.show_galaxy_map
        p = self.profile = self.db.get_profile(self.profile["id"])
        self.screen("map", horizon=False, nebula=0.85)
        lvl = level_from_xp(p["xp"])
        lo, hi = xp_for_level(lvl), xp_for_level(lvl + 1)
        into, need = p["xp"] - lo, hi - lo
        tier = tier_from_skill(p["skill"])
        # ---- header
        self.box((-0.2, 0.43), (1.34, 0.115), alpha=0.9, brackets=True)
        self.logo((self.mx(-0.8), 0.43), 0.12)
        self.label(p["name"], (-0.72, 0.452), 1.25, ui.WHITE, align="start", kind="display", wrap=14)
        self.label(self.T("age_" + p["age_group"]), (-0.72, 0.405), 0.7, ui.CYAN, align="start")
        self.label(self.T("level", n=lvl), (-0.34, 0.462), 0.95, ui.GOLD, align="start", kind="display")
        frac = into / need if need else 1
        bg, fill = ui.progress_bar(camera.ui, (self.mx(-0.15), 0.425), 0.34, 0.016, frac, ui.GOLD)
        self.add(bg)
        self.add(fill)
        self.label(self.T("xp_line", xp=p["xp"], hi=xp_for_level(lvl + 1)), (-0.15, 0.395), 0.62, ui.WHITE, alpha=0.8)
        self.box((0.3, 0.43), (0.22, 0.062), fill=ui.PANEL, outline=TIER_COLOR[tier], oalpha=0.9, alpha=0.95)
        self.label(self.T(tier), (0.3, 0.43), 0.95, TIER_COLOR[tier], kind="display")
        # ---- title
        self.label(self.T("galaxy_map"), (0, -0.425), 1.3, ui.CYAN, kind="display", mirror=False)
        # ---- mission nodes
        entries = session.mission_list(self.db, p["id"], self.missions())
        pts = [(self.mx(e["mission"].map_pos[0]) * 1.1, e["mission"].map_pos[1] * 0.95) for e in entries]
        for a, b in zip(pts, pts[1:]):
            for k in range(1, 14):
                f = k / 14
                self.add(Entity(parent=camera.ui, model="circle", scale=0.0075, z=3,
                                position=(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f),
                                color=rgba(ui.CYAN, 0.35)))
        for e, pt in zip(entries, pts):
            m = e["mission"]
            locked = not e["unlocked"]
            self.planet_art((pt[0], pt[1] + 0.06), 0.2, m.planet_color, locked, mirror=False)
            self.box((pt[0], pt[1] - 0.12), (0.38, 0.1), mirror=False, alpha=0.9,
                     outline=ui.CYAN if not locked else (0.3, 0.35, 0.5), oalpha=0.7, radius=0.2)
            self.label(m.name, (pt[0], pt[1] - 0.12), 0.58, ui.WHITE if not locked else (0.5, 0.55, 0.7),
                       mirror=False, wrap=24)
            if locked:
                self.img("icon_lock.png", (pt[0], pt[1] + 0.06), (0.07, 0.07), rgba(ui.WHITE, 0.8),
                         z=-0.05, mirror=False)
                self.label(self.T("locked"), (pt[0], pt[1] - 0.215), 0.7, ui.GOLD, mirror=False)
            else:
                for s in range(3):
                    self.img("star_full.png" if s < e["stars"] else "star_empty.png", (pt[0] + (s - 1) * 0.06, pt[1] - 0.215),
                             (0.05, 0.05), z=-0.03, mirror=False)
                click = Button(parent=camera.ui, model="circle", scale=0.22, position=(pt[0], pt[1] + 0.06, -0.06),
                               color=rgba(ui.WHITE, 0.0), highlight_color=rgba(ui.CYAN, 0.18),
                               pressed_color=rgba(ui.CYAN, 0.3))
                click.on_click = lambda mid=m.id: (ui.sfx("click"), self.show_briefing(mid))
                self.add(click)
        ach = self.db.list_achievements(p["id"])
        self.btn(self.T("achievements_count", a=len(ach), b=len(ACHIEVEMENTS)), (-0.62, -0.43), lambda: None,
                 size=(0.4, 0.06), style="secondary", text_scale=0.8).disabled = True
        self.btn(self.T("main_menu"), (0.64, -0.43), self.show_menu, size=(0.3, 0.07), style="secondary", text_scale=0.9)
        if notice:
            self.label(notice, (0, -0.33), 0.75, ui.GOLD, wrap=80)

    # ------------------------------------------------------------------ briefing
    def show_briefing(self, mission_id):
        self._rebuild = lambda: self.show_briefing(mission_id)
        m = next(x for x in self.missions() if x.id == mission_id)
        self.briefing_mission = m
        tier = tier_from_skill(self.profile["skill"])
        self.screen("briefing", horizon=False, nebula=0.8)
        self.box((-0.22, -0.02), (1.24, 0.9), alpha=0.86, brackets=True)
        self.label(m.name, (-0.78, 0.36), 1.45, ui.CYAN, align="start", kind="display", wrap=30, valign="top")
        top = 0.36 - 0.07 * (m.name.count("\n") + 1 + (len(m.name) // 30))
        self.label(m.briefing, (-0.78, top - 0.03), 0.95, ui.WHITE, align="start", wrap=58, valign="top")
        lines = len(i18n.wrap(m.briefing, 58).split("\n"))
        y = top - 0.03 - 0.045 * lines - 0.04
        self.box((-0.22, y - 0.02), (1.1, 0.065), fill=(0.04, 0.1, 0.32), oalpha=0.4, alpha=0.9)
        self.label(self.T("science_focus", x=m.science_focus), (-0.72, y - 0.02), 0.78, ui.GOLD, align="start", wrap=80)
        y -= 0.1
        self.label(self.T("objectives"), (-0.78, y), 0.85, ui.CYAN, align="start", kind="display")
        for i, o in enumerate(m.objectives):
            self.label(f"{i + 1}.  {o.text}", (-0.76, y - 0.045 - i * 0.045), 0.8, ui.WHITE, align="start", wrap=70)
        y2 = y - 0.045 - len(m.objectives) * 0.045 - 0.03
        self.label(self.T("controls"), (-0.78, y2), 0.85, ui.CYAN, align="start", kind="display")
        keys = [("WASD", "key_move"), ("Mouse", "key_look"), ("1-4", "key_tools"), ("E", "key_use"), ("H", "key_hint"),
                ("Q", "key_ask"), ("Tab", "key_log"), ("Esc", "key_leave")]
        for i, (k, d) in enumerate(keys):
            col, row = i % 4, i // 4
            self.label(f"{k}  {self.T(d)}", (-0.78 + col * 0.27, y2 - 0.05 - row * 0.045), 0.7, ui.WHITE, align="start", alpha=0.85)
        self.planet_art((0.62, 0.13), 0.36, m.planet_color)
        self.label(self.T("difficulty", t=self.T(tier)), (0.62, -0.17), 0.95, TIER_COLOR[tier], kind="display")
        self.label(self.T("adapts"), (0.62, -0.215), 0.65, ui.WHITE, alpha=0.6, wrap=26)
        self.btn(self.T("launch"), (0.62, -0.3), lambda: self.start_mission(m), size=(0.34, 0.095), style="success",
                 text_scale=1.3, kind="display")
        self.btn(self.T("back"), (0.62, -0.4), self.show_galaxy_map, size=(0.22, 0.06), style="secondary", text_scale=0.85)

    # ================================================================== MISSION
    def start_mission(self, m):
        self._rebuild = None
        self.state = session.start_mission(self.db, self.profile["id"], m, self.lang, self.age)
        self.t0 = pytime.time()
        self.clear()
        self.mode = "mission"
        self.tool_index = 0
        self.panel = None
        self.audio.sfx("launch")
        self.audio.play_music("mission")
        window.color = rgba(m.sky_color)
        self.world = World(m)
        suit_rgb = next((c for n, c in SUITS if n == self.profile.get("suit_color")), SUITS[0][1])
        self.viewmodel = ViewModel(suit_rgb)
        self.viewmodel.equip(TOOL_ORDER[0], animate=False)
        self.suit = Suit(self.state.tier)
        self.sounds = SuitSounds(self.audio, m.id)
        self.inside = False
        self.moving = False
        self.refilling = False
        self._last_xz = None
        self._alarm_t = 0.0
        self._charge_t = 0.0
        self._resting_until = 0.0
        self.checkpoint = (self.world.habitat.pos[0] + 8.4, self.world.habitat.pos[1], -90)   # outside the airlock
        self.build_hud()
        self.refresh_topbar()
        self.fade_in(0.8)
        self.toast(self.T("start_tip"), 7)

    def hud_add(self, e):
        self.hud.append(e)
        return e

    def hud_label(self, *a, **k):
        k["track"] = False
        return self.hud_add(self.label(*a, **k))

    def build_hud(self):
        for e in self.hud:
            if not e.is_empty():
                destroy(e)
        self.hud, self.slots, self.obj_rows = [], [], []
        st, m = self.state, self.state.mission
        X = lambda x: -x if self.rtl else x
        # crosshair
        self.hud_add(ui.ring(camera.ui, (0, 0), 0.026, ui.CYAN, 0.9, 2, z=-0.1))
        self.hud_add(Entity(parent=camera.ui, model="circle", scale=0.005, color=rgba(ui.CYAN), z=-0.1))
        # objectives
        n = len(m.objectives)
        h = 0.095 + 0.052 * n
        top = 0.485
        self.hud_add(ui.panel(camera.ui, (X(-0.565), top - h / 2), (0.6, h), alpha=0.78, brackets=True, z=2))
        self.hud_label(m.name, (-0.84, top - 0.03), 0.62, ui.CYAN, align="start", kind="display", wrap=40, valign="center", z=-0.03)
        for i, o in enumerate(m.objectives):
            y = top - 0.088 - i * 0.052
            ring_e = self.hud_add(ui.ring(camera.ui, (X(-0.825), y), 0.02, ui.WHITE, 0.9, 2, z=-0.03))
            check = self.hud_add(Entity(parent=camera.ui, model="quad", texture=ui.tex("icon_check.png"), position=(X(-0.825), y, -0.04),
                                        scale=0.028, color=rgba(ui.GREEN), enabled=False))
            check.setTransparency(TransparencyAttrib.MAlpha)
            txt = self.hud_label(o.text, (-0.795, y), 0.7, ui.WHITE, align="start", wrap=50)
            self.obj_rows.append((o.id, ring_e, check, txt))
        # toast
        self.toast_panel = self.hud_add(ui.panel(camera.ui, (X(0.17), 0.405), (0.78, 0.1), alpha=0.85, brackets=True, z=2))
        self.toast_text = self.hud_label("", (0.17, 0.405), 0.78, ui.WHITE, wrap=62)
        self.toast_panel.enabled = False
        # info panel
        self.hud_add(ui.panel(camera.ui, (X(0.7), 0.335), (0.3, 0.1), alpha=0.75, z=2))
        self.info_text = self.hud_label("", (0.7, 0.335), 0.7, ui.WHITE, wrap=30)
        # target name
        self.target_panel = self.hud_add(ui.panel(camera.ui, (0, -0.11), (0.5, 0.065), alpha=0.7, radius=0.4, z=2))
        self.target_text = self.hud_label("", (0, -0.11), 0.95, ui.GOLD, mirror=False)
        self.target_panel.enabled = False
        # tool slots
        for i, t in enumerate(TOOL_ORDER):
            x = (i - 1.5) * 0.14
            sp = self.hud_add(ui.panel(camera.ui, (x, -0.395), (0.125, 0.125), alpha=0.85, brackets=False, z=2))
            self.hud_add(Entity(parent=camera.ui, model="quad", texture=ui.tex(TOOL_ICON[t] + ".png"), position=(x, -0.378, -0.03),
                                scale=0.058, color=rgba(ui.WHITE))).setTransparency(TransparencyAttrib.MAlpha)
            self.hud_label(str(i + 1), (x - 0.045, -0.35), 0.62, ui.GOLD, mirror=False, z=-0.04)
            self.hud_label(self.T("glyph_" + t), (x, -0.449), 0.5, ui.CYAN, mirror=False)
            self.slots.append(sp)
        self.charge_fills = []
        for i, t in enumerate(TOOL_ORDER):                         # real tool batteries (see astro/suit.py)
            x = (i - 1.5) * 0.14
            self.hud_add(Entity(parent=camera.ui, model="quad", scale=(0.1, 0.009), position=(x, -0.425, -0.03),
                                color=rgba((0.02, 0.06, 0.16), 1)))
            fill = self.hud_add(Entity(parent=camera.ui, model="quad", scale=(0.1, 0.009), position=(x, -0.425, -0.04),
                                       color=rgba(ui.GREEN)))
            self.charge_fills.append(fill)
        self.prompt_text = self.hud_label("", (0, -0.165), 0.8, ui.CYAN, mirror=False)
        self.slot_name = self.hud_label("", (0, -0.318), 0.7, ui.WHITE, mirror=False, alpha=0.85)
        self.hud_label(self.T("hud_keys"), (0.86, -0.475), 0.5, ui.WHITE, align="end", alpha=0.5)
        self.select_tool(0)
        self.refresh_hud()

    def refresh_hud(self):
        st = self.state
        for oid, ring_e, check, txt in self.obj_rows:
            done = oid in st.done
            avail = any(o.id == oid for o in st.available_objectives())
            ring_e.enabled = not done
            check.enabled = done
            ring_e.alpha = 1.0 if avail else 0.35
            txt.alpha = 0.45 if done else (1.0 if avail else 0.5)
            txt.color = rgba(ui.GREEN if done else ui.WHITE, txt.alpha)
        ui.set_text(self.info_text, self.T("hud_info", t=self.T(st.tier), m=st.mistakes, h=st.hints))
        # easy tier: glow markers above the next object
        nxt = st.next_objective()
        for oid, mk in self.world.markers.items():
            mk.enabled = bool(nxt and TIER_SETTINGS[st.tier].highlight_targets and nxt.target == oid)

    def select_tool(self, i):
        self.tool_index = i % len(TOOL_ORDER)
        for k, sp in enumerate(self.slots):
            sel = k == self.tool_index
            sp.color = rgba((0.12, 0.3, 0.7) if sel else ui.PANEL, 0.95 if sel else 0.85)
            sp.scale = (0.138, 0.138) if sel else (0.125, 0.125)
        ui.set_text(self.slot_name, self.T("tool_" + TOOL_ORDER[self.tool_index]))
        vm = getattr(self, "viewmodel", None)
        if vm is not None and not vm.is_empty() and vm.current != TOOL_ORDER[self.tool_index]:
            vm.equip(TOOL_ORDER[self.tool_index])
            self.audio.sfx("equip", volume=0.8)
        else:
            self.audio.sfx("hover", volume=0.6)

    def toast(self, text, secs=4.0):
        if self.mode != "mission" or not getattr(self, "toast_text", None) or self.toast_text.is_empty():
            return
        self.toast_panel.enabled = True
        ui.set_text(self.toast_text, i18n.wrap(text, 62))
        self.toast_t = pytime.time() + secs

    # ---- effects
    def fx_pulse(self, col, big=0.9):
        e = ui.image(camera.ui, "pulse_ring.png", (0, 0), (0.05, 0.05), rgba(col, 0.95), z=-0.2)
        e.animate_scale((big, big), 0.55, curve=curve.out_expo)
        e.animate_color(rgba(col, 0), 0.55, curve=curve.linear)
        invoke(self._safe_destroy, e, delay=0.6)

    def fx_float(self, text, col=ui.GOLD):
        e = ui.label(camera.ui, text, (0, 0.06), 1.5, col, (0, 0), -0.3, 1.0, "display")
        e.animate_y(0.2, 1.1, curve=curve.out_expo)
        e.animate_color(rgba(col, 0), 1.1, curve=curve.in_expo)
        invoke(self._safe_destroy, e, delay=1.2)

    # ---- targeting and tools
    def current_target(self):
        if not self.world or self.panel:
            return None
        hit = raycast(camera.world_position, camera.forward, distance=11, ignore=[self.world.player])
        if hit.hit and getattr(hit.entity, "obj_id", None):
            return hit.entity.obj_id
        return None

    HAB_ACTIONS = {"hab_analyzer": "act_lab", "hab_bed": "act_rest", "hab_locker": "act_locker", "hab_o2": "act_o2"}

    def update_target(self):
        tid = self.current_target()
        prompt = ""
        if tid and tid.startswith("hab_"):
            hab, p = self.world.habitat, self.world.player
            if hab.distance_to(tid, p.x, p.z) > INTERACT_RANGE:
                tid = None
            else:
                act = ("act_close" if hab.door_open else "act_open") if tid == "hab_door" else self.HAB_ACTIONS[tid]
                prompt = self.T("prompt_e", action=self.T(act))
                name = self.T(tid)
        elif tid:
            name = self.state.mission.get_object(tid).name
        if tid:
            ui.set_text(self.target_text, name, "display")
            self.target_panel.enabled = True
        else:
            self.target_text.text = ""
            self.target_panel.enabled = False
        ui.set_text(self.prompt_text, prompt)
        self._target = tid

    def use_equipment(self):
        tid = getattr(self, "_target", None)
        if tid and tid.startswith("hab_"):                     # habitat stations work with any tool
            self.interact_habitat(tid)
            return
        tool = TOOL_ORDER[self.tool_index]
        vm = self.viewmodel
        if not self.suit.can_use(tool):                        # empty battery: nothing happens until recharged
            self.toast(self.T("tool_low", tool=self.T("tool_" + tool)), 5)
            self.audio.sfx("error")
            vm.play_use(tool, ok=False)
            return
        res = self.state.use_tool(tool, tid)
        if res.needs_choice:
            if not self.suit.can_use("wrench"):                  # the repair itself needs wrench battery
                self.toast(self.T("tool_low", tool=self.T("tool_wrench")), 5)
                self.audio.sfx("error")
                vm.play_use(tool, ok=False)
                return
            self.audio.sfx("wrench")
            vm.play_use("wrench", ok=True)
            self.audio.sfx("open")
            self.open_repair(res.target)
            return
        self.toast(res.message, 6 if res.ok else 4)
        vm.play_use(tool, ok=res.ok)
        if res.ok:
            self.suit.consume(tool)
            self.audio.sfx({"scanner": "scan", "sampler": "collect", "analyzer": "analyze"}.get(tool, "success"))
            self.fx_pulse(ui.CYAN if tool == "scanner" else ui.GREEN)
            if res.xp:
                self.fx_float(f"+{res.xp} XP")
            if res.completed_objective:
                invoke(self.audio.sfx, "success", delay=0.35)
        else:
            self.audio.sfx("error")
            self.fx_pulse(ui.RED, 0.5)
        self.refresh_hud()
        self.refresh_charges()
        if self.state.complete:
            invoke(self.finish_mission, delay=1.6)

    # ---- habitat stations (their rules live in astro/suit.py and MissionState.lab_analyze)
    def interact_habitat(self, tid):
        hab, st, suit = self.world.habitat, self.state, self.suit
        p = self.world.player
        if tid == "hab_door":
            if hab.door_open:
                lx, lz = hab.local(p.x, p.z)
                if abs(lx - 4.5) < 1.4 and abs(lz) < 1.3:
                    self.toast(self.T("door_blocked"), 3)
                    self.audio.sfx("error")
                    return
                hab.set_door(False)
                self.audio.sfx("door_close")
                self.toast(self.T("door_closed"), 2.5)
            else:
                hab.set_door(True)
                self.audio.sfx("door_open")
                self.toast(self.T("door_opened"), 2.5)
        elif tid == "hab_analyzer":
            res = st.lab_analyze()
            self.toast(res.message, 9 if res.ok else 5)
            if res.ok:
                hab.play_lab()
                self.audio.sfx("lab")
                self.fx_pulse(ui.GREEN)
                if res.xp:
                    self.fx_float(f"+{res.xp} XP")
                if res.completed_objective:
                    invoke(self.audio.sfx, "success", delay=1.3)
                self.refresh_hud()
                if st.complete:
                    invoke(self.finish_mission, delay=2.6)
            else:
                self.audio.sfx("error")
        elif tid == "hab_bed":
            self.rest_in_bed()
        elif tid == "hab_locker":
            needed = suit.recharge_all()
            hab.play_locker()
            hab.set_locker_leds(suit.charges)
            self.refresh_charges()
            self.audio.sfx("locker")
            self.toast(self.T("locker_charged" if needed else "locker_full"), 3.5)
            if needed:
                self.fx_pulse(ui.CYAN, 0.8)
        elif tid == "hab_o2":
            if self.refilling:
                self._stop_refill(silent=True)
            elif suit.oxygen >= 99.9:
                self.toast(self.T("o2_already_full"), 3)
                self.audio.sfx("click")
            else:
                self.refilling = True
                self.audio.loop_sfx("o2fill", True, 0.8)
                self.toast(self.T("o2_filling"), 3)

    def _stop_refill(self, silent=False):
        if self.refilling:
            self.refilling = False
            self.audio.loop_sfx("o2fill", False)
            if not silent:
                self.toast(self.T("o2_full"), 3)

    def rest_in_bed(self):
        """Rest in the bunk: fade out/in, save a checkpoint inside the habitat and recap what is left to do."""
        p, st = self.world.player, self.state
        self.audio.sfx("bed")
        self.checkpoint = (p.x, p.z, p.rotation_y)
        self._resting_until = pytime.time() + 1.9
        p.enabled = False
        self.fade.color = rgba(ui.NAVY, 0)
        self.fade.animate_color(rgba(ui.NAVY, 1), 0.5, curve=curve.linear)
        invoke(self._wake_up, delay=1.5)
        todo = [o.text for o in st.available_objectives()][:2]
        msg = self.T("bed_rest") + "\n" + (self.T("bed_todo", todo="; ".join(todo)) if todo else self.T("bed_all_done"))
        invoke(self.toast, msg, 9, delay=1.5)

    def _wake_up(self):
        if self.mode != "mission" or not self.world:
            return
        self.fade_in(0.6)
        if not self.panel:
            self.world.player.enabled = True
            mouse.locked = True

    def o2_emergency(self):
        """Oxygen hit zero: the suit's emergency system returns the astronaut to the last checkpoint."""
        self.state.mistakes += 1
        self.suit.emergency_reset()
        self._stop_refill(silent=True)
        self.audio.sfx("alarm_crit")
        self.fade.color = rgba(ui.NAVY, 0)
        self.fade.animate_color(rgba(ui.NAVY, 1), 0.45, curve=curve.linear)
        invoke(self._emergency_move, delay=0.55)
        self.toast(self.T("o2_empty"), 7)
        self.refresh_hud()

    def _emergency_move(self):
        if self.mode != "mission" or not self.world:
            return
        x, z, ry = self.checkpoint
        p = self.world.player
        p.position = Vec3(x, 0.05, z)         # feet on the floor: Ursina's controller can sink through it if it starts higher on a slow frame
        p.rotation_y = ry
        self.fade_in(0.8)

    def refresh_charges(self):
        for fill, t in zip(self.charge_fills, TOOL_ORDER):
            v = self.suit.charges[t]
            fill.scale_x = max(0.0005, 0.1 * v / 100.0)
            fill.x = (TOOL_ORDER.index(t) - 1.5) * 0.14 - (0.1 - fill.scale_x) / 2
            fill.color = rgba(ui.GREEN if v > 60 else (ui.GOLD if v > 25 else ui.RED))

    def use_hint(self):
        self.audio.sfx("hint")
        self.toast(self.T("hint_prefix") + self.state.hint(), 7)
        self.refresh_hud()

    # ---- panels (freeze the player while open)
    def open_panel(self, kind, size=(1.3, 0.9)):
        self.close_panel(silent=True)
        self.panel, self.panel_kind, self.panel_ui = True, kind, []
        self._hud_state = [(e, e.enabled) for e in self.hud if not e.is_empty()]
        for e, _ in self._hud_state:                      # keep the HUD from showing through the panel
            e.enabled = False
        if self.world and self.world.player:
            self.world.player.enabled = False
        mouse.locked = False
        dim = Entity(parent=camera.ui, model="quad", scale=(3, 2), color=rgba((0, 0.01, 0.06), 0.7), z=0.5)
        self.panel_ui.append(dim)
        pn = ui.panel(camera.ui, (0, 0), size, alpha=0.96, brackets=True, z=0.4)
        self.panel_ui.append(pn)
        self.target_panel.enabled = False
        self.target_text.text = ""

    def p_label(self, *a, **k):
        k["track"] = False
        e = self.label(*a, **k)
        self.panel_ui.append(e)
        return e

    def p_btn(self, *a, **k):
        b = self.btn(*a, **k)
        self.ui.remove(b)
        self.ui.remove(b._glow_ent)
        self.panel_ui += [b, b._glow_ent]
        return b

    def close_panel(self, silent=False):
        for e in self.panel_ui:
            if not e.is_empty():
                destroy(e)
        was = self.panel
        self.panel, self.panel_kind, self.panel_ui = None, None, []
        self._answer = None
        for e, en in getattr(self, "_hud_state", []):
            if not e.is_empty():
                e.enabled = en
        self._hud_state = []
        if was and self.world and self.world.player and self.mode == "mission":
            self.world.player.enabled = True
            mouse.locked = True
        if was and not silent:
            self.audio.sfx("click", volume=0.6)

    def open_repair(self, obj_id):
        obj = self.state.mission.get_object(obj_id)
        self.open_panel("repair", (1.3, 0.92))
        self.p_label(self.T("repair_title", name=obj.name), (0, 0.38), 1.4, ui.CYAN, kind="display", mirror=False, wrap=44)
        self.p_label(self.T("diagnosis", d=obj.fault), (-0.58, 0.29), 0.9, ui.WHITE, align="start", wrap=66, valign="top")
        n = len(i18n.wrap(obj.fault, 60).split("\n")) + 1
        q = "fix_question_young" if self.age == "young" else "fix_question"
        qy = 0.29 - 0.05 * n - 0.03
        self.p_label(self.T(q), (-0.58, qy), 0.95, ui.GOLD, align="start", wrap=66)
        opts = self.state.repair_options(obj_id)
        for k, (idx, opt) in enumerate(opts):
            self.p_btn(f"{k + 1}.  {opt.text}", (0, qy - 0.1 - k * 0.105),
                       lambda i=idx, o=obj_id: self.choose_fix(o, i), size=(1.12, 0.088),
                       style="secondary", mirror=False, text_scale=0.9)
        self.p_label(self.T("esc_cancel"), (0, -0.42), 0.6, ui.WHITE, alpha=0.5, mirror=False)

    def choose_fix(self, obj_id, idx):
        res = self.state.repair(obj_id, idx)
        self.suit.consume("wrench")                              # every repair attempt uses wrench battery
        self.refresh_charges()
        self.audio.sfx("wrench")
        self.close_panel(silent=True)
        self.toast(res.message, 9)
        if res.ok:
            self.audio.sfx("repair")
            self.fx_pulse(ui.GREEN, 1.3)
            self.fx_float(f"+{res.xp} XP", ui.GREEN)
        else:
            self.audio.sfx("error")
            self.fx_pulse(ui.RED, 0.6)
        self.refresh_hud()
        if self.state.complete:
            invoke(self.finish_mission, delay=2.2)

    def open_log(self):
        self.open_panel("log", (1.3, 0.9))
        self.audio.sfx("open")
        self.p_label(self.T("log_title"), (0, 0.38), 1.5, ui.CYAN, kind="display", mirror=False)
        ev = self.state.evidence
        if not ev:
            self.p_label(self.T("log_empty"), (0, 0.0), 0.9, ui.WHITE, alpha=0.7, mirror=False)
        y = 0.3
        for line in ev[-6:]:
            txt = i18n.wrap(line, 96)
            self.p_label(txt, (-0.58, y), 0.7, ui.WHITE, align="start", valign="top")
            y -= 0.045 * (txt.count("\n") + 1) + 0.035
        self.p_label(self.T("esc_close"), (0, -0.42), 0.6, ui.WHITE, alpha=0.5, mirror=False)

    def open_ask(self):
        self.open_panel("ask", (1.32, 0.96))
        self.audio.sfx("open")
        self.p_label(self.T("ask_title"), (0, 0.42), 1.5, ui.CYAN, kind="display", mirror=False)
        self.p_label(self.T("ask_hint"), (0, 0.355), 0.72, ui.WHITE, alpha=0.8, mirror=False, wrap=90)
        self.ask_box = ui.TextBox(camera.ui, (0, 0.285), (1.12, 0.08), placeholder=self.T("ask_placeholder"),
                                  max_len=140, on_submit=self._submit_ask)
        self.panel_ui.append(self.ask_box)
        self.p_btn(self.T("ask_btn"),
                   (0.0, 0.205), self._submit_ask, size=(0.24, 0.058), style="primary", mirror=False, text_scale=0.9)
        self.p_label(self.T("try_asking"), (-0.58, 0.14), 0.7, ui.GOLD, align="start")
        qs = SUGGESTED[self.state.mission.id][self.age][self.lang]
        for i, q in enumerate(qs):
            self.p_btn(q, (0, 0.085 - i * 0.07), lambda s=q: self._ask_text(s), size=(1.12, 0.06),
                       style="secondary", mirror=False, text_scale=0.78)
        self.ans = self.p_label("", (-0.58, -0.17), 0.82, ui.WHITE, align="start", valign="top")
        self.p_label(self.T("esc_close"), (0, -0.45), 0.6, ui.WHITE, alpha=0.5, mirror=False)

    def _submit_ask(self):
        self._ask_text(self.ask_box.value.strip())

    def _ask_text(self, q):
        if self._asking or not q:
            return
        self.ask_box.set_value(q)
        self._asking = True
        self._answer = self.T("thinking")
        mid, age, lang = self.state.mission.id, self.age, self.lang
        ev = list(self.state.evidence)

        def work():
            try:
                for partial in self.assistant.ask_stream(q, mid, age, ev, lang):
                    self._answer = partial
            except Exception:
                self._answer = self.T("comms_down")
            finally:
                self._asking = False
        threading.Thread(target=work, daemon=True).start()

    def _poll_answer(self):
        if self.panel_kind == "ask" and self._answer is not None and getattr(self, "ans", None) and not self.ans.is_empty():
            ui.set_text(self.ans, i18n.wrap(self._answer, 74))

    # ================================================================== COMPLETION
    def finish_mission(self):
        if self.mode != "mission":
            return
        seconds = pytime.time() - self.t0
        st = self.state
        summary = session.finish_mission(self.db, self.profile["id"], st, seconds)
        self.profile = self.db.get_profile(self.profile["id"])
        mission = st.mission
        evidence = list(st.evidence)
        stats = (st.mistakes, st.hints, int(seconds))
        self.end_world()
        self.audio.sfx("fanfare")
        self.show_complete(mission, summary, evidence, stats)

    def end_world(self):
        vm = getattr(self, "viewmodel", None)
        if vm is not None and not vm.is_empty():
            destroy(vm)
        self.viewmodel = None
        self.audio.loop_sfx("o2fill", False)
        self.refilling = False
        if self.world:
            self.world.destroy()
            self.world = None
        for e in self.hud:
            if not e.is_empty():
                destroy(e)
        self.hud = []
        self.close_panel(silent=True)
        mouse.locked = False

    def show_complete(self, mission, summary, evidence, stats):
        self._rebuild = None
        self.screen("complete", horizon=False, nebula=0.8)
        self.box((0, -0.02), (1.7, 0.92), alpha=0.86, brackets=True)
        self.label(self.T("complete"), (0, 0.38), 2.1, ui.GREEN, kind="display", mirror=False)
        self.label(mission.name, (0, 0.31), 1.0, ui.CYAN, mirror=False)
        for i in range(3):
            s = self.img("star_full.png" if i < summary["stars"] else "star_empty.png", ((i - 1) * 0.15, 0.2), (0.13, 0.13), z=-0.03, mirror=False)
            if i < summary["stars"]:
                s.scale = (0.01, 0.01)
                s.animate_scale((0.13, 0.13), 0.5, delay=0.35 + i * 0.3, curve=curve.out_back)
                invoke(self.audio.sfx, "star", 0.9, 1.0 + 0.18 * i, delay=0.35 + i * 0.3)
        self.label(self.T("xp_total", xp=summary["xp"], total=summary["total_xp"], lvl=summary["level"]), (0, 0.1), 1.05, ui.GOLD, mirror=False)
        if summary["leveled_up"]:
            self.label(self.T("level_up"), (0, 0.055), 1.2, ui.CYAN, kind="display", mirror=False)
            self.audio.sfx("levelup")
        self.label(self.T("stats", m=stats[0], h=stats[1], s=stats[2], t=self.T(summary["next_tier"])), (0, 0.012), 0.72, ui.WHITE, alpha=0.8, mirror=False, wrap=100)
        y = -0.035
        if summary["unlocked"]:
            names = ", ".join(m.name for m in self.missions() if m.id in summary["unlocked"])
            self.label(self.T("unlocked", names=names), (0, y), 0.8, ui.GREEN, mirror=False, wrap=100)
            y -= 0.04
        for a in summary["achievements"][:2]:
            self.label(self.T("achievement", text=self.T("ach_" + a)), (0, y), 0.72, ui.GOLD, mirror=False, wrap=110)
            y -= 0.04
        y -= 0.01
        self.label(self.T("learned"), (-0.74, y), 0.75, ui.CYAN, align="start", kind="display")
        y -= 0.035
        keep = 2 if self.age == "teen" else 3
        for line in evidence[-keep:]:
            txt = i18n.wrap(line, 150)
            self.label(txt, (-0.74, y), 0.56, ui.WHITE, align="start", valign="top", alpha=0.9)
            y -= 0.03 * (txt.count("\n") + 1) + 0.012
        if self.age == "teen":
            txt = i18n.wrap(deep_dive(mission.id, self.lang), 150)
            self.label(txt, (-0.74, y), 0.56, ui.GOLD, align="start", valign="top", alpha=0.95)
        self.btn(self.T("take_quiz"), (-0.22, -0.41), lambda: self.start_quiz(mission), size=(0.5, 0.085), style="gold", text_scale=1.0, mirror=True)
        self.btn(self.T("back_to_map"), (0.4, -0.41), self.show_galaxy_map, size=(0.46, 0.085), style="primary", text_scale=0.95)

    # ================================================================== QUIZ (adapts to age + language)
    def start_quiz(self, mission):
        qs = quiz_for(mission.id, self.age, self.lang, seed=self.profile["id"] * 31 + len(mission.id))
        self._quiz = {"mission": mission, "qs": qs, "i": 0, "correct": 0, "answered": False}
        self.show_quiz_question()

    def show_quiz_question(self):
        quiz = self._quiz
        self._rebuild = self.show_quiz_question
        self.screen("quiz", horizon=False, nebula=0.8)
        q, opts, correct, expl = quiz["qs"][quiz["i"]]
        self.box((0, -0.02), (1.5, 0.9), alpha=0.86, brackets=True)
        self.label(self.T("quiz_title"), (0, 0.38), 1.6, ui.GOLD, kind="display", mirror=False)
        self.label(self.T("quiz_q", i=quiz["i"] + 1, n=len(quiz["qs"])), (0, 0.325), 0.75, ui.CYAN, mirror=False)
        self.label(q, (0, 0.235), 1.2, ui.WHITE, mirror=False, wrap=52)
        self.quiz_btns = []
        for k, o in enumerate(opts):
            b = self.btn(f"{k + 1}.  {o}", (0, 0.1 - k * 0.11), lambda i=k: self.answer_quiz(i), size=(1.2, 0.092),
                         style="secondary", mirror=False, text_scale=1.0)
            self.quiz_btns.append(b)
        self.quiz_msg = self.label("", (0, -0.27), 0.95, ui.WHITE, mirror=False)
        self.quiz_next = None
        self.fx_quiz_xp = None

    def answer_quiz(self, i):
        quiz = self._quiz
        if quiz["answered"]:
            return
        quiz["answered"] = True
        q, opts, correct, expl = quiz["qs"][quiz["i"]]
        ok = i == correct
        for k, b in enumerate(self.quiz_btns):
            b.disabled = True
            if k == correct:
                ui.restyle(b, "success")
            elif k == i:
                ui.restyle(b, "danger")
        if ok:
            quiz["correct"] += 1
            self.db.add_xp(self.profile["id"], QUIZ_XP)
            self.audio.sfx("success")
            head = self.T("quiz_correct", xp=QUIZ_XP)
            col = ui.GREEN
        else:
            self.audio.sfx("error")
            head = self.T("quiz_wrong")
            col = ui.RED
        self.quiz_msg.text = ""
        ui.set_text(self.quiz_msg, head + "\n" + i18n.wrap(expl, 80))
        self.quiz_msg.color = rgba(col)
        last = quiz["i"] + 1 >= len(quiz["qs"])
        self.quiz_next = self.btn(self.T("quiz_finish" if last else "quiz_next"), (0, -0.4), self.next_quiz, size=(0.4, 0.08),
                                  style="primary", mirror=False)

    def next_quiz(self):
        quiz = self._quiz
        quiz["i"] += 1
        quiz["answered"] = False
        if quiz["i"] >= len(quiz["qs"]):
            self.show_quiz_result()
        else:
            self.show_quiz_question()

    def show_quiz_result(self):
        quiz = self._quiz
        self._rebuild = self.show_quiz_result
        self.profile = self.db.get_profile(self.profile["id"])
        self.screen("quiz_result", horizon=False, nebula=0.8)
        n, c = len(quiz["qs"]), quiz["correct"]
        self.box((0, 0), (1.2, 0.7), alpha=0.86, brackets=True)
        self.label(self.T("quiz_title"), (0, 0.25), 1.6, ui.GOLD, kind="display", mirror=False)
        self.label(self.T("quiz_result", c=c, n=n, xp=c * QUIZ_XP), (0, 0.12), 1.2, ui.WHITE, mirror=False, wrap=44)
        self.label(self.T("quiz_great" if c == n else "quiz_ok"), (0, 0.0), 1.0, ui.GREEN if c == n else ui.CYAN, mirror=False, wrap=50)
        for k in range(n):
            self.img("star_full.png" if k < c else "star_empty.png", ((k - (n - 1) / 2) * 0.14, -0.1), (0.12, 0.12), z=-0.03, mirror=False)
        if c == n:
            self.audio.sfx("fanfare")
        self.btn(self.T("back_to_map"), (0, -0.25), self.show_galaxy_map, size=(0.5, 0.09), style="primary", mirror=False)

    # ================================================================== input / update
    def abort_mission(self):
        self.end_world()
        self.state = None
        self.audio.play_music("menu")
        self.show_galaxy_map(self.T("aborted"))

    def input(self, key):
        typing = ui.TextBox.typing()
        if key == "m" and not typing:
            self.toggle_music()
            return
        if self.mode == "splash":
            if key in ("space", "enter", "left mouse down"):
                self._leave_splash()
            return
        if self.mode == "outpost":
            self.outpost.input(key)
            return
        if self.mode != "mission":
            return
        if key == "escape":
            if self.panel:
                self.close_panel()
            else:
                self.abort_mission()
            return
        if self.panel or typing:
            return
        if key in ("1", "2", "3", "4"):
            self.select_tool(int(key) - 1)
        elif key == "scroll up":
            self.select_tool(self.tool_index - 1)
        elif key == "scroll down":
            self.select_tool(self.tool_index + 1)
        elif key in ("e", "left mouse down"):
            self.use_equipment()
        elif key == "h":
            self.use_hint()
        elif key == "q":
            self.open_ask()
        elif key == "tab":
            self.open_log()

    def update(self):
        self.audio.update(time.dt)
        if self.mode != "mission":
            self.ambient_update()
            if self.mode == "outpost":
                self.outpost.update()
            return
        dt, now = time.dt, pytime.time()
        if self.world:
            self.world.update(now, dt)
        if self.toast_t and now > self.toast_t:
            self.toast_panel.enabled = False
            self.toast_text.text = ""
            self.toast_t = 0
        self.update_target()
        self._poll_answer()
        self.update_astronaut(dt, now)

    def update_astronaut(self, dt, now):
        """Movement-driven systems: oxygen, warnings, footsteps, breathing, hands and the wristwatch."""
        if not self.world or not self.world.player or not getattr(self, "suit", None):
            return
        p, hab, suit = self.world.player, self.world.habitat, self.suit
        active = not self.panel and p.enabled
        # real movement (works for keyboard and for scripted/teleport moves alike)
        if self._last_xz is None or dt <= 0:
            speed = 0.0
        else:
            speed = math.hypot(p.x - self._last_xz[0], p.z - self._last_xz[1]) / dt
        self._last_xz = (p.x, p.z)
        self.moving = active and 0.8 < speed < 14 and p.grounded
        self.inside = hab.inside(p.x, p.z)
        if active:
            for ev in suit.tick(dt, self.moving, self.inside):
                self.on_oxygen_event(ev)
            status = suit.status
            if status in ("low", "critical") and not self.inside:       # repeating alarm until you refill
                if now >= self._alarm_t:
                    self.audio.sfx("alarm_crit" if status == "critical" else "alarm_low", volume=0.8)
                    self._alarm_t = now + (1.6 if status == "critical" else 4.0)
            self.sounds.update(dt, self.moving, p.grounded, status, self.inside)
        vm = self.viewmodel
        if vm is not None and not vm.is_empty():
            vm.update_motion(dt, self.moving, mouse.velocity[0] if active else 0.0)
            vm.set_oxygen(suit.oxygen, suit.status, now)
        # oxygen station: refill while standing close, stop when walking away or full
        if self.refilling:
            if hab.distance_to("hab_o2", p.x, p.z) > INTERACT_RANGE + 1.5:
                self._stop_refill(silent=True)
            elif suit.refill(dt):
                self._stop_refill()
        near_o2 = hab.distance_to("hab_o2", p.x, p.z) < 9
        if near_o2:
            hab.set_o2_screen(suit.oxygen, self.refilling)
        self._charge_t -= dt
        if self._charge_t <= 0:
            self._charge_t = 0.3
            self.refresh_charges()
            hab.set_locker_leds(suit.charges)

    def on_oxygen_event(self, ev):
        p = int(self.suit.oxygen)
        if ev == "low":
            self.toast(self.T("o2_low", p=max(p, 1)), 6)
            self.audio.sfx("alarm_low")
            self._alarm_t = pytime.time() + 4.0
        elif ev == "critical":
            self.toast(self.T("o2_critical", p=max(p, 1)), 6)
            self.audio.sfx("alarm_crit")
            self._alarm_t = pytime.time() + 1.6
        elif ev == "empty":
            self.o2_emergency()
