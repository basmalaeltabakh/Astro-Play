"""Outpost Command UI tests: the REAL Game and OutpostUI in a real Ursina window (skipped if no window can be opened).

NASA calls are replaced by a controllable fake (``Net``) so nothing here touches the network; the background-loading
tests use real worker threads. Windows are small and short-lived, like the existing smoke test's."""
import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from astro import config, i18n, nasa_data, osdr_data
from astro import outpost as O
from astro import outpost_config as C
from astro.outpost_flow import BackgroundLoader, NasaData

ROOT = Path(__file__).resolve().parent.parent
MAIN_THREAD = threading.main_thread()
REAL_SOLAR, REAL_STUDIES = nasa_data.get_solar_activity, osdr_data.get_studies


class Net:
    """Stands in for NASA. ``mode``: live | fail (only saved data) | raise (worker error). ``gate`` blocks a worker."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.mode, self.gate, self.calls = "live", None, []

    def solar(self, **kw):
        if not kw.get("allow_network", True):
            return REAL_SOLAR(**kw)
        self.calls.append(("donki", threading.current_thread()))
        if self.gate:
            self.gate.wait(10)
        if self.mode == "raise":
            raise RuntimeError("boom")
        if self.mode == "fail":
            return REAL_SOLAR(allow_network=False)
        return nasa_data.SolarActivity(0.77, nasa_data.LIVE, "2026-11-09", ("2026-10-10", "2026-11-09"), {})

    def studies(self, **kw):
        if not kw.get("allow_network", True):
            return REAL_STUDIES(**kw)
        self.calls.append(("osdr", threading.current_thread()))
        if self.gate:
            self.gate.wait(10)
        if self.mode == "raise":
            raise RuntimeError("boom")
        base = REAL_STUDIES(allow_network=False)
        if self.mode == "fail":
            return base
        return osdr_data.StudySet(osdr_data._tag(base.entries, osdr_data.LIVE, "2026-11-09"), osdr_data.LIVE,
                                  "2026-11-09")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ui")
    try:
        from ursina import Text, Ursina
        Text.default_resolution = 1080 * Text.size
        app = Ursina(title="astro-ui-test", borderless=False, development_mode=False, size=(960, 540))
        for _ in range(2):
            app.step()
    except Exception as e:                                   # no display / no GPU: report, do not fail the suite
        pytest.skip(f"cannot open a window here: {type(e).__name__}")
    from astro.assistant import SpaceAssistant
    from astro.db import Database
    from astro.game.app import Game
    from astro.settings import Settings
    saved = (config.SETTINGS_PATH, config.DONKI_CACHE_PATH, config.OSDR_CACHE_PATH)
    config.SETTINGS_PATH = tmp / "settings.json"
    config.DONKI_CACHE_PATH, config.OSDR_CACHE_PATH = tmp / "donki_cache.json", tmp / "osdr_cache.json"
    net = Net()
    mp = pytest.MonkeyPatch()                                          # (real HTTP is blocked suite-wide by tests/netguard.py)
    mp.setattr(nasa_data, "get_solar_activity", net.solar)
    mp.setattr(osdr_data, "get_studies", net.studies)
    game = Game(Database(tmp / "t.db"), SpaceAssistant(use_chroma=False), Settings.load(tmp / "settings.json"))

    class Env:
        pass
    e = Env()
    e.app, e.game, e.net, e.tmp, e.opened = app, game, net, tmp, []
    e.step = lambda n=3: [app.step() for _ in range(n)]
    e.step(2)
    game._leave_splash()
    e.step(2)
    yield e
    mp.undo()
    config.SETTINGS_PATH, config.DONKI_CACHE_PATH, config.OSDR_CACHE_PATH = saved


@pytest.fixture
def ui(env, tmp_path):
    """A fresh Outpost UI on a fresh database, in English, at the main menu. Inline loader unless a test replaces it."""
    from astro.db import Database
    from astro.game.outpost_ui import OutpostUI
    env.net.reset()
    env.opened.clear()
    g = env.game
    previous = g.outpost                                     # a player leaves Outpost through leave(), which removes its
    previous._clear_overlay()                                # widgets; do the same here so no leftover button from the
    previous._clear_dyn()                                    # last test can sit under (and steal clicks from) this one
    previous.active = False
    env.step(1)
    g.db = Database(tmp_path / "t.db")
    g.audio.set_sfx(False)                                   # button clicks would otherwise play a sound each time
    g.show_menu()                                            # leave whatever screen the previous test ended on
    g.profile = None
    g.set_language("en")
    g.outpost = OutpostUI(g, loader=BackgroundLoader(inline=True), opener=env.opened.append)
    g.show_menu()
    env.step(2)
    env.g, env.o = g, g.outpost
    from astro.game import outpost_ui
    outpost_ui.ERRORS.clear()
    yield env
    leftover = list(outpost_ui.ERRORS)
    outpost_ui.ERRORS.clear()
    assert not leftover, "the Outpost UI reported an unexpected error: " + "; ".join(
        f"{e['context']}: {e['type']}: {e['message']}" for e in leftover)


def menu_buttons(g):
    return {e.text: e for e in g.ui if hasattr(e, "on_click") and getattr(e, "text_entity", None) is not None}


def click(env, key):
    env.o.buttons[key].on_click()
    env.step(1)


def open_outpost(env):
    menu_buttons(env.g)[i18n.shape(i18n.t("op_ui_menu"))].on_click()
    env.step(2)


def start_run(env, site="moon", difficulty="normal"):
    open_outpost(env)
    click(env, f"site:{site}")
    click(env, f"diff:{difficulty}")
    click(env, "start")
    return env.o.session


def section(o, start_key, end_key):
    a, b = o.shown.index(i18n.t(start_key)), o.shown.index(i18n.t(end_key))
    return o.shown[a + 1:b]


def sound_plan(o):
    s = o.session
    s.reset()
    for cat, want in (("life_support", 12), ("shielding", 6), ("comms", 5), ("science", 4)):
        s.adjust(cat, want)
    o.refresh_plan()                                         # in-place update, like a click (a full redraw is slow)


# ======================================================================= main menu and navigation
@pytest.mark.parametrize("lang", ["en", "ar"])
def test_main_menu_offers_outpost_command_next_to_the_existing_options(ui, lang):
    ui.g.set_language(lang)
    ui.step(2)
    texts = set(menu_buttons(ui.g))
    for key in ("new_game", "continue", "op_ui_menu", "quit"):
        assert i18n.shape(i18n.t(key, lang)) in texts, key                 # nothing was removed or renamed
    ys = sorted(round(e.y, 3) for e in menu_buttons(ui.g).values())
    assert len(ys) == len(set(ys)) >= 4                                     # four distinct rows: no overlap


def test_outpost_button_opens_the_outpost_setup_screen(ui):
    open_outpost(ui)
    assert ui.g.mode == "outpost" and ui.o.active and ui.o.screen == "setup" and ui.g._rebuild == ui.o.rebuild
    assert {"start", "research", "refresh", "menu", "site:moon", "site:mars", "diff:easy", "diff:normal",
            "diff:hard"} <= set(ui.o.buttons)
    assert i18n.t("op_ui_title") in ui.o.shown


def test_returning_to_the_main_menu_restores_it_completely(ui):
    open_outpost(ui)
    click(ui, "menu")
    assert ui.g.mode == "menu" and not ui.o.active and ui.o.dyn == [] and ui.g._rebuild == ui.g.show_menu
    assert i18n.shape(i18n.t("new_game")) in menu_buttons(ui.g) and ui.o.session is None
    open_outpost(ui)                                                         # and it can be opened again
    assert ui.g.mode == "outpost"


def test_escape_walks_back_one_level_at_a_time(ui):
    start_run(ui)
    assert ui.o.screen == "play"
    click(ui, "research")
    assert ui.o.screen == "cards"
    ui.g.input("escape"); ui.step(2)
    assert ui.o.screen == "play"                                             # cards -> where it was opened from
    ui.g.input("escape"); ui.step(2)
    assert ui.g.mode == "menu"                                               # play -> main menu (the run is saved)
    open_outpost(ui)
    assert ui.o.screen == "setup"
    ui.g.input("escape"); ui.step(2)
    assert ui.g.mode == "menu"


def test_outpost_is_a_separate_mode_that_never_runs_mission_code(ui):
    start_run(ui)
    for key in ("e", "h", "q", "tab", "1", "2", "3", "4", "scroll up", "left mouse down"):
        ui.g.input(key)                                                      # mission keys must be ignored here
    ui.step(5)                                                               # update() runs with mode == "outpost"
    assert ui.g.mode == "outpost" and ui.g.world is None and ui.g.state is None and ui.g.panel is None
    assert ui.o.screen == "play"


def test_language_button_redraws_the_current_outpost_screen(ui):
    start_run(ui)
    ui.g.toggle_language(); ui.step(2)
    assert ui.g.mode == "outpost" and ui.o.screen == "play" and ui.o.session is not None
    assert any(i18n.has_arabic(t) for t in ui.o.shown) and i18n.t("op_ui_advance", "ar") in ui.o.shown
    ui.g.toggle_language(); ui.step(2)
    assert i18n.t("op_ui_advance", "en") in ui.o.shown


# ======================================================================= existing game is unaffected
def test_existing_mission_navigation_still_works_around_outpost(ui):
    g = ui.g
    pid = g.db.create_profile("Astro", "mid")
    g.db.record_completion(pid, "moon", 3)
    g.load_profile(pid); ui.step(3)
    assert g.mode == "map"
    before = (g.db.get_profile(pid), g.db.get_progress(pid), g.db.completed_missions(pid), g.db.list_achievements(pid))
    g.show_menu(); ui.step(2)
    open_outpost(ui)
    click(ui, "start")
    sound_plan(ui.o)
    click(ui, "advance")
    click(ui, "menu")
    after = (g.db.get_profile(pid), g.db.get_progress(pid), g.db.completed_missions(pid), g.db.list_achievements(pid))
    assert before == after                                                   # no XP, stars, unlocks or achievements
    g.show_continue(); ui.step(2)
    assert g.mode == "continue"
    g.load_profile(pid); ui.step(3)
    assert g.mode == "map"
    g.show_briefing("mars") if "mars" in g.db.completed_missions(pid) | {"mars"} else None
    g.show_briefing("moon"); ui.step(3)
    assert g.mode == "briefing" and g.briefing_mission.id == "moon"
    from astro.missions import MISSIONS
    assert len(MISSIONS) == 4 and not [m for m in MISSIONS if "outpost" in m.id]


def test_starting_outpost_never_touches_a_mission_in_progress_flag_or_profile(ui):
    g = ui.g
    pid = g.db.create_profile("Astro", "mid")
    g.load_profile(pid); ui.step(2)
    g.show_menu(); ui.step(2)
    start_run(ui)
    assert g.profile["id"] == pid and ui.o.session.profile_id == pid and g.state is None
    assert g.db.latest_unfinished_outpost_run(pid)["profile_id"] == pid


def test_outpost_difficulty_follows_the_profiles_current_tier_but_can_be_changed(ui):
    g = ui.g
    pid = g.db.create_profile("Astro", "mid")
    g.db.set_skill(pid, 0.1)
    g.load_profile(pid); g.show_menu(); ui.step(2)
    open_outpost(ui)
    assert ui.o.difficulty == "easy"
    click(ui, "diff:hard")
    assert ui.o.difficulty == "hard"


# ======================================================================= the dashboard: resources and allocation
def test_exactly_three_resource_categories_are_shown_with_oxygen_and_food_inside_life_support(ui):
    start_run(ui)
    rows = section(ui.o, "op_ui_resources", "op_ui_preview")                  # the resource panel, above the preview
    wanted = [i18n.t(k) for k in ("op_power", "op_life_support", "op_oxygen", "op_food", "op_shielding")]
    assert [t for t in rows if t in wanted] == wanted                          # exactly these, in this order
    names = [t for t in rows if not t[0].isdigit()]
    assert names == wanted                                                     # nothing else is drawn as a resource
    block = " ".join(rows)
    assert i18n.t("op_comms") not in block and i18n.t("op_science") not in block      # allocations, not resources
    assert i18n.t("op_crew_health") not in block and i18n.t("op_score") not in block  # status indicators, not resources
    head = ui.o.shown[:ui.o.shown.index(i18n.t("op_ui_resources"))]
    assert i18n.t("op_crew_health") in head and any(t.startswith(i18n.t("op_score")) for t in head)


def test_header_shows_sol_location_difficulty_crew_health_score_and_status(ui):
    start_run(ui, "mars", "hard")
    head = ui.o.shown[:ui.o.shown.index(i18n.t("op_ui_resources"))]
    joined = " | ".join(head)
    assert i18n.t("op_ui_site_mars") in joined and i18n.t("hard") in joined
    assert i18n.t("op_ui_sol", n=1, total=C.DIFFICULTY["hard"]["sols"]) in head
    assert i18n.t("op_crew_health") in head and any(t.startswith(i18n.t("op_score")) for t in head)
    assert i18n.t("op_ui_status_running") in head


def test_four_allocation_rows_show_budget_limits_and_hints(ui):
    start_run(ui)
    o, s = ui.o, ui.o.session
    block = section(o, "op_ui_allocation", "op_ui_forecast_title")
    assert i18n.t("op_ui_available", n=s.available()) in block and i18n.t("op_ui_unspent", n=s.available()) in block
    for cat in C.ALLOCATIONS:
        assert i18n.t("op_" + cat) in block and i18n.t("op_ui_hint_" + cat) in block
        assert i18n.t("op_ui_limit", n=C.ALLOC_LIMIT[cat]) in block
        assert f"plus:{cat}" in o.buttons and f"minus:{cat}" in o.buttons
    assert i18n.t("op_ui_focus") in block


def test_clicking_plus_and_minus_changes_the_plan_within_limits_and_budget(ui):
    start_run(ui)
    o, s = ui.o, ui.o.session
    assert all(o.buttons[f"minus:{c}"].disabled for c in C.ALLOCATIONS)          # nothing to take away yet
    click(ui, "plus:science")
    click(ui, "plus:science")
    assert s.alloc["science"] == 2 and "2" in o.shown and not o.buttons["minus:science"].disabled
    click(ui, "minus:science")
    assert s.alloc["science"] == 1
    for _ in range(C.ALLOC_LIMIT["comms"] + 3):
        click(ui, "plus:comms")
    assert s.alloc["comms"] == C.ALLOC_LIMIT["comms"] and o.buttons["plus:comms"].disabled
    for cat in ("life_support", "shielding", "science"):
        for _ in range(C.ALLOC_LIMIT[cat]):
            click(ui, f"plus:{cat}")
    assert s.unspent() == 0 and all(o.buttons[f"plus:{c}"].disabled for c in C.ALLOCATIONS)
    click(ui, "reset")
    assert s.allocated() == 0


def test_shift_changes_an_allocation_by_five(ui, monkeypatch):
    start_run(ui)
    monkeypatch.setattr(type(ui.o), "_shift", staticmethod(lambda: True))
    click(ui, "plus:life_support")
    assert ui.o.session.alloc["life_support"] == 5


def test_life_support_focus_buttons_choose_oxygen_balanced_or_food(ui):
    start_run(ui)
    click(ui, "focus:1.0")
    assert ui.o.session.focus == 1.0
    click(ui, "focus:0.0")
    assert ui.o.session.focus == 0.0
    click(ui, f"focus:{C.LS_FOCUS_DEFAULT}")
    assert ui.o.session.focus == C.LS_FOCUS_DEFAULT


def test_preview_shows_the_consequences_before_advancing_and_warns(ui):
    start_run(ui)
    o, s = ui.o, ui.o.session
    assert i18n.t("op_ui_preview") in o.shown and i18n.t("op_ui_preview_note") in o.shown
    p = s.preview()
    expect = i18n.t("op_ui_value_delta", name=i18n.t("op_oxygen"), value=str(round(p["next"]["oxygen"])),
                    delta=f"{round(p['delta']['oxygen']):+d}")
    assert expect in o.shown                                                 # numbers follow the current plan
    click(ui, "plus:life_support")
    assert i18n.t("op_ui_value_delta", name=i18n.t("op_oxygen"), value=str(round(s.preview()["next"]["oxygen"])),
                  delta=f"{round(s.preview()['delta']['oxygen']):+d}") in o.shown
    s.state = replace(s.state, oxygen=C.CONSUME["oxygen"])
    s.reset()
    o.redraw()
    assert i18n.t("op_ui_warn_lost_oxygen") in o.shown


def test_advance_plays_the_sol_updates_the_screen_and_saves_the_run(ui):
    start_run(ui)
    o, s = ui.o, ui.o.session
    sound_plan(o)
    rid = s.run_id
    click(ui, "advance")
    assert s.state.sol == 2 and i18n.t("op_ui_sol", n=2, total=10) in o.shown
    row = ui.g.db.get_outpost_run(rid)
    assert row["sol"] == 2 and row["status"] == "running" and row["profile_id"] is None
    assert i18n.t("op_ui_last_sol", n=1) in o.shown
    ui.g.input("enter"); ui.step(2)                                          # the keyboard shortcut advances too
    assert s.state.sol == 3
    ui.g.input("r"); ui.step(2)
    assert s.allocated() == 0


# ======================================================================= events and forecast on screen
def force(ui, **state_changes):
    s = ui.o.session
    s.state = replace(s.state, **state_changes)
    return s


def test_no_forecast_is_shown_without_communications_and_the_event_stays_hidden(ui):
    start_run(ui)
    s = force(ui, comms_level=0)
    s._event = "solar_storm"
    ui.o.redraw()
    shown = " | ".join(ui.o.shown)
    assert i18n.t("op_forecast_off") in ui.o.shown
    assert i18n.t("op_event_solar_storm") not in shown and i18n.t("op_forecast_radiation") not in shown
    assert i18n.t("op_ui_comms_status", state=i18n.t("op_ui_comms_weak")) in ui.o.shown
    assert i18n.t("op_ui_forecast_need", a=C.COMMS_FORECAST_MIN, b=C.COMMS_FORECAST_FULL) in ui.o.shown


def test_basic_communications_show_only_the_category(ui):
    start_run(ui)
    s = force(ui, comms_level=C.COMMS_FORECAST_MIN)
    s._event = "solar_storm"
    ui.o.redraw()
    assert i18n.t("op_forecast_radiation") in ui.o.shown
    shown = " | ".join(ui.o.shown)
    assert i18n.t("op_event_solar_storm") not in shown and i18n.t("op_ui_sev_high") not in shown
    s._event = "dust_storm"
    ui.o.redraw()
    assert i18n.t("op_forecast_weather") in ui.o.shown and i18n.t("op_event_dust_storm") not in " | ".join(ui.o.shown)


def test_strong_communications_show_the_exact_event_and_its_severity(ui):
    start_run(ui)
    s = force(ui, comms_level=C.COMMS_FORECAST_FULL)
    s._event = "solar_storm"
    ui.o.redraw()
    assert i18n.t("op_forecast_exact", event=i18n.t("op_event_solar_storm")) in ui.o.shown
    assert i18n.t("op_ui_severity", level=i18n.t("op_ui_sev_high")) in ui.o.shown
    s._event = None
    ui.o.redraw()
    assert i18n.t("op_ui_forecast_quiet") in ui.o.shown


def test_the_event_that_happened_is_shown_with_severity_messages_and_effects(ui):
    start_run(ui)
    s = force(ui, comms_level=0, shielding=10.0)
    s._event = "solar_storm"
    sound_plan(ui.o)
    click(ui, "advance")
    shown = ui.o.shown
    assert i18n.t("op_ui_last_sol", n=1) in shown and i18n.t("op_event_solar_storm") in shown
    assert i18n.t("op_ui_severity", level=i18n.t("op_ui_sev_high")) in shown
    assert any(t.startswith(i18n.t("op_msg_radiation_leaked", leak=0)[:12]) or "radiation" in t.lower() for t in shown)
    s._event = "dust_storm"
    sound_plan(ui.o)
    click(ui, "advance")
    dust = i18n.t("op_ui_effect_dust", percent=round(C.EVENTS["dust_storm"]["dust_factor"] * 100),
                  sols=C.EVENTS["dust_storm"]["dust_sols"])
    assert dust in ui.o.shown and i18n.t("op_ui_no_effects") not in ui.o.shown
    s._event = "comms_blackout"
    sound_plan(ui.o)
    click(ui, "advance")
    comms = i18n.t("op_ui_effect_comms_down", sols=C.EVENTS["comms_blackout"]["comms_down_sols"])
    assert any(comms in t for t in ui.o.shown)           # active effects share one label (dust may still be active too)
    assert any("radio down" in t for t in ui.o.shown)


def test_quiet_sol_message_and_no_effects_text(ui):
    start_run(ui)
    ui.o.session._event = None
    sound_plan(ui.o)
    click(ui, "advance")
    assert i18n.t("op_ui_no_event") in ui.o.shown and i18n.t("op_ui_no_effects") in ui.o.shown


# ======================================================================= result screens
def lose_quickly(ui):
    start_run(ui, "mars", "hard")
    for _ in range(40):
        if ui.o.screen != "play":
            break
        ui.o.session.reset()
        click(ui, "advance")


def test_failure_shows_the_educational_explanation_and_options(ui):
    lose_quickly(ui)
    o = ui.o
    assert o.screen == "result" and i18n.t("op_ui_result_lost") in o.shown and i18n.t("op_ui_why_failed") in o.shown
    r = o.session.result()
    assert r["failure_text"] in o.shown and len(r["failure_text"]) > 60
    assert i18n.t("op_ui_seed", n=r["seed"]) in o.shown and {"again", "research", "menu"} <= set(o.buttons)
    row = ui.g.db.get_outpost_run(o.session.run_id)
    assert row["status"] == "lost" and row["fail_reason"] and row["seed"] == r["seed"]
    click(ui, "again")
    assert o.screen == "setup"


def test_winning_shows_stars_score_and_is_saved(ui):
    start_run(ui, "moon", "easy")
    o = ui.o
    for _ in range(12):
        if o.screen != "play":
            break
        sound_plan(o)
        click(ui, "advance")
    assert o.screen == "result" and o.session.state.status == O.WON
    r = o.session.result()
    assert i18n.t("op_ui_result_won") in o.shown and i18n.t("op_ui_stars", n=r["stars"]) in o.shown
    assert i18n.t("op_ui_final_score", n=str(round(r["score"]))) in o.shown
    assert ui.g.db.get_outpost_run(o.session.run_id)["status"] == "won"
    click(ui, "again")
    assert ui.g.db.best_outpost_score(None) == r["score"]
    assert i18n.t("op_ui_best", n=str(round(r["score"]))) in o.shown


# ======================================================================= persistence through the UI
def test_leaving_mid_run_offers_resume_and_resume_restores_the_exact_run(ui):
    s = start_run(ui, "mars", "normal")
    for _ in range(3):
        sound_plan(ui.o)
        click(ui, "advance")
    state, seed, rid = s.state, s.seed, s.run_id
    click(ui, "menu")
    assert ui.g.mode == "menu"
    open_outpost(ui)
    assert "resume" in ui.o.buttons and i18n.t("op_ui_resume", n=state.sol) in ui.o.shown
    click(ui, "resume")
    r = ui.o.session
    assert ui.o.screen == "play" and r.run_id == rid and r.seed == seed and r.state == state
    assert (ui.o.site, ui.o.difficulty) == ("mars", "normal")


def test_starting_a_new_run_retires_the_old_unfinished_one(ui):
    first = start_run(ui)
    click(ui, "menu")
    second = start_run(ui)
    db = ui.g.db
    assert db.get_outpost_run(first.run_id)["status"] == "abandoned" and db.get_outpost_run(second.run_id)["status"] == "running"
    assert len(db.list_outpost_runs(None)) == 2


def test_a_run_is_stored_with_the_selected_location_difficulty_and_seed(ui):
    s = start_run(ui, "mars", "hard")
    row = ui.g.db.get_outpost_run(s.run_id)
    assert (row["site"], row["difficulty"], row["seed"]) == ("mars", "hard", s.seed)
    assert row["solar_source"] and row["state_json"] and row["created_at"]


# ======================================================================= NASA data on screen
SOURCES = [(nasa_data.LIVE, "2026-11-09"), (nasa_data.CACHED, "2026-11-01"), (nasa_data.ARCHIVED, "2026-10-20"),
           (nasa_data.DEFAULT, None)]


@pytest.mark.parametrize("source,date", SOURCES)
def test_donki_status_label_level_date_and_honest_note(ui, source, date):
    open_outpost(ui)
    solar = nasa_data.SolarActivity(0.55, source, date)
    ui.o.nasa.solar = solar
    ui.o.redraw()
    shown = ui.o.shown
    assert solar.describe() in shown and i18n.t(solar.level_key) in shown
    assert i18n.t("op_ui_solar_note") in shown                                 # gameplay mapping, not a NASA measurement
    assert ("Not live" in solar.describe()) == (source in (nasa_data.CACHED, nasa_data.ARCHIVED))
    if date:
        assert i18n.t("op_ui_retrieved", date=date) in shown
    else:
        assert not any(t.startswith(i18n.t("op_ui_retrieved", date="")[:10]) for t in shown)
    if source != nasa_data.LIVE:
        assert "Live" not in solar.describe()[:5]


def test_the_run_keeps_the_solar_activity_it_started_with(ui):
    open_outpost(ui)
    ui.o.nasa.solar = nasa_data.SolarActivity(0.9, nasa_data.ARCHIVED, "2026-10-20")
    click(ui, "start")
    s = ui.o.session
    ui.o.nasa.solar = nasa_data.SolarActivity(0.1, nasa_data.LIVE, "2026-11-09")   # a later refresh must not change the run
    ui.o.redraw()
    assert s.solar_level == 0.9 and s.solar_source == nasa_data.ARCHIVED
    assert s.solar().describe() in ui.o.shown and i18n.t("op_ui_solar_short") in ui.o.shown   # short note while playing


def test_setup_screen_shows_the_osdr_card_count_and_source(ui):
    open_outpost(ui)
    n = ui.o.nasa
    assert i18n.t("op_ui_cards_count", n=len(n.studies.entries)) in ui.o.shown and len(n.studies.entries) >= 8
    assert n.studies.describe() in ui.o.shown


def test_research_cards_show_title_setting_topic_explanation_source_and_link(ui):
    open_outpost(ui)
    click(ui, "research")
    o = ui.o
    assert o.screen == "cards"
    cards = o.filtered_cards()
    assert len(cards) >= 8 and i18n.t("op_ui_card_n", n=1, total=len(cards)) in o.shown
    card = cards[0]
    r = card.render()
    for expect in (card.title, r["setting"], r["topic"], r["summary"], r["gameplay_note"], r["disclaimer"],
                   card.source_url, i18n.t("op_osdr_game_label")):
        assert expect in o.shown, expect
    assert card.title in o.shown                                                # NASA's English title, unchanged
    assert {"prev", "next", "open", "back"} <= set(o.buttons)
    assert o.nasa.studies.describe() in o.shown


def test_ground_studies_are_clearly_distinguished_from_spaceflight_studies(ui):
    open_outpost(ui)
    click(ui, "research")
    o = ui.o
    seen = {}
    for _ in range(len(o.filtered_cards())):
        card = o.filtered_cards()[o.card_index]
        seen.setdefault(card.setting, []).append(card)
        assert card.render()["setting"] in o.shown
        assert o.shown.count(card.render()["setting"]) == 1
        click(ui, "next")
    assert {"spaceflight", "ground"} <= set(seen)
    texts = {i18n.t("op_osdr_setting_" + k) for k in ("spaceflight", "ground", "unknown")}
    assert len(texts) == 3
    from astro.game.outpost_ui import SETTING_COLOR
    assert len({tuple(c) for c in SETTING_COLOR.values()}) == 3                 # three different badge colours
    ground = seen["ground"][0].render()
    assert "Earth" in ground["setting"] and "not in space" in ground["summary"]


def test_cards_can_be_filtered_by_topic_and_stepped_through(ui):
    open_outpost(ui)
    click(ui, "research")
    o = ui.o
    total = len(o.filtered_cards())
    click(ui, "filter:plants")
    plants = o.filtered_cards()
    assert 0 < len(plants) < total and all(c.topic == "plants" for c in plants)
    click(ui, "filter:all")
    assert len(o.filtered_cards()) == total
    first = o.filtered_cards()[0].accession
    click(ui, "prev")
    assert o.filtered_cards()[o.card_index].accession == o.filtered_cards()[-1].accession       # wraps around
    click(ui, "next")
    assert o.filtered_cards()[o.card_index].accession == first
    ui.g.input("right arrow"); ui.step(2)
    assert o.card_index == 1
    click(ui, "back")
    assert o.screen == "setup"


def test_open_study_page_uses_only_official_nasa_links(ui):
    open_outpost(ui)
    click(ui, "research")
    card = ui.o.filtered_cards()[0]
    click(ui, "open")
    assert ui.opened == [card.source_url] and card.source_url.startswith("https://osdr.nasa.gov/bio/repo/data/studies/OSD-")
    ui.o.open_study(replace(card, source_url="https://evil.example/phish"))
    ui.o.open_study(replace(card, source_url="javascript:alert(1)"))
    assert ui.opened == [card.source_url]                                     # anything else is refused


def test_empty_research_results_show_the_empty_message(ui):
    open_outpost(ui)
    ui.o.nasa.studies = osdr_data.StudySet([], osdr_data.NONE)
    click(ui, "research")
    assert i18n.t("op_osdr_empty") in ui.o.shown and "open" not in ui.o.buttons
    assert ui.o.nasa.studies.describe() in ui.o.shown


# ======================================================================= offline start, background loading, errors
def test_the_game_is_fully_playable_with_no_internet(ui):
    ui.net.mode = "fail"
    open_outpost(ui)
    o = ui.o
    assert o.nasa.solar.source in (nasa_data.ARCHIVED, nasa_data.CACHED, nasa_data.DEFAULT) and not o.nasa.solar.is_live
    assert len(o.nasa.studies.entries) >= 8 and o.nasa.studies.source in (osdr_data.OFFLINE, osdr_data.CACHED)
    assert i18n.t("op_ui_nasa_unreachable") in o.shown
    click(ui, "start")
    for _ in range(3):
        sound_plan(o)
        click(ui, "advance")
    click(ui, "research")
    assert len(o.filtered_cards()) >= 8 and o.screen == "cards"
    assert not any("Live" in t[:5] for t in o.shown if "NASA" in t)


def test_background_loading_keeps_the_game_responsive_and_applies_results_on_the_main_thread(ui):
    from astro.game.outpost_ui import OutpostUI
    gate = threading.Event()
    ui.net.gate = gate
    g = ui.g
    g.outpost = OutpostUI(g, loader=BackgroundLoader(), opener=ui.opened.append)
    g.show_menu(); ui.step(2)
    ui.o = g.outpost
    t0 = time.time()
    open_outpost(ui)
    assert time.time() - t0 < 2.0                                              # opening did not wait for the workers
    o = ui.o
    assert o.nasa.loading and i18n.t("op_ui_nasa_loading") in o.shown and o.buttons["refresh"].disabled
    before_solar = o.nasa.solar
    for _ in range(8):
        ui.step(2)                                                             # frames keep running while loading
    assert o.nasa.loading and o.nasa.solar is before_solar
    click(ui, "start")                                                         # and the game can already be played
    assert o.screen == "play" and o.session.solar_source == before_solar.source
    click(ui, "menu")
    open_outpost(ui)
    gate.set()
    for _ in range(150):
        ui.step(1)
        time.sleep(0.02)
        if not o.nasa.loading:
            break
    assert not o.nasa.loading and o.nasa.solar.is_live and o.nasa.solar.level == 0.77
    assert i18n.t("op_ui_nasa_done") in o.shown and i18n.t(o.nasa.solar.level_key) in o.shown
    workers = {t for _, t in ui.net.calls}
    assert workers and all(t is not MAIN_THREAD for t in workers)               # work ran off the main thread


def test_refresh_while_a_refresh_is_running_is_ignored(ui):
    from astro.game.outpost_ui import OutpostUI
    gate = threading.Event()
    ui.net.gate = gate
    g = ui.g
    g.outpost = OutpostUI(g, loader=BackgroundLoader(), opener=ui.opened.append)
    g.show_menu(); ui.step(2)
    ui.o = g.outpost
    open_outpost(ui)
    for _ in range(5):
        ui.o.refresh_nasa()
    gate.set()
    for _ in range(150):
        ui.step(1)
        time.sleep(0.02)
        if not ui.o.nasa.loading:
            break
    assert sorted(n for n, _ in ui.net.calls) == ["donki", "osdr"]               # one lookup each, not five


def test_a_worker_error_shows_a_message_and_does_not_crash_the_game(ui):
    from astro.game.outpost_ui import OutpostUI
    ui.net.mode = "raise"
    g = ui.g
    g.outpost = OutpostUI(g, loader=BackgroundLoader(), opener=ui.opened.append)
    g.show_menu(); ui.step(2)
    ui.o = g.outpost
    open_outpost(ui)
    for _ in range(150):
        ui.step(1)
        time.sleep(0.02)
        if not ui.o.nasa.loading:
            break
    o = ui.o
    assert o.nasa.state == {"donki": "error", "osdr": "error"} and i18n.t("op_ui_nasa_failed") in o.shown
    assert o.nasa.solar is not None and len(o.nasa.studies.entries) >= 8       # saved data kept
    assert not o.buttons["refresh"].disabled                                    # and the player can try again
    click(ui, "start")
    assert o.screen == "play"


def snapshot(o):
    return {"buttons": dict(o.buttons), "shown": list(o.shown), "dyn": list(o.dyn), "screen": o.screen}


def same_screen(o, snap):
    return (o.buttons == snap["buttons"] and o.shown == snap["shown"] and o.dyn == snap["dyn"]
            and o.screen == snap["screen"] and all(not b.is_empty() for b in o.buttons.values())
            and all(not e.is_empty() for e in o.dyn))


def break_drawing(o, monkeypatch, times=None, partial=True):
    """Make ``o.draw`` fail (the first ``times`` calls, or always) after building a widget, like a real mid-draw bug."""
    real, calls = o.draw, {"n": 0}

    def faulty_draw():
        calls["n"] += 1
        if times is None or calls["n"] <= times:
            if partial:
                o.lab("PARTIAL WIDGET", (0, 0), 0.8)                              # built before the bug hits
            raise RuntimeError("injected drawing bug")
        real()
    monkeypatch.setattr(o, "draw", faulty_draw)
    return calls


def test_a_one_off_redraw_failure_keeps_the_previous_screen_intact_and_tells_the_player(ui, monkeypatch, caplog):
    open_outpost(ui)
    o = ui.o
    snap, shown_before = snapshot(o), len(o.shown)
    ui.step(2)
    calls = break_drawing(o, monkeypatch, times=1)
    assert o.redraw() is False                                                # reported, not hidden
    ui.step(2)
    assert same_screen(o, snap), "a failed redraw must restore the previous screen exactly (same widgets)"
    assert "PARTIAL WIDGET" not in o.shown and len(o.shown) == shown_before    # nothing half-built is left behind
    assert o.layout_problems() == []                                           # and the restored screen is still clean
    errors = o.errors
    assert len(errors) == 1 and errors[0]["type"] == "RuntimeError" and "injected drawing bug" in errors[0]["message"]
    assert "faulty_draw" in errors[0]["traceback"] and "outpost_ui.py" in errors[0]["traceback"]   # a useful traceback
    records = [r for r in caplog.records if r.name == "astro.outpost_ui" and r.levelname == "ERROR"]
    assert len(records) == 1 and records[0].exc_info and "injected drawing bug" in caplog.text
    assert o.overlay_text and i18n.t("op_ui_error_notice") in o.overlay_text and i18n.t("op_ui_dismiss") in o.overlay_text
    assert ui.g.mode == "outpost" and o.active                                 # NOT sent back to the menu
    click(ui, "start")                                                         # the restored screen is fully usable
    assert o.screen == "play"
    assert o.overlay == []                                                     # moving on removes the notice
    o.consume_errors()


def test_the_notice_can_be_dismissed_and_the_next_redraw_recovers(ui, monkeypatch):
    open_outpost(ui)
    o = ui.o
    o.redraw()
    break_drawing(o, monkeypatch, times=1)
    o.redraw()
    assert o.overlay
    notice = list(o.overlay)
    o.overlay[3].on_click()                                                    # the OK button
    ui.step(3)
    assert o.overlay == [] and o.overlay_text == []
    assert all(e.is_empty() for e in notice)                                   # the notice's widgets are really destroyed
    assert o.redraw() is True and not o.degraded and "start" in o.buttons       # the second attempt simply works
    o.consume_errors()


def test_a_recurring_failure_pauses_automatic_redraws_but_stays_visible_and_playable(ui, monkeypatch, caplog):
    from astro.game import outpost_ui
    open_outpost(ui)
    o = ui.o
    snap = snapshot(o)
    calls = break_drawing(o, monkeypatch, times=None)
    for _ in range(8):                                                         # eight background results arrive
        o.nasa.state["donki"] = "loading"
        o.loader.start("donki", lambda: o.nasa.solar)
        o.update()
    assert calls["n"] == outpost_ui.ERROR_STREAK                               # retried 3 times, then paused: no 8-frame flicker loop
    assert o.degraded and len(o.errors) == outpost_ui.ERROR_STREAK
    assert all(e["type"] == "RuntimeError" for e in o.errors) and o.errors[-1]["degraded"] is True
    assert len([r for r in caplog.records if r.levelname == "ERROR" and r.exc_info]) == outpost_ui.ERROR_STREAK
    assert same_screen(o, snap)                                                # still the last good screen
    assert i18n.t("op_ui_error_repeated") in o.overlay_text                    # the player is told it is recurring
    assert ui.g.mode == "outpost" and o.active                                 # never silently sent to the menu
    click(ui, "site:mars")                                                     # ... and can keep using the buttons
    assert o.site == "mars" or o.errors                                        # (a click redraws; it is allowed to fail visibly)
    o.consume_errors()
    monkeypatch.undo()
    o.go("setup")                                                              # the player navigates: everything recovers
    assert not o.degraded and o.overlay == [] and "start" in o.buttons


def test_a_failure_when_changing_screens_shows_an_explicit_error_screen_never_the_menu(ui, monkeypatch, caplog):
    open_outpost(ui)
    o = ui.o
    monkeypatch.setattr(o, "draw_cards", lambda: (_ for _ in ()).throw(RuntimeError("cards screen bug")))
    click(ui, "research")                                                      # go("cards") fails
    assert o.screen == "error" and ui.g.mode == "outpost" and o.active
    assert set(o.buttons) == {"retry", "menu"}                                 # a consistent, known-good screen
    assert i18n.t("op_ui_error_title") in o.shown and i18n.t("op_ui_error_screen") in o.shown
    assert o.layout_problems() == []
    assert len(o.errors) == 1 and "cards" in o.errors[0]["context"] and "cards screen bug" in o.errors[0]["traceback"]
    assert any(r.exc_info and "cards screen bug" in caplog.text for r in caplog.records)
    click(ui, "retry")                                                         # still broken: reported again, still consistent
    assert o.screen == "error" and len(o.errors) == 2 and set(o.buttons) == {"retry", "menu"}
    monkeypatch.undo()
    click(ui, "retry")                                                         # fixed: Try again really returns to the screen
    assert o.screen == "cards" and "next" in o.buttons and not o.degraded
    o.consume_errors()
    monkeypatch.setattr(o, "draw_cards", lambda: (_ for _ in ()).throw(RuntimeError("again")))
    click(ui, "back")
    click(ui, "research")
    assert o.screen == "error"
    click(ui, "menu")                                                          # leaving is the player's explicit choice
    assert ui.g.mode == "menu" and not o.active
    o.consume_errors()


def test_the_error_screen_works_in_arabic_and_is_clean(ui, monkeypatch):
    ui.g.set_language("ar")
    ui.step(2)
    open_outpost(ui)
    o = ui.o
    monkeypatch.setattr(o, "draw_cards", lambda: (_ for _ in ()).throw(RuntimeError("bug")))
    click(ui, "research")
    assert o.screen == "error" and i18n.t("op_ui_error_screen", "ar") in o.shown and i18n.has_arabic(o.shown[0])
    assert o.layout_problems() == []
    o.consume_errors()


def test_a_data_layer_error_is_reported_and_leaves_the_screen_untouched(ui, monkeypatch):
    open_outpost(ui)
    o = ui.o
    snap = snapshot(o)
    monkeypatch.setattr(o.nasa, "pump", lambda: (_ for _ in ()).throw(ValueError("bad result shape")))
    o.update()
    assert same_screen(o, snap) and ui.g.mode == "outpost" and o.active
    assert len(o.errors) == 1 and "applying NASA results" in o.errors[0]["context"] and "bad result shape" in o.errors[0]["traceback"]
    o.consume_errors()


def test_an_unexpected_ui_error_fails_the_test_that_caused_it_unless_it_was_acknowledged(ui, monkeypatch):
    """The fixture's teardown check: errors cannot pass unnoticed. Here the test acknowledges the one it provoked."""
    from astro.game import outpost_ui
    open_outpost(ui)
    break_drawing(ui.o, monkeypatch, times=1)
    ui.o.redraw()
    assert len(outpost_ui.ERRORS) == 1                                        # recorded globally too
    assert len(ui.o.consume_errors()) == 1 and outpost_ui.ERRORS == []         # acknowledged: the teardown stays green


