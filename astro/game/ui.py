"""Reusable, themed UI building blocks (colours taken from the Astro Play logo).

Everything that shows text goes through ``i18n.shape`` here, so Arabic is joined and ordered correctly and
the right font is used.  Pass *logical* text to these helpers (never pre-shaped text).
"""
from ursina import *  # noqa: F401,F403
from ursina.models.procedural.circle import Circle
from ursina.models.procedural.quad import Quad
from panda3d.core import TransparencyAttrib

from .. import config, i18n

# Palette sampled from the logo
NAVY = (0.004, 0.05, 0.176)      # logo background (#010D2D) - screens use it so the logo blends in
PANEL = (0.02, 0.07, 0.22)
CYAN = (0.16, 0.83, 1.0)
BLUE = (0.16, 0.42, 1.0)
PURPLE = (0.55, 0.32, 1.0)
MAGENTA = (0.95, 0.3, 0.85)
GOLD = (1.0, 0.8, 0.25)
GREEN = (0.3, 0.9, 0.55)
RED = (1.0, 0.4, 0.45)
WHITE = (1, 1, 1)

_cache = {}
_sfx_hook = lambda name, **kw: None


def set_sfx_hook(fn):
    """Game installs its audio here so buttons can click/hover without importing audio."""
    global _sfx_hook
    _sfx_hook = fn


def sfx(name, **kw):
    _sfx_hook(name, **kw)


def rgba(c, a=1.0):
    return Color(c[0], c[1], c[2], a)


def tex(name):
    """Texture from assets/ui (or a path relative to assets/, e.g. 'sky/earth.png')."""
    if name not in _cache:
        p = config.ASSETS_DIR / "ui" / name
        if not p.exists():
            p = config.ASSETS_DIR / name
        if not p.exists():                                 # an Ursina built-in such as "white_cube"
            _cache[name] = load_texture(name.rsplit(".", 1)[0] if name.endswith(".png") else name)
            return _cache[name]
        t = Texture(p)
        if name.startswith(("ground_", "mottle_", "detail_", "rock", "crater", "footprint", "sky/")):
            t.filtering = "mipmap"                       # smooth at a distance...
            from panda3d.core import SamplerState
            t._texture.setMagfilter(SamplerState.FT_linear)   # ...and not blocky up close (Ursina only sets the min filter)
            t._texture.setAnisotropicDegree(4)
        _cache[name] = t
    return _cache[name]


def setup_fonts():
    """Point Ursina's font search at our fonts folder (so lookup by file name is fast and finds ours)."""
    application.fonts_folder = config.ASSETS_DIR / "fonts"


def logo_texture():
    """The official logo as a texture. The file itself is never modified; at display time only the
    navy corners outside the logo's circle are made transparent so it blends into the backdrop."""
    path = config.find_logo()
    if not path:
        return None
    if "logo" not in _cache:
        try:
            from PIL import Image, ImageDraw, ImageFilter
            im = Image.open(path).convert("RGBA")
            w, h = im.size
            r = min(w, h) * 0.452            # just outside the outer ring (~0.43)
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), fill=255)
            im.putalpha(mask.filter(ImageFilter.GaussianBlur(w * 0.006)))
            _cache["logo"] = Texture(im)
        except Exception:
            _cache["logo"] = Texture(path)
    return _cache["logo"]


def image(parent, name, pos=(0, 0), scale=(1, 1), col=None, z=0, **kw):
    e = Entity(parent=parent, model="quad", texture=tex(name), position=(pos[0], pos[1], z),
               scale=scale, color=col or color.white, **kw)
    e.setTransparency(TransparencyAttrib.MAlpha)
    return e


def panel(parent, pos, size, fill=PANEL, alpha=0.9, outline=CYAN, oalpha=0.55, radius=0.07, z=1, brackets=False):
    """Glassy rounded panel with an optional neon outline and sci-fi corner brackets."""
    aspect = size[0] / size[1]
    e = Entity(parent=parent, model=Quad(radius=radius, aspect=aspect), position=(pos[0], pos[1], z),
               scale=size, color=rgba(fill, alpha))
    # soft lighter top band gives a "glass" look
    bh = min(0.16, 0.12 / size[1])
    Entity(parent=e, model=Quad(radius=0.4, aspect=(size[0] * 0.97) / (size[1] * bh)), scale=(0.97, bh),
           y=0.5 - bh / 2 - 0.015, color=rgba(WHITE, 0.04), z=-0.0005)
    if outline:
        Entity(parent=e, model=Quad(radius=radius, aspect=aspect, mode="line", thickness=2),
               color=rgba(outline, oalpha), z=-0.001)
        if brackets:
            ln, th = min(size) * 0.28, 0.006
            for sx in (-1, 1):
                for sy in (-1, 1):
                    Entity(parent=e, model="quad", color=rgba(outline, min(1.0, oalpha + 0.4)), z=-0.002,
                           scale=(ln / size[0], th / size[1]),
                           position=(sx * (0.5 - ln / size[0] / 2), sy * (0.5 - th / size[1] / 2)))
                    Entity(parent=e, model="quad", color=rgba(outline, min(1.0, oalpha + 0.4)), z=-0.002,
                           scale=(th / size[0], ln / size[1]),
                           position=(sx * (0.5 - th / size[0] / 2), sy * (0.5 - ln / size[1] / 2)))
    return e


