"""Outpost Command screens (Ursina). Drawing and input only: every rule lives in ``astro.outpost`` and every flow
decision in ``astro.outpost_flow``.

Screens:  setup  ->  play  ->  result        and        cards (research cards, reachable from setup / play / result)

Network safety: this module never does network work. NASA lookups run on worker threads inside ``NasaData``; the game
loop only calls ``update()`` which applies finished results on the main thread, so no worker ever touches an Entity.

Layout: text is placed top-down inside each panel with a ``Stack`` using its MEASURED size, so wrapped lines (English or
Arabic) can never collide. Every label, button and panel registers its bounds in ``self.rects``; ``layout_problems()``
reports anything that leaves its panel, overlaps another widget, covers the top-bar icons or leaves the screen.
Text sizes: 0.75 is the smallest used (about 13.5 px at 720p); body text is 0.9.

For tests, every drawn label's logical (unshaped) text is kept in ``self.shown`` and every button in ``self.buttons``.
"""
import datetime as dt
import logging
import sys
import time
import traceback
import webbrowser
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from ursina import Text, camera, destroy

from .. import fileio, i18n, osdr_data
from .. import outpost as O
from .. import outpost_config as C
from ..outpost_flow import BackgroundLoader, NasaData, OutpostSession
from ..progression import tier_from_skill
from . import ui

log = logging.getLogger("astro.outpost_ui")
OFFICIAL_HOST = "https://osdr.nasa.gov/"            # the only place the "Open NASA study page" button may send you
SETTING_COLOR = {"spaceflight": ui.CYAN, "ground": ui.GOLD, "unknown": (0.65, 0.68, 0.78)}
SEVERITY_COLOR = {"low": ui.GREEN, "medium": ui.GOLD, "high": ui.RED}
SCREENS = ("setup", "play", "result", "cards", "error")
ERROR_WINDOW_S, ERROR_STREAK = 10.0, 3          # the same error 3 times within 10 s = a recurring failure
MAX_ERRORS_KEPT = 50
ERRORS: List[dict] = []                          # every drawing/data error of every Outpost UI, newest last (see _report)

SC_HEAD, SC_BODY, SC_SMALL, SC_MIN = 0.9, 0.9, 0.82, 0.75      # text scales (0.75 = smallest anywhere, about 13.5 px at 720p)
LINE = 0.025                                                     # height of one text line at scale 1 (Ursina's Text.size)
CHAR = 0.0108                                                    # generous width of one character at scale 1


def T(key, **kw):
    return i18n.t(key, **kw)


def num(v: float) -> str:
    return str(int(round(v)))


def signed(v: float) -> str:
    n = int(round(v))
    return f"{n:+d}" if n else "0"


def bar_color(frac: float, good=ui.GREEN):
    return ui.RED if frac < C.LOW_LEVEL / 100.0 else good


def chars(width: float, scale: float) -> int:
    """How many characters fit on one line of ``width`` screen units at ``scale`` (used as the wrap width)."""
    return max(8, int(width / (CHAR * scale) * 0.92))


@dataclass
class Rect:
    kind: str                       # text | button | panel
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    container: Optional[str] = None

    def overlaps(self, o: "Rect", eps: float = 0.003) -> bool:
        return self.x0 < o.x1 - eps and o.x0 < self.x1 - eps and self.y0 < o.y1 - eps and o.y0 < self.y1 - eps

    def inside(self, o: "Rect", eps: float = 0.003) -> bool:
        return self.x0 >= o.x0 - eps and self.x1 <= o.x1 + eps and self.y0 >= o.y0 - eps and self.y1 <= o.y1 + eps


class Stack:
    """Top-down text placement inside a panel. Each ``text`` call measures what it drew and moves the cursor below it."""

    def __init__(self, o: "OutpostUI", name: str, x0: float, x1: float, top: float, bottom: float, pad: float = 0.03):
        self.o, self.name, self.pad = o, name, pad
        self.x0, self.x1, self.top, self.bottom = x0 + pad, x1 - pad, top, bottom
        self.y = top - pad * 0.8

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    def x_for(self, align: str) -> float:
        return {"start": self.x0, "center": (self.x0 + self.x1) / 2, "end": self.x1}[align]

    def text(self, text, scale=SC_SMALL, col=ui.WHITE, align="start", kind="body", gap=0.014, alpha=1.0, lines=None,
             wrap=True, width=None):
        w = width if width is not None else self.width
        e = self.o.lab(text, (self.x_for(align), self.y), scale, col, align, kind, chars(w, scale) if wrap else None, alpha,
                       valign="top", container=self.name)
        h = (lines * LINE * scale * getattr(e, "line_height", 1)) if lines else e.height * e.scale_y
        self.y -= h + gap
        return e

    def space(self, h: float) -> None:
        self.y -= h

    def bar(self, frac: float, col, height=0.016, indent=0.0, gap=0.016) -> None:
        self.o.bar(((self.x0 + indent + self.x1) / 2, self.y - height / 2), self.x1 - self.x0 - indent, frac, col, height)
        self.y -= height + gap