def test_the_old_symptom_cannot_come_from_a_half_built_screen_any_more(ui, monkeypatch):
    """The original KeyError('start') looked like a half-built setup screen. After any failed draw the screen is either
    the previous complete one or the explicit error screen, so buttons['start'] is never missing on the setup screen."""
    open_outpost(ui)
    o = ui.o
    for times in (1, 2):
        break_drawing(o, monkeypatch, times=times)
        o.redraw()
        assert o.screen == "setup" and "start" in o.buttons                    # restored, complete
        o.consume_errors()
        monkeypatch.undo()
    monkeypatch.setattr(o, "draw_setup", lambda: (_ for _ in ()).throw(RuntimeError("setup bug")))
    o.go("setup")
    assert o.screen == "error" and "start" not in o.buttons and {"retry", "menu"} == set(o.buttons)
    o.consume_errors()


# ======================================================================= Arabic: shaping, fonts, layout
def test_arabic_text_is_shaped_exactly_once_and_titles_stay_in_english(ui):
    from ursina import Text
    ui.g.set_language("ar")
    ui.step(2)
    open_outpost(ui)
    o = ui.o
    texts = [e for e in o.dyn if isinstance(e, Text)]
    title = i18n.t("op_ui_title", "ar")
    assert any(e.text == i18n.shape(title) for e in texts) and i18n.shape(title) != title
    for key in ("op_ui_location", "op_ui_difficulty", "op_ui_nasa", "op_ui_donki_title"):
        logical = i18n.t(key, "ar")
        assert any(e.text == i18n.shape(logical) for e in texts), key             # one shaping pass, no more
    btn = o.buttons["start"]
    assert btn.text == i18n.shape(i18n.t("op_ui_start", "ar"))
    click(ui, "research")
    card = o.filtered_cards()[0]
    ent = [e for e in o.dyn if isinstance(e, Text) and id(e) in o._sidx and o.shown[o._sidx[id(e)]] == card.title
           and e.text == i18n.wrap(card.title, o._wraps[id(e)])]                                # wrapped, never shaped
    assert ent, "NASA's English title must be drawn unchanged (never shaped or translated)"
    assert not i18n.has_arabic(card.title) and card.render("ar")["topic"] != card.render("en")["topic"]