STYLES = {
    "primary": (BLUE, CYAN),
    "secondary": ((0.06, 0.12, 0.3), (0.35, 0.55, 0.95)),
    "success": ((0.07, 0.5, 0.36), (0.45, 1.0, 0.75)),
    "danger": ((0.5, 0.12, 0.22), (1.0, 0.45, 0.55)),
    "gold": ((0.55, 0.38, 0.05), (1.0, 0.8, 0.25)),
}


class GlowButton(Button):
    """Rounded button with a neon outline and a glow that brightens on hover (plus hover/click sounds)."""

    def on_mouse_enter(self):
        super().on_mouse_enter()
        if not self.disabled:
            sfx("hover", volume=0.5)
            g = getattr(self, "_glow", None)
            if g is not None and not g.is_empty():
                g.alpha = 0.75

    def on_mouse_exit(self):
        super().on_mouse_exit()
        g = getattr(self, "_glow", None)
        if g is not None and not g.is_empty():
            g.alpha = getattr(self, "_glow_base", 0.3)


def button(parent, text, pos, size, cb, style="primary", z=-0.02, text_scale=1.0, kind="body", font=None):
    fill, edge = STYLES[style]
    aspect = size[0] / size[1]
    glow = Entity(parent=parent, model="quad", texture=tex("glow.png"), position=(pos[0], pos[1], z + 0.01),
                  scale=(size[0] * 1.5, size[1] * 2.8), color=rgba(edge, 0.3))
    glow.setTransparency(TransparencyAttrib.MAlpha)
    b = GlowButton(parent=parent, text=i18n.shape(text), model=Quad(radius=0.3, aspect=aspect),
                   position=(pos[0], pos[1], z), scale=size, color=rgba(fill))
    b._glow, b._glow_base, b._glow_ent = glow, 0.3, glow
    b.highlight_color = rgba(fill).tint(0.18)
    b.pressed_color = rgba(fill).tint(-0.12)
    b.text_color = color.white
    if b.text_entity:
        b.text_entity.font = font or i18n.font(kind, text=text)
        b.text_size = text_scale
        b.highlight_text_size = text_scale
    Entity(parent=b, model=Quad(radius=0.3, aspect=aspect, mode="line", thickness=2), color=rgba(edge, 0.95), z=-0.01)
    Entity(parent=b, model=Quad(radius=0.3, aspect=aspect / 0.48 * 0.96), scale=(0.96, 0.48), y=0.24,
           color=rgba(WHITE, 0.10), z=-0.005)
    b.on_click = lambda: (sfx("click"), cb())
    return b


def destroy_button(b):
    g = getattr(b, "_glow_ent", None)
    if g is not None and not g.is_empty():
        destroy(g)
    destroy(b)


def restyle(b, style):
    fill, edge = STYLES[style]
    b.color = rgba(fill)
    b.highlight_color = rgba(fill).tint(0.18)
    b.pressed_color = rgba(fill).tint(-0.12)
    g = getattr(b, "_glow", None)
    if g is not None and not g.is_empty():
        g.color = rgba(edge, 0.3)


def icon_button(parent, icon, pos, size, cb, tint=WHITE, z=-0.05):
    """Small round icon button (music / sound / language). Use .set_icon(name) and .set_tint(rgb)."""
    glow = Entity(parent=parent, model="quad", texture=tex("glow.png"), position=(pos[0], pos[1], z + 0.01),
                  scale=size * 2.1, color=rgba(CYAN, 0.25))
    glow.setTransparency(TransparencyAttrib.MAlpha)
    b = GlowButton(parent=parent, model="circle", position=(pos[0], pos[1], z), scale=size,
                   color=rgba((0.02, 0.07, 0.22), 0.92))
    b._glow, b._glow_base, b._glow_ent = glow, 0.25, glow
    b.highlight_color = rgba((0.1, 0.2, 0.5), 0.95)
    b.pressed_color = rgba((0.02, 0.05, 0.15), 1)
    ico = Entity(parent=b, model="quad", texture=tex(f"{icon}.png"), scale=0.62, z=-0.01, color=rgba(tint))
    ico.setTransparency(TransparencyAttrib.MAlpha)
    Entity(parent=b, model=Circle(resolution=40, mode="line", thickness=2), color=rgba(CYAN, 0.75), z=-0.02)
    b._icon = ico
    b.set_icon = lambda name: setattr(ico, "texture", tex(f"{name}.png"))
    b.set_tint = lambda rgb, a=1.0: setattr(ico, "color", rgba(rgb, a))
    b.on_click = lambda: (sfx("click"), cb())
    return b


def label(parent, text, pos, scale=1.0, col=WHITE, origin=(0, 0), z=-0.03, alpha=1.0, kind="body"):
    t = Text(parent=parent, text=i18n.shape(text), position=(pos[0], pos[1], z), scale=scale, origin=origin,
             color=rgba(col, alpha))
    t.font = i18n.font(kind, text=text)
    if t.font is not None and i18n.has_arabic(text):
        t.line_height = 1.45                      # Arabic glyphs need more leading
    return t