class OutpostUI:
    def __init__(self, game, loader: Optional[BackgroundLoader] = None, opener: Callable[[str], object] = None):
        self.g = game
        self.loader = loader or BackgroundLoader()
        self.opener = opener or webbrowser.open
        self.nasa: Optional[NasaData] = None
        self.session: Optional[OutpostSession] = None
        self.screen = "setup"
        self.site, self.difficulty = "moon", "normal"
        self.card_index, self.card_filter = 0, None
        self._cards_back = "setup"
        self.dyn: List = []                        # widgets of the screen being shown (the backdrop belongs to Game)
        self.buttons: Dict[str, object] = {}
        self.shown: List[str] = []
        self.refs: Dict[str, object] = {}          # widgets that are updated in place (allocation values, preview)
        self.rects: List[Rect] = []                # measured bounds of everything drawn (for the layout check)
        self._rect_of: Dict[int, Rect] = {}
        self._sidx: Dict[int, int] = {}            # id(label) -> its position in self.shown
        self._wraps: Dict[int, Optional[int]] = {}
        self.active = False
        # ---- drawing failures are never silent: each is logged with its traceback AND kept here (see ``_report``)
        self.errors: List[dict] = []
        self.degraded = False                      # True after a recurring failure: automatic redraws are paused
        self._recent: List[tuple] = []
        self.overlay: List = []                    # the "something went wrong" notice drawn over a restored screen
        self.overlay_text: List[str] = []
        self._error_back = "setup"

    # ------------------------------------------------------------------ entering and leaving
    def enter(self) -> None:
        """Open Outpost Command from the main menu. Existing mission state is not touched."""
        self.active = True
        if self.nasa is None:
            self.nasa = NasaData(self.loader)          # local files only: instant, works offline
        profile = self.g.profile
        self.difficulty = tier_from_skill(profile["skill"]) if profile else "normal"
        self.session = None
        self.nasa.refresh()                            # background thread; ignored if one is already running
        self.g._rebuild = self.rebuild                 # language switch redraws this screen
        self.go("setup")

    def leave(self) -> None:
        """Back to the main menu. A run in progress stays saved and can be resumed."""
        self._clear_overlay()
        self._clear_dyn()
        self.active = False
        self.session = None
        self.g.show_menu()

    # ------------------------------------------------------------------ widgets
    # ------------------------------------------------------------------ drawing, with failures that stay visible
    def _report(self, context: str) -> None:
        """Record the exception being handled: logged with its traceback, kept in ``self.errors``, and counted so a
        recurring failure can be told apart from a one-off. Never swallowed silently, never re-raised from here."""
        exc = sys.exc_info()[1]
        sig = (context, type(exc).__name__, str(exc)[:80])
        now = time.monotonic()
        self._recent = [(t, x) for t, x in self._recent if now - t < ERROR_WINDOW_S] + [(now, sig)]
        if sum(1 for _, x in self._recent if x == sig) >= ERROR_STREAK:
            self.degraded = True
        entry = {"context": context, "type": type(exc).__name__, "message": str(exc),
                 "traceback": traceback.format_exc(), "screen": self.screen, "degraded": self.degraded}
        self.errors.append(entry)
        ERRORS.append(entry)
        del self.errors[:-MAX_ERRORS_KEPT], ERRORS[:-MAX_ERRORS_KEPT]
        log.error("Outpost screen problem while %s%s", context, " (recurring: automatic redraws paused)"
                  if self.degraded else "", exc_info=True)

    def consume_errors(self) -> List[dict]:
        """Return and clear the recorded errors (tests use this to acknowledge an error they provoked on purpose)."""
        out, self.errors = self.errors, []
        for e in out:
            if e in ERRORS:
                ERRORS.remove(e)
        return out

    def _destroy(self, widgets) -> None:
        """Destroy widgets AND their children. Ursina's own destroy() does not touch children (that code is commented out
        there), so without this every redraw would leave dozens of orphaned child entities in ``scene.entities``."""
        for e in widgets:
            if not e.is_empty():
                destroy(e)

    def _registries(self):
        return (self.dyn, self.buttons, self.shown, self.refs, self.rects, self._rect_of, self._sidx, self._wraps)

    def _set_registries(self, regs) -> None:
        (self.dyn, self.buttons, self.shown, self.refs, self.rects, self._rect_of, self._sidx, self._wraps) = regs

    def _clear_dyn(self) -> None:
        self._destroy(self.dyn)
        self._set_registries(([], {}, [], {}, [], {}, {}, {}))

    def _clear_overlay(self) -> None:
        self._destroy(self.overlay)
        self.overlay, self.overlay_text = [], []

    def go(self, screen: str) -> None:
        """Show a screen. If it cannot be drawn the player gets an explicit error screen (retry / main menu): never a
        half-built screen, and never a silent jump to the menu."""
        assert screen in SCREENS
        self._clear_overlay()
        self.screen = screen
        self._clear_dyn()
        self.g.screen("outpost", horizon=False, nebula=0.8)
        try:
            self.draw()
            self.degraded = False
        except Exception:
            self._report(f"drawing the '{screen}' screen")
            self._clear_dyn()
            if screen == "error":
                raise                                  # the error screen itself is broken: nothing safe is left to show
            self._error_back = screen
            self.screen = "error"
            self.draw_error()

    def rebuild(self) -> None:
        if self.active:
            self.go(self._error_back if self.screen == "error" else self.screen)

    def redraw(self) -> bool:
        """Draw the current screen again (after a click or new data) without rebuilding the backdrop.

        Transactional: the new widgets are built first and only replace the old ones if everything was drawn. If drawing
        fails, the partial widgets are discarded, the previous screen stays exactly as it was (still consistent and
        clickable), a notice is shown over it, and the error is logged and recorded. Returns True if the redraw happened."""
        old = self._registries()
        self._set_registries(([], {}, [], {}, [], {}, {}, {}))
        try:
            self.draw()
        except Exception:
            self._destroy(self.dyn)                    # throw away whatever was half-built
            self._set_registries(old)                  # ...and the previous screen is back, untouched
            self._report(f"redrawing the '{self.screen}' screen")
            self._show_notice()
            return False
        self._destroy(old[0])
        self._clear_overlay()
        self.degraded = False
        return True

    def _show_notice(self) -> None:
        """A small panel over the (restored) screen telling the player something went wrong, with an OK button."""
        self._clear_overlay()
        msg = T("op_ui_error_repeated" if self.degraded else "op_ui_error_notice")
        box = self.g.box((0, 0.0), (1.12, 0.36), alpha=0.97, outline=ui.GOLD, oalpha=0.9, brackets=True, z=-0.5)
        self.g.ui.remove(box)
        box.collider = "box"                           # it also absorbs clicks, so nothing underneath fires by accident
        title = self._text(T("op_ui_error_title"), (0, 0.105), 1.0, ui.GOLD, "center", "display", None, 1.0)
        body = self._text(msg, (0, 0.025), SC_BODY, ui.WHITE, "center", "body", chars(1.0, SC_BODY), 1.0, "center")
        ok = self.g.btn(T("op_ui_dismiss"), (0, -0.115), self._clear_overlay, size=(0.26, 0.06), style="gold", z=-0.55)
        self.g.ui.remove(ok)
        self.g.ui.remove(ok._glow_ent)
        for e in (title, body):
            e.z = -0.6
        self.overlay = [box, title, body, ok, ok._glow_ent]
        self.overlay_text = [T("op_ui_error_title"), msg, T("op_ui_dismiss")]

    @staticmethod
    def _text_rect(e, name, container) -> Rect:
        w, h = e.width * e.scale_x, e.height * e.scale_y
        x0 = e.x - (e.origin_x + 0.5) * w
        y1 = e.y - (e.origin_y - 0.5) * h              # origin_y 0.5 = anchored at the top, so the text hangs below y
        return Rect("text", name, x0, y1 - h, x0 + w, y1, container)

    def lab(self, text, pos, scale=SC_BODY, col=ui.WHITE, align="center", kind="body", wrap=None, alpha=1.0,
            valign="center", container=None):
        self.shown.append(text)
        e = self._text(text, pos, scale, col, align, kind, wrap, alpha, valign)
        self.dyn.append(e)
        self._sidx[id(e)], self._wraps[id(e)] = len(self.shown) - 1, wrap
        r = self._text_rect(e, text, container)
        self.rects.append(r)
        self._rect_of[id(e)] = r
        return e

    def _text(self, text, pos, scale, col, align, kind, wrap, alpha, valign="center"):
        """Same result as ``Game.label`` / ``ui.label`` (mirroring, wrapping, font, Arabic shaping once), but the font
        is chosen BEFORE the Text is built, which halves the cost of a label (a screen has about 60)."""
        x, y = pos
        ox = {"start": -0.5, "center": 0, "end": 0.5}[align]
        oy = {"center": 0, "top": 0.5, "bottom": -0.5}[valign]
        if self.g.rtl:
            x, ox = -x, -ox
        if wrap:
            text = i18n.wrap(text, wrap)
        font = i18n.font(kind, text=text)
        old = Text.default_font
        Text.default_font = font
        try:
            e = Text(parent=camera.ui, text=i18n.shape(text), position=(x, y, -0.03), scale=scale, origin=(ox, oy),
                     color=ui.rgba(col, alpha))
        finally:
            Text.default_font = old
        e._font_name = font                                   # so ui.set_text does not rebuild it when the font is unchanged
        if i18n.has_arabic(text):
            e.line_height = 1.45                              # Arabic glyphs need more leading (as in ui.label)
        return e

    def settext(self, e, text: str) -> None:
        """Change a label in place (cheap: no new widget). Keeps ``shown`` and the measured bounds in step; shapes Arabic once."""
        wrap = self._wraps.get(id(e))
        ui.set_text(e, i18n.wrap(text, wrap) if wrap else text)
        self.shown[self._sidx[id(e)]] = text
        old = self._rect_of.get(id(e))
        if old is not None:
            new = self._text_rect(e, text, old.container)
            old.x0, old.y0, old.x1, old.y1, old.name = new.x0, new.y0, new.x1, new.y1, text

    @staticmethod
    def set_enabled(b, enabled: bool) -> None:
        b.disabled = not enabled
        b.alpha = 1.0 if enabled else 0.45
        b._glow_ent.enabled = enabled

    def btn(self, key, text, pos, cb, size=(0.3, 0.065), style="secondary", text_scale=0.85, enabled=True, container=None):
        b = self.g.btn(text, pos, cb, size=size, style=style, text_scale=text_scale)
        self.g.ui.remove(b)
        self.g.ui.remove(b._glow_ent)
        self.dyn += [b, b._glow_ent]
        if not enabled:
            b.disabled = True
            b.alpha = 0.45
            b._glow_ent.enabled = False
        self.buttons[key] = b
        self.shown.append(text)
        x = self.g.mx(pos[0])
        self.rects.append(Rect("button", key, x - size[0] / 2, pos[1] - size[1] / 2, x + size[0] / 2,
                               pos[1] + size[1] / 2, container))
        return b

    def box(self, pos, size, name="panel", **kw):
        e = self.g.box(pos, size, **kw)
        self.g.ui.remove(e)
        self.dyn.append(e)
        x = self.g.mx(pos[0])
        self.rects.append(Rect("panel", name, x - size[0] / 2, pos[1] - size[1] / 2, x + size[0] / 2, pos[1] + size[1] / 2))
        return e

    def bar(self, pos, width, frac, col, height=0.016):
        x = self.g.mx(pos[0])
        bg, fill = ui.progress_bar(camera.ui, (x, pos[1]), width, height, frac, col)
        if self.g.rtl:                                # fill from the right edge in Arabic
            fill.x = x + width / 2 - fill.scale_x / 2
        self.dyn += [bg, fill]

    def panel(self, name, x0, x1, top, bottom, **kw) -> Stack:
        """Draw a panel and return a Stack for its content."""
        self.box(((x0 + x1) / 2, (top + bottom) / 2), (x1 - x0, top - bottom), name=name, **kw)
        return Stack(self, name, x0, x1, top, bottom)

    # ------------------------------------------------------------------ layout verification (used by the tests)
    def topbar_rects(self) -> List[Rect]:
        out = []
        for e in self.g.topbar:
            if getattr(e, "is_empty", lambda: True)() or getattr(e, "_glow_ent", None) is None:
                continue                                      # only the real buttons, not their soft glow halos
            out.append(Rect("topbar", "topbar", e.x - e.scale_x / 2, e.y - e.scale_y / 2, e.x + e.scale_x / 2,
                            e.y + e.scale_y / 2))
        return out

    def layout_problems(self) -> List[str]:
        """Everything wrong with the current screen's layout (empty list = clean)."""
        problems, eps = [], 0.003
        panels = {r.name: r for r in self.rects if r.kind == "panel"}
        widgets = [r for r in self.rects if r.kind in ("text", "button") and (r.kind == "button" or r.name.strip())]
        top = self.topbar_rects()
        for r in widgets:
            if r.x0 < -0.889 - eps or r.x1 > 0.889 + eps or r.y0 < -0.5 - eps or r.y1 > 0.5 + eps:
                problems.append(f"off screen: {r.kind} {r.name[:30]!r}")
            if r.container and r.container in panels and not r.inside(panels[r.container]):
                problems.append(f"outside its panel '{r.container}': {r.kind} {r.name[:30]!r}")
            for t in top:
                if r.overlaps(t):
                    problems.append(f"covers the top-bar icons: {r.kind} {r.name[:30]!r}")
        for r in widgets:
            for pn in panels.values():
                if r.overlaps(pn) and not r.inside(pn):
                    problems.append(f"straddles the edge of panel '{pn.name}': {r.kind} {r.name[:30]!r}")
        for i, a in enumerate(widgets):
            for b in widgets[i + 1:]:
                if a.overlaps(b):
                    problems.append(f"overlap: {a.kind} {a.name[:24]!r} / {b.kind} {b.name[:24]!r}")
        return problems

    # ------------------------------------------------------------------ dispatch
    def draw(self) -> None:
        {"setup": self.draw_setup, "play": self.draw_play, "result": self.draw_result,
         "cards": self.draw_cards, "error": self.draw_error}[self.screen]()

    def draw_error(self) -> None:
        """A known-good screen (no data needed) shown when another screen could not be drawn."""
        self.lab(T("op_ui_error_title"), (0, 0.2), 1.6, ui.GOLD, kind="display")
        self.lab(T("op_ui_error_screen"), (0, 0.06), SC_BODY + 0.1, ui.WHITE, wrap=60)
        self.btn("retry", T("op_ui_error_retry"), (-0.22, -0.18), lambda: self.go(self._error_back), (0.36, 0.07),
                 "success", 0.9)
        self.btn("menu", T("main_menu"), (0.22, -0.18), self.leave, (0.36, 0.07), "danger", 0.9)

    # ------------------------------------------------------------------ shared NASA status text
    def nasa_message(self) -> str:
        n = self.nasa
        if n is None:
            return ""
        if n.loading:
            return T("op_ui_nasa_loading")
        if "error" in n.state.values():
            return T("op_ui_nasa_failed")
        if n.unreachable:
            return T("op_ui_nasa_unreachable")
        return T("op_ui_nasa_done") if "ok" in n.state.values() else ""

    def solar_stack(self, st: Stack, solar, note: str = "full") -> None:
        """Solar activity level, where the number came from, and the honest 'game mapping' note."""
        st.text(T(solar.level_key), SC_HEAD, ui.CYAN, gap=0.01)
        st.bar(solar.level, ui.CYAN, 0.014, gap=0.01)
        st.text(solar.describe(), SC_SMALL, ui.WHITE, alpha=0.95, gap=0.004)
        when = solar.retrieved_text()                               # WHEN WE GOT IT (local time), never an event date
        if when:
            st.text(T("op_ui_retrieved", date=when), SC_MIN, ui.WHITE, alpha=0.8, gap=0.003)
        if solar.is_nasa_data:                                      # WHEN IT HAPPENED: the newest NASA event, unchanged
            if solar.latest_event_date:
                st.text(T("op_ui_latest_event", date=solar.latest_event_date), SC_MIN, ui.WHITE, alpha=0.8, gap=0.003)
                if solar.latest_event_date != dt.date.today().isoformat() and note == "full":
                    st.text(T("op_ui_latest_event_note"), SC_MIN, ui.WHITE, alpha=0.65, gap=0.004)
            elif solar.counts and not any(solar.counts.values()):
                st.text(T("op_ui_no_events"), SC_MIN, ui.WHITE, alpha=0.8, gap=0.01)
        if note == "full":
            st.text(T("op_ui_solar_note"), SC_MIN, ui.GOLD, alpha=0.95)
        elif note == "short":
            st.text(T("op_ui_solar_short"), SC_MIN, ui.GOLD, alpha=0.95)

    # ------------------------------------------------------------------ setup screen
    def draw_setup(self) -> None:
        g, n = self.g, self.nasa
        self.lab(T("op_ui_title"), (0, 0.42), 1.9, ui.CYAN, kind="display")
        self.lab(T("op_ui_setup_sub"), (0, 0.345), SC_SMALL, ui.WHITE, wrap=78, alpha=0.9)
        # ---- left: mission choices
        self.box((-0.41, -0.055), (0.66, 0.66), name="choices", alpha=0.85, brackets=True)
        self.lab(T("op_ui_location"), (-0.41, 0.2), SC_HEAD, ui.GOLD, kind="display", container="choices")
        for i, site in enumerate(C.SITES):
            self.btn(f"site:{site}", T(f"op_ui_site_{site}"), (-0.565 + i * 0.31, 0.135), lambda s=site: self.pick(site=s),
                     (0.28, 0.07), "primary" if self.site == site else "secondary", container="choices")
        self.lab(T("op_ui_difficulty"), (-0.41, 0.065), SC_HEAD, ui.GOLD, kind="display", container="choices")
        for i, d in enumerate(C.DIFFICULTY):
            self.btn(f"diff:{d}", T(d), (-0.62 + i * 0.21, 0.0), lambda dd=d: self.pick(difficulty=dd),
                     (0.19, 0.065), "primary" if self.difficulty == d else "secondary", 0.8, container="choices")
        pid = g.profile["id"] if g.profile else None
        run = g.db.latest_unfinished_outpost_run(pid)
        self.btn("start", T("op_ui_start"), (-0.41, -0.09), self.start_run, (0.5, 0.075), "success", 1.0, container="choices")
        if run:
            self.btn("resume", T("op_ui_resume", n=run["sol"]), (-0.41, -0.175), self.resume_run, (0.5, 0.065), "gold",
                     container="choices")
        self.btn("research", T("op_ui_research"), (-0.41, -0.255), lambda: self.open_cards("setup"), (0.5, 0.065),
                 container="choices")
        best = g.db.best_outpost_score(pid)
        if best:
            self.lab(T("op_ui_best", n=num(best)), (-0.41, -0.322), SC_SMALL, ui.GREEN, container="choices")
        # ---- right: NASA data
        st = self.panel("nasa", 0.08, 0.74, 0.275, -0.385, alpha=0.85)
        st.text(T("op_ui_nasa"), SC_HEAD, ui.GOLD, "center", "display", gap=0.008)
        st.text(T("op_ui_donki_title"), SC_SMALL, ui.WHITE, alpha=0.8, gap=0.006)
        self.solar_stack(st, n.solar, "full")
        st.space(0.002)
        st.text(T("op_ui_osdr_title"), SC_SMALL, ui.WHITE, alpha=0.8, gap=0.006)
        st.text(T("op_ui_cards_count", n=len(n.studies.entries)), SC_HEAD, ui.CYAN, gap=0.008)
        st.text(n.studies.describe(), SC_SMALL, ui.WHITE, alpha=0.95, gap=0.012)
        checked = fileio.local_text(n.checked_at.get("donki")) if n.checked_at.get("donki") else None
        if checked and not n.loading:                                # when NASA was last ASKED (may differ from when data came)
            st.text(T("op_ui_checked", when=checked), SC_MIN, ui.WHITE, alpha=0.8, gap=0.003)
        st.text(self.nasa_message(), SC_SMALL, ui.GOLD if n.loading else ui.WHITE, lines=2, gap=0.0)
        self.btn("refresh", T("op_ui_refresh"), (0.41, -0.335), self.refresh_nasa, (0.46, 0.058), "secondary", 0.8,
                 enabled=not n.loading, container="nasa")
        self.btn("menu", T("main_menu"), (0, -0.44), self.leave, (0.36, 0.062), "danger")

    def pick(self, site: Optional[str] = None, difficulty: Optional[str] = None) -> None:
        self.site = site or self.site
        self.difficulty = difficulty or self.difficulty
        self.redraw()

    def refresh_nasa(self) -> None:
        if self.nasa and self.nasa.refresh(force=True):              # the player asked: always ask NASA, even if a cache is fresh
            self.redraw()

    def start_run(self) -> None:
        pid = self.g.profile["id"] if self.g.profile else None
        self.session = OutpostSession.new(self.g.db, pid, self.site, self.difficulty, self.nasa.solar)
        self.go("play")

    def resume_run(self) -> None:
        pid = self.g.profile["id"] if self.g.profile else None
        self.session = OutpostSession.resume(self.g.db, pid)
        if self.session is None:
            self.redraw()                            # the save was damaged and has been retired
        else:
            self.site, self.difficulty = self.session.state.site, self.session.state.difficulty
            self.go("play")

    # ------------------------------------------------------------------ play screen
    LEFT, MID, RIGHT = (-0.87, -0.37), (-0.35, 0.35), (0.37, 0.87)
    PANEL_TOP, PANEL_BOTTOM = 0.345, -0.385

    def resource_row(self, st: Stack, label_key, value, cap, col, small=False, indent=0.0) -> None:
        sc = SC_SMALL if small else SC_BODY
        name = self.lab(T(label_key), (st.x0 + indent, st.y), sc, ui.WHITE, "start", valign="top", container=st.name)
        self.lab(f"{num(value)}/{num(cap)}", (st.x1, st.y), sc, col, "end", valign="top", container=st.name)
        st.y -= name.height * name.scale_y + 0.008
        st.bar(value / cap, bar_color(value / cap, col), 0.012 if small else 0.016, indent, gap=0.012 if small else 0.02)

    def draw_play(self) -> None:
        s = self.session
        st = s.state
        # ---- header: location, sol, crew health and score (status indicators, not resources)
        self.lab(f"{T(f'op_ui_site_{st.site}')}  -  {T(st.difficulty)}", (-0.86, 0.492), SC_SMALL, ui.CYAN, "start",
                 valign="top")
        self.lab(T("op_ui_sol", n=min(st.sol, st.total_sols), total=st.total_sols), (-0.86, 0.455), 1.15, ui.GOLD, "start",
                 kind="display", valign="top")
        self.lab(T("op_crew_health"), (-0.2, 0.492), SC_SMALL, ui.WHITE, "start", valign="top")
        self.bar((-0.07, 0.445), 0.28, st.crew_health / C.CAP["crew_health"],
                 bar_color(st.crew_health / C.CAP["crew_health"]), 0.014)
        self.lab(f"{T('op_score')}: {num(st.score)}", (0.18, 0.492), SC_BODY, ui.GOLD, "start", valign="top")
        self.lab(T(f"op_ui_status_{st.status}"), (0.18, 0.455), SC_SMALL, ui.GREEN if st.status != O.LOST else ui.RED,
                 "start", valign="top")
        top, bottom = self.PANEL_TOP, self.PANEL_BOTTOM
        # ---- left: exactly three resource categories (life support has oxygen and food inside)
        left = self.panel("resources", *self.LEFT, top, bottom, alpha=0.85)
        left.text(T("op_ui_resources"), SC_HEAD, ui.GOLD, "center", "display", gap=0.012)
        self.resource_row(left, "op_power", st.power, C.CAP["power"], ui.GOLD)
        self.resource_row(left, "op_life_support", O.life_support(st), C.CAP["oxygen"], ui.GREEN)
        self.resource_row(left, "op_oxygen", st.oxygen, C.CAP["oxygen"], ui.GREEN, True, 0.06)
        self.resource_row(left, "op_food", st.food, C.CAP["food"], ui.GREEN, True, 0.06)
        self.resource_row(left, "op_shielding", st.shielding, C.CAP["shielding"], ui.PURPLE)
        self.draw_preview(left)
        # ---- middle: power allocation
        mid = self.panel("allocation", *self.MID, top, bottom, alpha=0.85, brackets=True)
        mid.text(T("op_ui_allocation"), SC_HEAD, ui.GOLD, "center", "display", gap=0.014)
        mid.text(T("op_ui_available", n=s.available()), SC_BODY, ui.CYAN, gap=0.004)
        self.refs["allocated"] = mid.text(T("op_ui_allocated", n=s.allocated()), SC_SMALL, ui.WHITE, alpha=0.9, lines=1,
                                          gap=0.002)
        self.refs["unspent"] = mid.text(T("op_ui_unspent", n=s.unspent()), SC_SMALL, ui.WHITE, alpha=0.9, lines=1,
                                        gap=0.02)
        text_w = 0.40
        for cat in C.ALLOCATIONS:
            row_top = mid.y
            mid.text(T(f"op_{cat}"), SC_BODY, ui.WHITE, gap=0.004, width=text_w)
            mid.text(T(f"op_ui_hint_{cat}"), SC_MIN, ui.WHITE, alpha=0.8, gap=0.0, width=text_w)
            centre = (row_top + mid.y) / 2
            self.btn(f"minus:{cat}", "-", (0.135, centre), lambda c=cat: self.change(c, -1), (0.06, 0.055), "secondary",
                     1.2, enabled=s.alloc[cat] > 0, container=mid.name)
            self.refs[f"val:{cat}"] = self.lab(str(s.alloc[cat]), (0.21, centre + 0.006), SC_BODY + 0.1, ui.GOLD,
                                               container=mid.name)
            self.btn(f"plus:{cat}", "+", (0.285, centre), lambda c=cat: self.change(c, +1), (0.06, 0.055), "secondary", 1.2,
                     enabled=s.alloc[cat] < s.limit(cat) and s.unspent() > 0, container=mid.name)
            self.lab(T("op_ui_limit", n=s.limit(cat)), (0.21, centre - 0.034), SC_MIN, ui.WHITE, alpha=0.75,
                     valign="top", container=mid.name)           # under the buttons (never beside them)
            mid.y -= 0.022
        mid.text(T("op_ui_focus"), SC_SMALL, ui.WHITE, gap=0.006)
        y = mid.y - 0.026
        for i, choice in enumerate(C.LS_FOCUS_CHOICES):
            name = "op_ui_focus_oxygen" if choice == 1.0 else "op_ui_focus_food" if choice == 0.0 else "op_ui_focus_balanced"
            self.btn(f"focus:{choice}", T(name), (-0.2 + i * 0.2, y), lambda v=choice: self.focus(v), (0.185, 0.05),
                     "primary" if s.focus == choice else "secondary", 0.75, container=mid.name)
        # ---- right: events, forecast, effects and the solar activity of this run
        right = self.panel("events", *self.RIGHT, top, bottom, alpha=0.85)
        self.draw_events(right)
        # ---- bottom buttons (below every panel)
        self.btn("menu", T("main_menu"), (-0.66, -0.44), self.leave, (0.3, 0.062), "danger", 0.85)
        self.btn("reset", T("op_ui_reset"), (-0.31, -0.44), self.reset, (0.24, 0.062), "secondary", 0.85)
        self.btn("advance", T("op_ui_advance"), (0.07, -0.44), self.advance, (0.46, 0.07), "success", 0.95,
                 enabled=s.running)
        self.btn("research", T("op_ui_research"), (0.49, -0.44), lambda: self.open_cards("play"), (0.3, 0.062),
                 "secondary", 0.85)
        self.lab(T("op_ui_help"), (0, -0.486), SC_MIN, ui.WHITE, wrap=130, alpha=0.7)

    PREVIEW_ROWS = (("op_power", "power"), ("op_oxygen", "oxygen"), ("op_food", "food"), ("op_shielding", "shielding"),
                    ("op_crew_health", "crew_health"))

    def draw_preview(self, st: Stack) -> None:
        """Fixed slots (so a click only has to change their text, never rebuild the screen)."""
        st.text(T("op_ui_preview"), SC_SMALL, ui.CYAN, gap=0.002)
        st.text(T("op_ui_preview_note"), SC_MIN, ui.WHITE, alpha=0.75, gap=0.012)
        for i in range(len(self.PREVIEW_ROWS)):
            self.refs[f"prev:{i}"] = st.text("-", SC_SMALL, ui.WHITE, alpha=0.95, lines=1, gap=0.008, wrap=False)
        self.refs["warn"] = st.text("-", SC_BODY, ui.RED, lines=2, gap=0.0)
        self.update_preview()

    def update_preview(self) -> None:
        p = self.session.preview()
        ok = bool(p.get("valid"))
        for i, (key, field) in enumerate(self.PREVIEW_ROWS):
            text = (T("op_ui_value_delta", name=T(key), value=num(p["next"][field]), delta=signed(p["delta"][field]))
                    if ok else "")
            self.settext(self.refs[f"prev:{i}"], text)
        warnings = p["warnings"][:2] if ok else []
        self.settext(self.refs["warn"], "\n".join(T(w) for w in warnings))

    def refresh_plan(self) -> None:
        """The plan changed: update only the numbers, button states and preview that depend on it."""
        s = self.session
        for cat in C.ALLOCATIONS:
            self.settext(self.refs[f"val:{cat}"], str(s.alloc[cat]))
            self.set_enabled(self.buttons[f"minus:{cat}"], s.alloc[cat] > 0)
            self.set_enabled(self.buttons[f"plus:{cat}"], s.alloc[cat] < s.limit(cat) and s.unspent() > 0)
        self.settext(self.refs["allocated"], T("op_ui_allocated", n=s.allocated()))
        self.settext(self.refs["unspent"], T("op_ui_unspent", n=s.unspent()))
        for choice in C.LS_FOCUS_CHOICES:
            ui.restyle(self.buttons[f"focus:{choice}"], "primary" if s.focus == choice else "secondary")
        self.update_preview()

    def draw_events(self, st: Stack) -> None:
        s = self.session
        f = s.forecast_view()
        st.text(T("op_ui_forecast_title"), 0.75, ui.GOLD, "center", "display", gap=0.014)
        if f["blackout_sols"] > 0:
            comms = T("op_ui_comms_down", n=f["blackout_sols"])
        else:
            comms = T("op_ui_comms_ok" if f["comms_ok"] else "op_ui_comms_weak")
        st.text(T("op_ui_comms_status", state=comms), SC_SMALL, ui.WHITE, alpha=0.95, gap=0.012)
        if f["kind"] == "exact":
            st.text(T("op_forecast_exact", event=T(f"op_event_{f['event']}")), SC_SMALL, ui.CYAN, gap=0.008)
            st.text(T("op_ui_severity", level=T(f"op_ui_sev_{f['severity']}")), SC_SMALL, SEVERITY_COLOR[f["severity"]],
                    gap=0.016)
        elif f["kind"] == "category":
            st.text(T(f"op_forecast_{f['category']}"), SC_SMALL, ui.CYAN, gap=0.016)
        elif f["kind"] == "quiet":
            st.text(T("op_ui_forecast_quiet"), SC_SMALL, ui.GREEN, gap=0.016)
        else:
            st.text(T("op_forecast_off"), SC_SMALL, ui.WHITE, alpha=0.95, gap=0.008)
        if f["kind"] != "exact":                                   # the thresholds matter only until you have a forecast
            st.text(T("op_ui_forecast_need", a=f["need_hint"], b=f["need_full"]), SC_MIN, ui.WHITE, alpha=0.75, gap=0.016)
        # ---- last sol
        last = s.last_sol_view()
        if last:
            st.text(T("op_ui_last_sol", n=last["sol"]), SC_BODY - 0.1, ui.GOLD, kind="display", gap=0.008)
            if last["event"]:
                st.text(T(f"op_event_{last['event']}"), SC_SMALL, ui.WHITE, gap=0.006)
                st.text(T("op_ui_severity", level=T(f"op_ui_sev_{last['severity']}")), SC_SMALL,
                        SEVERITY_COLOR[last["severity"]], gap=0.008)
            else:
                st.text(T("op_ui_no_event"), SC_SMALL, ui.GREEN, gap=0.008)
            msgs = [T(k, **p) for k, p in last["messages"][:2]]
            if msgs:
                st.text("\n".join(msgs), SC_MIN, ui.WHITE, alpha=0.9, gap=0.016)
        # ---- active effects
        st.text(T("op_ui_effects"), SC_BODY - 0.1, ui.GOLD, kind="display", gap=0.008)
        effects = s.effects_view()
        if effects:
            st.text("\n".join(T(e["key"], **{k: v for k, v in e.items() if k != "key"}) for e in effects[:2]), SC_MIN,
                    ui.WHITE, gap=0.016)
        else:
            st.text(T("op_ui_no_effects"), SC_MIN, ui.WHITE, alpha=0.75, gap=0.016)
        # ---- solar activity used by this run (fixed when the run started)
        solar = s.solar()
        st.text(T(solar.level_key), SC_SMALL + 0.05, ui.CYAN, gap=0.004)
        st.text(solar.describe(), SC_MIN, ui.WHITE, alpha=0.9, gap=0.004)
        st.text(T("op_ui_solar_short"), SC_MIN, ui.GOLD, alpha=0.95, gap=0.0)

    def change(self, cat: str, delta: int) -> None:
        step = 5 if self._shift() else 1
        if self.session.adjust(cat, delta * step):
            self.refresh_plan()

    def focus(self, value: float) -> None:
        if self.session.set_focus(value):
            self.refresh_plan()

    def reset(self) -> None:
        self.session.reset()
        self.refresh_plan()

    @staticmethod
    def _shift() -> bool:
        try:
            from ursina import held_keys
            return bool(held_keys["shift"])
        except Exception:
            return False

    def advance(self) -> None:
        s = self.session
        if not s or not s.advance():
            return
        if s.running:
            self.g.audio.sfx("click", volume=0.6)
            self.redraw()
        else:
            self.go("result")

    # ------------------------------------------------------------------ result screen
    def draw_result(self) -> None:
        r = self.session.result()
        won = r["status"] == O.WON
        self.lab(T("op_ui_result_won" if won else "op_ui_result_lost"), (0, 0.36), 2.1, ui.GREEN if won else ui.RED,
                 kind="display")
        if won:
            for i in range(3):
                self.dyn.append(self.g.img("star_full.png" if i < r["stars"] else "star_empty.png",
                                           (-0.14 + i * 0.14, 0.24), (0.12, 0.12)))
                self.g.ui.remove(self.dyn[-1])
            self.lab(T("op_ui_stars", n=r["stars"]), (0, 0.15), 0.9, ui.GOLD)
        self.lab(T("op_ui_final_score", n=num(r["score"])), (0, 0.095), 1.05, ui.WHITE)
        self.lab(T("op_ui_sols_survived", n=r["sols"], total=r["total_sols"]), (0, 0.045), SC_BODY, ui.WHITE, alpha=0.9)
        self.lab(T("op_ui_seed", n=r["seed"]), (0, 0.005), SC_MIN, ui.WHITE, alpha=0.7)
        if won:
            self.lab(T("op_msg_won"), (0, -0.09), 1.0, ui.GREEN, wrap=64)
        else:
            self.lab(T("op_ui_why_failed"), (0, -0.045), SC_HEAD, ui.GOLD, kind="display")
            self.lab(r["failure_text"], (0, -0.15), 0.85, ui.WHITE, wrap=64)
        self.btn("again", T("op_ui_play_again"), (-0.4, -0.36), lambda: self.go("setup"), (0.34, 0.07), "success", 0.9)
        self.btn("research", T("op_ui_research"), (0.0, -0.36), lambda: self.open_cards("result"), (0.34, 0.07), "secondary", 0.9)
        self.btn("menu", T("main_menu"), (0.4, -0.36), self.leave, (0.34, 0.07), "danger", 0.9)

    # ------------------------------------------------------------------ research cards
    def open_cards(self, back: str) -> None:
        self._cards_back = back
        self.card_index = 0
        self.go("cards")

    def filtered_cards(self):
        cards = self.nasa.studies.cards()
        return [c for c in cards if self.card_filter in (None, c.topic)]

    def draw_cards(self) -> None:
        self.lab(T("op_ui_cards_title"), (0, 0.445), 1.5, ui.CYAN, kind="display")
        self.btn("filter:all", T("op_ui_filter_all"), (-0.6, 0.385), lambda: self.set_filter(None), (0.22, 0.05),
                 "primary" if self.card_filter is None else "secondary", 0.7)
        for i, topic in enumerate(osdr_data.TOPICS):
            self.btn(f"filter:{topic}", T(f"op_osdr_topic_{topic}"), (-0.36 + i * 0.235, 0.385),
                     lambda t=topic: self.set_filter(t), (0.225, 0.05), "primary" if self.card_filter == topic else "secondary",
                     0.6)
        cards = self.filtered_cards()
        self.lab(self.nasa.studies.describe(), (0, 0.335), SC_MIN, ui.WHITE, alpha=0.9, wrap=110)
        if not cards:
            self.lab(T("op_osdr_empty"), (0, 0.0), 1.0, ui.WHITE)
        else:
            self.card_index %= len(cards)
            self.draw_card(cards[self.card_index])
            self.btn("prev", T("op_ui_prev"), (-0.43, -0.42), lambda: self.step_card(-1), (0.25, 0.065), "secondary", 0.8)
            self.lab(T("op_ui_card_n", n=self.card_index + 1, total=len(cards)), (-0.1, -0.42), SC_BODY, ui.WHITE)
            self.btn("next", T("next"), (0.22, -0.42), lambda: self.step_card(1), (0.25, 0.065), "secondary", 0.8)
            self.btn("open", T("op_ui_open_nasa"), (0.62, -0.42), lambda c=cards[self.card_index]: self.open_study(c),
                     (0.46, 0.065), "primary", 0.75)
        self.btn("back", T("back"), (-0.74, -0.42), lambda: self.go(self._cards_back), (0.2, 0.065), "danger", 0.8)

    def draw_card(self, card) -> None:
        r = card.render()
        st = self.panel("card", -0.81, 0.81, 0.295, -0.365, alpha=0.9, brackets=True)
        head = st.y
        a = self.lab(r["topic"], (st.x0, head), SC_HEAD, ui.GOLD, "start", "display", valign="top", container="card")
        b = self.lab(r["setting"], (st.x1, head), SC_BODY, SETTING_COLOR[card.setting], "end", valign="top", container="card")
        st.y -= max(a.height * a.scale_y, b.height * b.scale_y) + 0.01
        st.text(f"{T('op_osdr_accession')}: {card.accession}   |   {r['data_status']}", SC_MIN, ui.WHITE, alpha=0.8, gap=0.02)
        st.text(r["official_title"], 1.05, ui.WHITE, "center", gap=0.014)                    # NASA's English title, unchanged
        facts = []
        if card.organism:
            facts.append(f"{T('op_osdr_organism')}: {r['organism']}")
        if card.mission:
            facts.append(f"{T('op_osdr_mission')}: {card.mission}")
        if card.platform:
            facts.append(f"{T('op_osdr_platform')}: {r['platform']}")
        if facts:
            st.text("   |   ".join(facts), SC_SMALL, ui.WHITE, "center", alpha=0.9, gap=0.016)
        st.text(r["summary"], 1.0, ui.CYAN, "center", gap=0.022)
        # ---- the educational box: contents first (measured), then the box drawn around them with padding
        pad = 0.022
        inner = Stack(self, "card", st.x0 + 0.02, st.x1 - 0.02, st.y, st.bottom, pad=pad)
        box_top = st.y
        inner.text(T("op_osdr_game_label"), SC_SMALL, ui.GOLD, gap=0.01)
        inner.text(r["gameplay_note"], 1.0, ui.WHITE, "center", gap=0.016)
        inner.text(r["disclaimer"], SC_SMALL, ui.WHITE, "center", alpha=0.85, gap=0.0)
        box_bottom = inner.y - pad * 0.6
        self.box(((st.x0 + st.x1) / 2, (box_top + box_bottom) / 2), (st.x1 - st.x0, box_top - box_bottom), name="card-note",
                 alpha=0.9, outline=ui.GOLD, oalpha=0.5)
        st.y = box_bottom - 0.02
        st.text(card.source_url, SC_MIN, ui.CYAN, "center", alpha=0.9, gap=0.0)

    def set_filter(self, topic: Optional[str]) -> None:
        self.card_filter, self.card_index = topic, 0
        self.redraw()

    def step_card(self, d: int) -> None:
        n = len(self.filtered_cards())
        if n:
            self.card_index = (self.card_index + d) % n
            self.redraw()

    def open_study(self, card) -> None:
        """Open the study's own NASA page in the browser (external; the game itself makes no request)."""
        if isinstance(card.source_url, str) and card.source_url.startswith(OFFICIAL_HOST):
            try:
                self.opener(card.source_url)
            except Exception:
                pass

    # ------------------------------------------------------------------ input and per-frame work
    def input(self, key: str) -> None:
        if not self.active:
            return
        if key == "escape":
            if self.screen == "cards":
                self.go(self._cards_back)
            elif self.screen == "setup":
                self.leave()
            elif self.screen in ("play", "error"):
                self.leave()                                  # explicit player action; a run in progress stays saved
            else:
                self.go("setup")
        elif self.screen == "play" and self.session:
            if key in ("enter", "space"):
                self.advance()
            elif key == "r":
                self.reset()
        elif self.screen == "cards":
            if key in ("right arrow", "d"):
                self.step_card(1)
            elif key in ("left arrow", "a"):
                self.step_card(-1)

    def update(self) -> None:
        """Called every frame by the game loop: applies finished NASA results on THIS (main) thread.

        Errors are reported (logged with traceback, recorded, shown to the player) and the UI stays consistent; a
        recurring failure pauses automatic redraws instead of retrying every frame. The player is never sent back to the
        main menu behind their back."""
        if not (self.active and self.nasa):
            return
        try:
            changed = self.nasa.pump()
        except Exception:
            self._report("applying NASA results")      # a data problem: the screen itself is untouched
            return
        if changed and self.screen in ("setup", "play", "cards") and not self.degraded:
            self.redraw()