def test_arabic_play_screen_mirrors_the_layout_and_keeps_everything_visible(ui):
    ui.g.set_language("ar")
    ui.step(2)
    start_run(ui)
    o = ui.o
    assert ui.g.rtl and {"advance", "reset", "menu", "research"} <= set(o.buttons)
    xs = [round(e.x, 3) for e in (o.buttons["menu"], o.buttons["research"])]
    assert xs[0] > 0 > xs[1]                                                    # mirrored: menu on the right in Arabic
    for b in o.buttons.values():
        assert abs(b.x) < 0.89 and abs(b.y) < 0.5                               # inside the screen
    assert i18n.t("op_ui_advance", "ar") in o.shown and i18n.t("op_power", "ar") in o.shown
    for cat in C.ALLOCATIONS:
        assert i18n.t("op_" + cat, "ar") in o.shown


def test_every_string_the_outpost_screens_can_show_is_covered_by_the_fonts(ui):
    """The suite's glyph test covers i18n.STRINGS; this checks the text actually drawn, in both languages."""
    from fontTools.ttLib import TTFont
    ok = {}
    for f in ("Cairo-Bold.ttf", "Cairo-Black.ttf", "Rajdhani-Bold.ttf", "Orbitron-Bold.ttf"):
        ok[f] = set(TTFont(str(config.ASSETS_DIR / "fonts" / f)).getBestCmap())
    for lang in ("en", "ar"):
        ui.g.set_language(lang)
        ui.step(2)
        start_run(ui)
        for screen in ("play",):
            for text in ui.o.shown:
                font = i18n.font("body", text=text)
                missing = {ch for ch in i18n.shape(text) if ch not in "\n " and ord(ch) not in ok[font]}
                assert not missing, (lang, text, missing)
        click(ui, "menu")