def set_text(entity, text, kind="body"):
    """Update an existing label with new logical text (shapes it, picks a font that has the glyphs)."""
    f = i18n.font(kind, text=text)
    if getattr(entity, "_font_name", None) != f:
        entity._font_name = f
        entity.font = f
    entity.line_height = 1.45 if i18n.has_arabic(text) else 1
    entity.text = i18n.shape(text)


def progress_bar(parent, pos, width, height, frac, col=CYAN, z=-0.02):
    bg = panel(parent, pos, (width, height), fill=(0.02, 0.05, 0.15), alpha=1, outline=(0.3, 0.5, 0.9),
               oalpha=0.5, radius=0.5, z=z)
    fw = max(0.001, width * max(0.0, min(1.0, frac)))
    fill = Entity(parent=parent, model=Quad(radius=0.5, aspect=max(fw / height, 0.5)),
                  position=(pos[0] - width / 2 + fw / 2, pos[1], z - 0.005),
                  scale=(fw, height * 0.8), color=rgba(col))
    return bg, fill


def ring(parent, pos, size, col=WHITE, alpha=1.0, thickness=3, z=0):
    return Entity(parent=parent, model=Circle(resolution=48, mode="line", thickness=thickness),
                  position=(pos[0], pos[1], z), scale=size, color=rgba(col, alpha))


# ------------------------------------------------------------------------------------ text input
class TextBox(Entity):
    """Single-line text input that supports Arabic: it receives raw unicode keystrokes from Ursina
    (``text_input``) and displays the text shaped, right-aligned when it contains Arabic."""

    boxes = []

    def __init__(self, parent, pos, size=(0.7, 0.075), text="", placeholder="", max_len=24, on_submit=None,
                 on_change=None, text_scale=1.0, z=-0.02):
        super().__init__(parent=parent, position=(pos[0], pos[1], z))
        self.size_xy = size
        self.max_len = max_len
        self.on_submit = on_submit
        self.on_change = on_change
        self.text_value = text
        self.placeholder = placeholder
        self.active = True
        self._t = 0.0
        self._back_hold = 0.0
        aspect = size[0] / size[1]
        Entity(parent=self, model=Quad(radius=0.35, aspect=aspect), scale=size, color=rgba((0.01, 0.04, 0.15), 0.96))
        self._edge = Entity(parent=self, model=Quad(radius=0.35, aspect=aspect, mode="line", thickness=2),
                            scale=size, color=rgba(CYAN, 0.9), z=-0.001)
        self._ph = Text(parent=self, text="", scale=text_scale, origin=(0, 0), z=-0.005, color=rgba(WHITE, 0.35))
        self._ph.font = i18n.font("body")
        self._txt = Text(parent=self, text="", scale=text_scale * 1.1, origin=(-0.5, 0), z=-0.005, color=rgba(WHITE))
        self._txt.font = i18n.font("body")
        TextBox.boxes.append(self)
        self._render()

    @classmethod
    def typing(cls):
        cls.boxes = [b for b in cls.boxes if not b.is_empty()]
        return any(b.active and b.enabled for b in cls.boxes)

    @property
    def value(self):
        return self.text_value

    def set_value(self, v):
        self.text_value = v[: self.max_len]
        self._render()

    def _render(self, caret=True):
        v = self.text_value
        if not v:
            self._txt.text = ""
            self._ph.text = i18n.shape(self.placeholder)
            return
        self._ph.text = ""
        shown = v + ("|" if caret else "")
        rtl = i18n.has_arabic(v)
        self._txt.origin = (0.5, 0) if rtl else (-0.5, 0)
        room = self.size_xy[0] - 0.05
        while True:                                   # keep the newest characters visible if the text is too wide
            self._txt.text = i18n.shape(shown)
            if self._txt.width * self._txt.scale_x <= room or len(shown) < 3:
                break
            shown = shown[1:] if not rtl else shown[:-1]
        half = self.size_xy[0] / 2 - 0.022
        self._txt.x = half if rtl else -half

    def text_input(self, key):
        if not self.active or len(self.text_value) >= self.max_len:
            return
        self.text_value += key
        sfx("type", volume=0.4)
        self._render()
        if self.on_change:
            self.on_change()

    def input(self, key):
        if not self.active:
            return
        if key == "backspace":
            self._back_hold = 0.0
            self._backspace()
        elif key in ("enter", "return", "keypad enter"):
            if self.on_submit:
                self.on_submit()

    def _backspace(self):
        if self.text_value:
            self.text_value = self.text_value[:-1]
            self._render()
            if self.on_change:
                self.on_change()

    def update(self):
        if not self.active:
            return
        self._t += time.dt
        if held_keys["backspace"]:
            self._back_hold += time.dt
            if self._back_hold > 0.45:
                self._back_hold -= 0.05
                self._backspace()
        else:
            self._back_hold = 0.0
        self._render(caret=int(self._t * 2) % 2 == 0)
