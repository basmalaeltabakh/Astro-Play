"""Smoke test of Outpost Command inside the REAL Ursina game (needs a display, like scripts/smoke_test.py).

    python scripts/smoke_outpost.py            # NASA endpoints pointed at closed local ports: exercises the genuine
                                               # offline / failure path, so the result never depends on the network
    python scripts/smoke_outpost.py --live     # use the real NASA services (a failed lookup is reported, not fatal)

Plays: main menu -> Outpost Command -> setup -> background NASA refresh -> a full mission (win or lose) -> result ->
research cards -> back to the main menu -> existing profile / galaxy map / briefing screens, in English and Arabic.
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ursina import Text, Ursina  # noqa: E402

from astro import config, i18n  # noqa: E402

LIVE = "--live" in sys.argv
if not LIVE:                                    # connection refused at once: the real error handling, no waiting
    config.DONKI_BASE_URL = "http://127.0.0.1:9/DONKI-API/get"
    config.OSDR_BASE_URL = "http://127.0.0.1:9/biodata/api"

from astro.assistant import SpaceAssistant  # noqa: E402
from astro.db import Database  # noqa: E402
from astro.game.app import Game  # noqa: E402
from astro.settings import Settings  # noqa: E402

Text.default_resolution = 1080 * Text.size
app = Ursina(title="Astro Play outpost smoke", borderless=False, development_mode=False, size=(1280, 720))
tmp = Path(tempfile.mkdtemp())
config.SETTINGS_PATH = tmp / "settings.json"
config.DONKI_CACHE_PATH, config.OSDR_CACHE_PATH = tmp / "donki_cache.json", tmp / "osdr_cache.json"
db = Database(tmp / "smoke.db")
game = Game(db, SpaceAssistant(use_chroma=False), Settings.load(tmp / "settings.json"))


def step(n=3):
    for _ in range(n):
        app.step()


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


def menu_button(key):
    return next(e for e in game.ui if hasattr(e, "on_click") and getattr(e, "text_entity", None) is not None
                and e.text == i18n.shape(i18n.t(key)))


def click(key):
    game.outpost.buttons[key].on_click()
    step(2)


def wait_for_nasa(limit=60):
    t0 = time.time()
    while game.outpost.nasa.loading and time.time() - t0 < limit:
        step(1)
        time.sleep(0.03)
    return not game.outpost.nasa.loading


def play_a_mission(tag):
    o = game.outpost
    click("start")
    check(o.screen == "play" and o.session is not None, f"[{tag}] mission started")
    for _ in range(14):
        if o.screen != "play":
            break
        s = o.session
        s.reset()
        for cat, want in (("life_support", 12), ("shielding", 6), ("comms", 5), ("science", 4)):
            for _ in range(want):
                game.outpost.buttons[f"plus:{cat}"].on_click() if not game.outpost.buttons[f"plus:{cat}"].disabled else None
                step(1)
        game.outpost.buttons["advance"].on_click()
        step(2)
    check(o.screen == "result", f"[{tag}] mission reached its result screen ({o.session.state.status})")
    row = db.get_outpost_run(o.session.run_id)
    check(row["status"] in ("won", "lost") and row["seed"] == o.session.seed, f"[{tag}] result saved to the database")


def run(lang):
    tag = lang
    game.set_language(lang)
    step(3)
    game.show_menu()
    step(3)
    check(game.mode == "menu", f"[{tag}] main menu")
    for key in ("new_game", "continue", "op_ui_menu", "quit"):
        menu_button(key)
    check(True, f"[{tag}] menu has New Game, Continue, Outpost Command and Quit")
    menu_button("op_ui_menu").on_click()
    step(3)
    o = game.outpost
    check(game.mode == "outpost" and o.screen == "setup", f"[{tag}] Outpost Command setup screen opens")
    check(o.nasa.solar is not None and len(o.nasa.studies.entries) > 0, f"[{tag}] saved NASA data is available at once (offline-safe)")
    t0 = time.time()
    done = wait_for_nasa()
    print(f"     background NASA check: finished={done} in {time.time() - t0:.1f}s | DONKI {o.nasa.state['donki']}/"
          f"{o.nasa.solar.source} | OSDR {o.nasa.state['osdr']}/{o.nasa.studies.source}")
    check(done, f"[{tag}] background NASA refresh finished while the game kept running")
    if not LIVE:
        check(not o.nasa.solar.is_live and o.nasa.studies.source != "live", f"[{tag}] offline: saved data, never labeled live")
        check(i18n.t("op_ui_nasa_unreachable") in o.shown or "error" in o.nasa.state.values(), f"[{tag}] unreachable message shown")
    play_a_mission(tag)
    click("research")
    check(o.screen == "cards" and len(o.filtered_cards()) >= 8, f"[{tag}] {len(o.filtered_cards())} research cards")
    seen = set()
    for _ in range(len(o.filtered_cards())):
        seen.add(o.filtered_cards()[o.card_index].setting)
        click("next")
    check({"spaceflight", "ground"} <= seen, f"[{tag}] both spaceflight and ground-based studies are labeled")
    click("back")
    check(o.screen == "result", f"[{tag}] cards go back to where they were opened")
    click("menu")
    check(game.mode == "menu" and not o.active, f"[{tag}] back at the main menu")


run("en")
run("ar")
game.set_language("en")
step(2)
# the existing game still works after Outpost Command
pid = db.create_profile("Smoke", "mid")
db.record_completion(pid, "moon", 2)
before = (db.get_profile(pid)["xp"], db.get_progress(pid), db.completed_missions(pid))
game.load_profile(pid)
step(3)
check(game.mode == "map", "existing profile still opens the galaxy map")
check((db.get_profile(pid)["xp"], db.get_progress(pid), db.completed_missions(pid)) == before, "mission progress untouched by Outpost")
game.show_briefing("mars")
step(3)
check(game.mode == "briefing" and game.briefing_mission.id == "mars", "existing mission briefing still opens")
game.show_menu()
step(2)
check(game.mode == "menu", "and back to the menu")
print("ALL OUTPOST SMOKE CHECKS PASSED")