# ======================================================================= layout, readability and clickability
def hit_entity(env, x, y):
    """The entity Ursina's own mouse picking would hover/click at (x, y): same collision ray, same resolution."""
    from ursina import camera, mouse, scene, window
    mouse._pickerNP.reparent_to(scene.ui_camera)
    mouse._pickerRay.set_from_lens(camera._ui_lens_node, x * 2 / window.aspect_ratio, y * 2)
    mouse._picker.traverse(camera.ui)
    mouse._pq.sortEntries()
    found = None
    for entry in mouse._pq.getEntries():
        for e in scene.entities:
            if entry.getIntoNodePath().parent == e and e.collision:
                found = e
                break
        if found is not None:
            break
    mouse._pickerNP.reparent_to(camera)
    return found


def stage(env, name):
    """Put the Outpost UI in one of the screen states below and return it."""
    o = env.o
    if name == "setup":
        open_outpost(env)
    elif name == "setup_resume_best":
        start_run(env)
        sound_plan(o)
        click(env, "advance")
        click(env, "menu")
        env.g.db.update_outpost_run(env.g.db.create_outpost_run(None, "moon", "easy", 1, 0.3, "default", None, "{}"),
                                    status="won", sol=8, score=321.0, stars=2, fail_reason=None, state_json="{}",
                                    history_json="[]")
        open_outpost(env)
    elif name in ("play_exact_forecast", "play_no_forecast", "play_hint"):
        start_run(env)
        s = o.session
        s._event = "dust_storm"
        sound_plan(o)
        click(env, "advance")                                   # a past event + active effects on screen
        level = {"play_exact_forecast": C.COMMS_FORECAST_FULL, "play_no_forecast": 0, "play_hint": C.COMMS_FORECAST_MIN}[name]
        s.state = replace(s.state, comms_level=level, oxygen=14.0, shielding=22.0)
        s._event = "solar_storm"
        s.reset()
        for cat, v in (("life_support", 3), ("shielding", 2), ("comms", 5), ("science", 2)):
            s.adjust(cat, v)
        o.redraw()
    elif name in ("result_lost", "result_won"):
        start_run(env, "mars" if name == "result_lost" else "moon", "hard" if name == "result_lost" else "easy")
        for _ in range(40):
            if o.screen != "play":
                break
            if name == "result_won":
                sound_plan(o)
            else:
                o.session.reset()
            click(env, "advance")
    elif name in ("cards_spaceflight", "cards_ground"):
        open_outpost(env)
        click(env, "research")
        want = name.split("_")[1]
        for _ in range(len(o.filtered_cards())):
            if o.filtered_cards()[o.card_index].setting == want:
                break
            click(env, "next")
    return o


LAYOUT_STATES = ["setup", "setup_resume_best", "play_exact_forecast", "play_no_forecast", "play_hint", "result_lost",
                 "result_won", "cards_spaceflight", "cards_ground"]


@pytest.mark.parametrize("lang", ["en", "ar"])
@pytest.mark.parametrize("state", LAYOUT_STATES)
def test_no_overflow_overlap_or_top_bar_collision_on_any_screen_in_either_language(ui, lang, state):
    ui.g.set_language(lang)
    ui.step(2)
    o = stage(ui, state)
    assert o.layout_problems() == [], o.layout_problems()
    assert len(o.rects) > 5


@pytest.mark.parametrize("lang", ["en", "ar"])
@pytest.mark.parametrize("state", LAYOUT_STATES)
def test_every_enabled_button_is_visible_and_a_real_mouse_ray_hits_it(ui, lang, state):
    ui.g.set_language(lang)
    ui.step(2)
    o = stage(ui, state)
    ui.step(2)
    assert o.buttons
    for key, b in o.buttons.items():
        assert b.enabled and b.visible and b.collision and callable(b.on_click), key
        assert abs(b.x) + b.scale_x / 2 <= 0.889 + 0.003 and abs(b.y) + b.scale_y / 2 <= 0.5 + 0.003, f"{key} is off screen"
        if b.disabled:
            continue
        for fx, fy in ((0, 0), (-0.35, 0), (0.35, 0), (0, -0.3), (0, 0.3)):                 # centre and four inner points
            hit = hit_entity(ui, b.x + fx * b.scale_x, b.y + fy * b.scale_y)
            assert hit is b, f"{key}: clicking at {(fx, fy)} would hit {getattr(hit, 'text', hit)!r}"


def test_the_research_back_button_is_clear_of_the_top_bar_and_clickable(ui):
    for lang in ("en", "ar"):
        ui.g.set_language(lang)
        ui.step(2)
        o = stage(ui, "cards_spaceflight")
        back = o.buttons["back"]
        assert back.y < 0 and not [r for r in o.topbar_rects() if r.overlaps(next(x for x in o.rects if x.name == "back"))]
        assert hit_entity(ui, back.x, back.y) is back
        click(ui, "back")
        assert o.screen == "setup"                                   # it really leaves the cards screen
        click(ui, "menu")


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_the_disclaimer_has_padding_inside_its_box_and_nothing_crosses_a_border(ui, lang):
    ui.g.set_language(lang)
    ui.step(2)
    o = stage(ui, "cards_ground")
    box = next(r for r in o.rects if r.kind == "panel" and r.name == "card-note")
    card = o.filtered_cards()[o.card_index].render()
    disclaimer = next(r for r in o.rects if r.kind == "text" and r.name == card["disclaimer"])
    note = next(r for r in o.rects if r.kind == "text" and r.name == card["gameplay_note"])
    for r in (disclaimer, note):
        assert r.x0 - box.x0 >= 0.02 and box.x1 - r.x1 >= 0.02 and box.y1 - r.y1 >= 0.015, "text touches the box edge"
    assert disclaimer.y0 - box.y0 >= 0.012                           # padding under the last line as well
    status = next(r for r in o.rects if r.kind == "text" and r.name == o.nasa.studies.describe())
    panel = next(r for r in o.rects if r.kind == "panel" and r.name == "card")
    assert status.y0 >= panel.y1 - 0.003, "the status line must sit ABOVE the card, not on its border"


@pytest.mark.parametrize("lang", ["en", "ar"])
def test_setup_buttons_best_score_and_refresh_stay_inside_their_panels_with_margin(ui, lang):
    ui.g.set_language(lang)
    ui.step(2)
    o = stage(ui, "setup_resume_best")
    panels = {r.name: r for r in o.rects if r.kind == "panel"}
    buttons = {r.name: r for r in o.rects if r.kind == "button"}
    for key in ("site:moon", "site:mars", "diff:easy", "diff:normal", "diff:hard", "start", "resume", "research"):
        r, p = buttons[key], panels["choices"]
        assert r.x0 - p.x0 >= 0.02 and p.x1 - r.x1 >= 0.02 and r.y0 - p.y0 >= 0.015 and p.y1 - r.y1 >= 0.01, key
    r, p = buttons["refresh"], panels["nasa"]
    assert r.x0 - p.x0 >= 0.02 and p.x1 - r.x1 >= 0.02 and r.y0 - p.y0 >= 0.015, "refresh must not cross the panel edge"
    best = next(x for x in o.rects if x.kind == "text" and x.name.startswith(i18n.t("op_ui_best", n="")[:6]))
    assert best.inside(panels["choices"]) and best.y0 - panels["choices"].y0 >= 0.01


def test_the_game_mapping_note_stays_inside_its_panel_and_clear_of_every_button(ui):
    for lang in ("en", "ar"):
        ui.g.set_language(lang)
        ui.step(2)
        o = stage(ui, "play_exact_forecast")
        short = next(r for r in o.rects if r.kind == "text" and r.name == i18n.t("op_ui_solar_short"))
        events = next(r for r in o.rects if r.kind == "panel" and r.name == "events")
        assert short.inside(events) and short.y0 - events.y0 >= 0.01
        assert not [b for b in o.rects if b.kind == "button" and b.overlaps(short)]
        research = next(b for b in o.rects if b.kind == "button" and b.name == "research")
        assert research.y1 <= events.y0 - 0.01, "bottom buttons must sit below every panel"
        click(ui, "menu")


def test_small_text_is_big_enough_for_young_players(ui):
    from ursina import Text
    from astro.game import outpost_ui
    assert outpost_ui.SC_MIN >= 0.75                                  # it was 0.38 for hints, limits and notes
    for lang in ("en", "ar"):
        ui.g.set_language(lang)
        ui.step(2)
        for state in ("setup", "play_exact_forecast", "cards_ground", "result_lost"):
            o = stage(ui, state)
            sizes = [e.scale_x for e in o.dyn if isinstance(e, Text) and e.text.strip()]
            assert sizes and min(sizes) >= outpost_ui.SC_MIN - 1e-6, (lang, state, min(sizes))
            o.leave()                                                  # back to the main menu between screens
            ui.step(1)
    ui.g.set_language("en")
    ui.step(2)
    o = stage(ui, "play_exact_forecast")
    wanted = (i18n.t("op_ui_hint_science"), i18n.t("op_ui_limit", n=14), i18n.t("op_ui_help"), i18n.t("op_ui_preview_note"))
    by_text = {o.shown[o._sidx[id(e)]]: e.scale_x for e in o.dyn if isinstance(e, Text) and id(e) in o._sidx}
    for text in wanted:                                               # the hint, limit, key-help and preview texts
        assert by_text[text] >= 0.75, (text, by_text[text])


def test_wrapped_text_stays_inside_the_panel_even_with_the_longest_strings(ui, monkeypatch):
    """Stress: a very long hint must wrap to its column (not shrink or overflow) in both languages."""
    long_en = "A very long explanation that must be wrapped onto several lines instead of running out of its panel. " * 2
    for lang in ("en", "ar"):
        ui.g.set_language(lang)
        ui.step(2)
        monkeypatch.setitem(i18n.STRINGS[lang], "op_ui_hint_science", long_en if lang == "en" else "\u0634\u0631\u062d \u0637\u0648\u064a\u0644 \u062c\u062f\u0627 " * 14)
        o = stage(ui, "play_exact_forecast")
        science = next(r for r in o.rects if r.kind == "text" and r.name == i18n.t("op_ui_hint_science"))
        assert science.x1 - science.x0 <= 0.43, "the long hint was not wrapped to its column"
        click(ui, "menu")


# ======================================================================= the smoke script exists and the hook is minimal
def test_app_changes_are_minimal_and_isolated_to_the_outpost_mode():
    src = (ROOT / "astro" / "game" / "app.py").read_text(encoding="utf-8")
    assert src.count('self.mode == "outpost"') == 2 and "OutpostUI(self)" in src
    assert "outpost_flow" not in src and "nasa_data" not in src and "osdr_data" not in src
    ui_src = (ROOT / "astro" / "game" / "outpost_ui.py").read_text(encoding="utf-8")
    assert "requests" not in ui_src and "urllib" not in ui_src and "socket" not in ui_src   # no network in the UI module


def test_leaving_outpost_while_jobs_run_then_returning_applies_results_once_and_only_while_active(ui):
    """Leave with DONKI/OSDR still running, re-enter, finish: no duplicate jobs, nothing drawn while the player is on
    the main menu, results applied on the main thread (update()), and the screen shows them afterwards."""
    from astro.game.outpost_ui import OutpostUI
    gate = threading.Event()
    ui.net.gate = gate
    g = ui.g
    g.outpost = OutpostUI(g, loader=BackgroundLoader(), opener=ui.opened.append)
    g.show_menu(); ui.step(2)
    ui.o = o = g.outpost
    open_outpost(ui)
    assert o.nasa.loading
    before = o.nasa.solar
    o.leave(); ui.step(2)                                                     # leave while both jobs are running
    assert not o.active and o.nasa.loading
    gate.set()
    assert wait_until_idle(o.nasa.loader)                                      # workers finish while on the main menu
    for _ in range(5):
        ui.step(1)
        o.update()                                                            # inactive: must apply and draw nothing
    assert o.nasa.solar is before and not o.dyn and o.nasa.state["donki"] == "loading"
    open_outpost(ui)                                                          # re-enter: leftover results are applied
    for _ in range(10):
        ui.step(1)
    assert o.nasa.solar.is_live and o.nasa.solar.level == 0.77 and not o.nasa.loading
    donki_calls = [n for n, _ in ui.net.calls if n == "donki"]
    assert len(donki_calls) <= 2                                              # leftover job + at most one fresh refresh
    assert i18n.t(o.nasa.solar.level_key) in o.shown
    assert all(t is not MAIN_THREAD for _, t in ui.net.calls)


def wait_until_idle(loader, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if not loader.is_loading():
            return True
        time.sleep(0.01)
    return False



def test_whole_journey_menu_setup_play_save_resume_result_and_replay(ui):
    """Phase 7 end-to-end: main menu -> setup -> play -> leave (auto-saved) -> resume -> finish -> result -> play again."""
    db = ui.g.db
    assert ui.g.mode == "menu"
    open_outpost(ui)
    assert ui.o.screen == "setup" and "resume" not in ui.o.buttons                      # nothing saved yet
    first = start_run_from_setup(ui, "mars", "easy")
    assert ui.o.screen == "play" and db.get_outpost_run(first.run_id)["status"] == "running"
    for _ in range(3):
        sound_plan(ui.o)
        click(ui, "advance")
    saved = db.get_outpost_run(first.run_id)
    assert saved["sol"] == 4 and saved["status"] == "running"                           # saved after every sol
    click(ui, "menu")                                                                   # leave mid-run
    assert ui.g.mode == "menu"
    open_outpost(ui)
    click(ui, "resume")
    o = ui.o
    resumed = o.session
    assert resumed.run_id == first.run_id and resumed.state.sol == 4 and o.screen == "play"
    guard = 0
    while resumed.running and guard < 30:                                               # play the rest of the mission
        sound_plan(o)
        click(ui, "advance")
        guard += 1
    assert o.screen == "result" and not resumed.running
    row = db.get_outpost_run(first.run_id)
    assert row["status"] in ("won", "lost") and row["status"] == resumed.state.status
    assert row["score"] == resumed.state.score and row["sol"] >= 8
    assert i18n.t("op_ui_result_won" if row["status"] == "won" else "op_ui_result_lost") in o.shown
    assert i18n.t("op_ui_seed", n=first.seed) in o.shown
    assert {"again", "research", "menu"} <= set(o.buttons)
    click(ui, "again")                                                                  # replay: back to setup, no resume offer
    assert o.screen == "setup" and "resume" not in o.buttons
    second = start_run_from_setup(ui, "moon", "normal")
    assert second.run_id != first.run_id and second.seed != first.seed and o.screen == "play"
    assert db.get_outpost_run(first.run_id)["status"] == row["status"]                  # the finished run is untouched
    assert db.get_outpost_run(second.run_id)["status"] == "running"
    assert [r["status"] for r in db.list_outpost_runs(None)].count("running") == 1       # only one unfinished run


def start_run_from_setup(env, site, difficulty):
    click(env, f"site:{site}")
    click(env, f"diff:{difficulty}")
    click(env, "start")
    return env.o.session


# ======================================================================= NASA data: when it happened / retrieved / checked
def test_setup_shows_retrieval_time_newest_event_and_last_check_separately_in_both_languages(ui):
    import datetime as dt
    from astro import fileio
    open_outpost(ui)
    o = ui.o
    for lang in ("en", "ar"):
        ui.g.set_language(lang)
        o.nasa.solar = nasa_data.SolarActivity(0.55, nasa_data.CACHED, "2026-11-09", ("2026-10-10", "2026-11-09"), {"cme": 3},
                                               "2026-11-09T12:00:00+02:00", "2026-10-03T09:12Z")
        o.nasa.checked_at["donki"] = "2026-11-13T18:30:00+02:00"
        o.redraw()
        shown = o.shown
        retrieved = fileio.local_text("2026-11-09T12:00:00+02:00")
        assert i18n.t("op_ui_retrieved", date=retrieved) in shown                       # when we got it (local time)
        assert i18n.t("op_ui_latest_event", date="2026-10-03") in shown                 # when it happened, NASA's date
        assert i18n.t("op_ui_latest_event_note") in shown                               # why it can be old
        assert i18n.t("op_ui_checked", when=fileio.local_text("2026-11-13T18:30:00+02:00")) in shown
        assert o.nasa.solar.describe() in shown and "Live" not in o.nasa.solar.describe("en")[:5]
        assert o.layout_problems() == [], o.layout_problems()
    ui.g.set_language("en")


def test_no_event_note_is_shown_when_the_newest_event_is_today_and_none_is_invented_when_there_are_no_events(ui):
    import datetime as dt
    open_outpost(ui)
    o = ui.o
    today = dt.date.today().isoformat()
    o.nasa.solar = nasa_data.SolarActivity(0.9, nasa_data.LIVE, today, None, {"cme": 2}, None, today + "T01:00Z")
    o.redraw()
    assert i18n.t("op_ui_latest_event", date=today) in o.shown and i18n.t("op_ui_latest_event_note") not in o.shown
    o.nasa.solar = nasa_data.SolarActivity(0.0, nasa_data.LIVE, today, None, {k: 0 for k in nasa_data.COUNT_KEYS})
    o.redraw()
    assert i18n.t("op_ui_no_events") in o.shown and not any(t.startswith("Newest NASA event") for t in o.shown)
    o.nasa.solar = nasa_data.SolarActivity(0.3, nasa_data.DEFAULT)                      # no NASA data: no NASA dates at all
    o.redraw()
    assert not any(t.startswith(("Newest NASA event", "Retrieved")) for t in o.shown)
    assert o.layout_problems() == []


def test_the_refresh_button_forces_a_real_request_but_opening_does_not(ui, monkeypatch):
    calls = []
    real = nasa_data.get_solar_activity
    monkeypatch.setattr(nasa_data, "get_solar_activity",
                        lambda **kw: (calls.append(kw), real(**{**kw, "allow_network": False}))[1])
    from astro.outpost_flow import BackgroundLoader as BL
    ui.g.outpost.loader = BL(inline=True)
    open_outpost(ui)
    ui.step(2)
    assert [kw.get("force") for kw in calls if kw.get("allow_network", True)] == [False]       # opening: cache allowed
    click(ui, "refresh")
    ui.step(2)
    assert [kw.get("force") for kw in calls if kw.get("allow_network", True)] == [False, True]  # the button: always ask
    assert ui.o.nasa.checked_at["donki"] and ui.o.nasa.checked_at["osdr"]
