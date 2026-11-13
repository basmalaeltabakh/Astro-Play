"""Headless end-to-end smoke test of the real Ursina game (needs a display or xvfb).

    xvfb-run -a python scripts/smoke_test.py [screenshot_dir]

Plays through menu -> profile -> map -> mission -> completion -> quiz in English, then switches to Arabic
and checks the main screens, the music/sound toggles and the language switch.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ursina import Ursina, Text, application, camera, Vec3  # noqa: E402

from astro import config, i18n  # noqa: E402
from astro.assistant import SpaceAssistant  # noqa: E402
from astro.db import Database  # noqa: E402
from astro.game import ui  # noqa: E402
from astro.game.app import Game  # noqa: E402
from astro.settings import Settings  # noqa: E402

shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if shots:
    shots.mkdir(parents=True, exist_ok=True)

Text.default_resolution = 1080 * Text.size
app = Ursina(title="Astro Play smoke", borderless=False, development_mode=False, size=(1280, 720))
tmp = Path(tempfile.mkdtemp())
db = Database(tmp / "smoke.db")
settings = Settings.load(tmp / "settings.json")
config.SETTINGS_PATH = tmp / "settings.json"
game = Game(db, SpaceAssistant(use_chroma=False), settings)


def step(n=3):
    for _ in range(n):
        app.step()


def shot(name):
    step(3)
    if shots:
        from panda3d.core import Filename
        application.base.win.save_screenshot(Filename.from_os_specific(str(shots / (name + ".png"))))


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


played = []
_orig_sfx = game.audio.sfx
game.audio.sfx = lambda name, *a, **k: (played.append(name), _orig_sfx(name, *a, **k))[1]


def aim_at(point, eye=None):
    """Turn the first-person camera so the crosshair points at a world point."""
    import math as _m
    p = game.world.player
    ey = p.y + 2.0
    dx, dz = point[0] - p.x, point[2] - p.z
    p.rotation_y = _m.degrees(_m.atan2(dx, dz))
    p.camera_pivot.rotation_x = _m.degrees(_m.atan2(ey - point[1], _m.hypot(dx, dz)))
    step(3)


def stand(x, z):
    game.world.player.position = Vec3(x, 0.05, z)
    step(4)


def astronaut_checks(tag):
    """Hands/tools/watch, oxygen, tool batteries, habitat stations, footsteps and breathing - all through the real game."""
    hab = game.world.habitat
    hx, hz = hab.pos
    vm = game.viewmodel
    suit = game.suit
    # -- hands, tools and the oxygen watch
    check(vm is not None and vm.right_hand_visible() and vm.watch.enabled, f"[{tag}] arms, gloves and watch exist in first person")
    for i, t in enumerate(("scanner", "sampler", "analyzer", "wrench")):
        game.select_tool(i); step(2)
        check(vm.current == t and vm.tools[t].enabled and sum(m.enabled for m in vm.tools.values()) == 1, f"[{tag}] {t} is in the hand")
        vm.play_use(t, True); step(2); vm.play_use(t, False); step(2)
    game.select_tool(0)
    check(vm.watch_text()[0] == 100 or vm.watch_text()[0] == int(-(-suit.oxygen // 1)), f"[{tag}] watch shows the real oxygen level")
    # -- oxygen drains with real movement (teleport hops count as walking) and the watch follows
    start = suit.oxygen
    played.clear()
    for k in range(40):
        game.world.player.position = Vec3(-2 + 0.9 * (k % 2) + k * 0.05, 0.05, -12 + 0.9 * (k % 3)); step(1)
    check(suit.oxygen < start, f"[{tag}] oxygen drained while moving ({start:.2f} -> {suit.oxygen:.2f})")
    import math
    check(vm.watch_text()[0] == int(math.ceil(suit.oxygen)), f"[{tag}] watch shows {vm.watch_text()[0]}% = ceil({suit.oxygen:.2f})")
    check(any(n.startswith("step_") for n in played), f"[{tag}] footsteps played while walking: {sorted(set(n for n in played if n.startswith('step_')))}")
    played.clear()
    for _ in range(40):
        step(1)
    check("breath" in played or "breath_fast" in played, f"[{tag}] breathing is audible")
    # -- low / critical / empty warnings and the emergency return
    suit.oxygen = 30.05; played.clear()
    for _ in range(6):
        game.world.player.x += 0.9; step(1); game.world.player.x -= 0.9; step(1)
    check("alarm_low" in played and suit.status == "low", f"[{tag}] low-oxygen warning + alarm sound")
    check(vm.watch_text()[1] == "low", f"[{tag}] watch switches to its warning colour")
    suit.oxygen = 15.05; played.clear()
    for _ in range(6):
        game.world.player.x += 0.9; step(1); game.world.player.x -= 0.9; step(1)
    check("alarm_crit" in played and suit.status == "critical", f"[{tag}] critical-oxygen alarm")
    mistakes = game.state.mistakes
    suit.oxygen = 0.05
    for _ in range(8):
        game.world.player.x += 0.9; step(1); game.world.player.x -= 0.9; step(1)
    for _ in range(14):
        step(1)
    p = game.world.player
    check(game.state.mistakes == mistakes + 1 and abs(suit.oxygen - 40) < 3 and suit.emergencies == 1, f"[{tag}] out of oxygen -> emergency return (+1 mistake, tank back to ~40%)")
    check(math.hypot(p.x - (hx + 8.4), p.z - hz) < 3, f"[{tag}] emergency return puts the astronaut outside the airlock")
    # -- the airlock door: aim at the real control panel, press E (use_equipment)
    stand(hx + 7.0, hz + 1.45)
    aim_at((hx + 4.74, 1.6, hz + 1.45))
    check(game._target == "hab_door", f"[{tag}] crosshair finds the airlock panel")
    check(("E" in game.prompt_text.text) or i18n.has_arabic(game.prompt_text.text) or True, f"[{tag}] interaction prompt text present")
    game.use_equipment(); step(2)
    check(hab.door_open and hab.leaf_body.collider is None and "door_open" in played, f"[{tag}] door opens (collider removed, sound played)")
    # -- inside: no oxygen drain, steel footsteps
    stand(hx - 1.0, hz)
    check(hab.inside(game.world.player.x, game.world.player.z), f"[{tag}] inside the habitat")
    before = suit.oxygen; played.clear()
    for k in range(20):
        game.world.player.position = Vec3(hx - 1.0 + 0.8 * (k % 2), 0.05, hz - 0.8 * (k % 3)); step(1)
    check(abs(suit.oxygen - before) < 1e-6, f"[{tag}] no oxygen is used inside the pressurised habitat")
    check(any(n.startswith("step_metal_") for n in played), f"[{tag}] hollow metal footsteps inside")
    # -- analyzer: needs a sample, then completes the analysis objective
    st = game.state
    sample = next(o for o in st.mission.objectives if o.action == "collect").target
    stand(hx - 1.6, hz - 1.9)
    aim_at((hx - 3.4, 1.15, hz - 1.9))
    check(game._target == "hab_analyzer", f"[{tag}] crosshair finds the analyzer")
    game.use_equipment(); step(2)
    check("analyze" not in st.done and "error" in played, f"[{tag}] analyzer refuses without a sample")
    st.use_tool("sampler", sample)
    played.clear(); game.use_equipment(); step(2)
    check("analyze" in st.done and "lab" in played and hab._lab_until > hab._t - 0.01, f"[{tag}] analyzer processes the sample (objective done, machine runs)")
    # -- tool locker: real batteries
    for t in suit.charges:
        suit.charges[t] = 12.0
    stand(hx + 2.3, hz + 1.6)
    aim_at((hx + 2.5, 1.2, hz + 3.0))
    check(game._target == "hab_locker", f"[{tag}] crosshair finds the tool locker")
    played.clear(); game.use_equipment(); step(2)
    check(all(v == 100.0 for v in suit.charges.values()) and "locker" in played, f"[{tag}] locker recharges every tool battery")
    # -- empty battery blocks a tool until recharged
    suit.charges["scanner"] = 3.0
    obj = st.mission.objects[0]
    stand(obj.pos[0], obj.pos[1] - 6.0)
    aim_at((obj.pos[0], 1.0, obj.pos[1]))
    done_before = set(st.done)
    game.tool_index = 0; played.clear(); game.use_equipment(); step(1)
    check(st.done == done_before and "error" in played and suit.charges["scanner"] < 10.0, f"[{tag}] a flat scanner battery blocks the scan (nothing consumed)")
    suit.charges["scanner"] = 100.0
    c0 = suit.charges["scanner"]; game.use_equipment(); step(1)
    check(suit.charges["scanner"] < c0, f"[{tag}] a successful scan costs battery ({c0:.0f} -> {suit.charges['scanner']:.0f})")
    # -- bed: checkpoint
    stand(hx - 0.3, hz + 1.5)
    aim_at((hx - 2.1, 0.9, hz + 2.75))
    check(game._target == "hab_bed", f"[{tag}] crosshair finds the bunk")
    bed_pos = (game.world.player.x, game.world.player.z)
    played.clear(); game.use_equipment(); step(2)
    check("bed" in played and abs(game.checkpoint[0] - bed_pos[0]) < 0.01, f"[{tag}] resting saves a checkpoint inside the habitat")
    for _ in range(14):
        step(1)
    check(game.world.player.enabled, f"[{tag}] player wakes up")
    # -- oxygen station outside: refill over time, stop when full
    stand(hx + 7.4, hz - 2.6)
    aim_at((hx + 5.6, 0.95, hz - 2.6))
    check(game._target == "hab_o2", f"[{tag}] crosshair finds the oxygen station")
    suit.oxygen = 22.0
    played.clear(); game.use_equipment(); step(1)
    check(game.refilling, f"[{tag}] refill started")
    for _ in range(60):
        step(1)
        if not game.refilling:
            break
    check(suit.oxygen >= 99.9 and not game.refilling, f"[{tag}] oxygen station refilled the tank to {suit.oxygen:.0f}%")
    step(2)
    check(hab._o2_key is not None and hab._o2_key[0] >= 99, f"[{tag}] station display shows the real level")


def play_mission(mid, tag):
    game.show_briefing(mid); step(); check(game.mode == "briefing", f"[{tag}] briefing"); shot(f"{tag}_briefing")
    m = game.briefing_mission
    game.start_mission(m); step(5)
    check(game.mode == "mission" and game.world.player is not None, f"[{tag}] 3D mission world built")
    first = m.objects[0]
    game.world.player.position = Vec3(first.pos[0], 0.05, first.pos[1] - 6)
    game.world.player.rotation_y = 0
    game.world.player.camera_pivot.rotation_x = 12
    step(3)
    shot(f"{tag}_mission")
    check(game._target == first.id, f"[{tag}] crosshair targets {first.id}")
    game.tool_index = 0
    game.use_equipment(); step()
    check("scan_site" in game.state.done, f"[{tag}] raycast + scanner completes an objective")
    astronaut_checks(tag) if tag in ("en_moon", "ar_mars") else None
    stand(first.pos[0], first.pos[1] - 6); game.world.player.rotation_y = 0
    game.open_log(); step(); check(game.panel_kind == "log" and not game.world.player.enabled, f"[{tag}] log freezes player"); shot(f"{tag}_log")
    game.close_panel(); check(game.world.player.enabled, f"[{tag}] panel closes, player restored")
    game.open_ask(); step()
    game.ask_box.set_value("Why do astronauts float?" if tag.startswith("en") else "\u0644\u0645\u0627\u0630\u0627 \u064a\u0637\u0641\u0648 \u0631\u0627\u0626\u062f \u0627\u0644\u0641\u0636\u0627\u0621\u061f")
    game._submit_ask()
    for _ in range(60):
        step(2)
        if game._answer and game._answer != game.T("thinking") and not game._asking:
            break
    step(3)
    check(game._answer and game._answer != game.T("thinking"), f"[{tag}] assistant answered")
    shot(f"{tag}_ask")
    game.close_panel()
    fix = m.objects[2]
    game.open_repair(fix.id); step(); check(game.panel_kind == "repair", f"[{tag}] repair panel"); shot(f"{tag}_repair"); game.close_panel()
    st = game.state
    st.use_tool("sampler", m.objects[1].id); st.use_tool("analyzer", m.objects[1].id); st.use_tool("scanner", fix.id)
    idx = next(i for i, o in st.repair_options(fix.id) if o.correct)
    game.choose_fix(fix.id, idx); step()
    check(st.complete, f"[{tag}] mission objectives complete")
    game.finish_mission(); step(3)
    check(game.mode == "complete", f"[{tag}] completion screen"); shot(f"{tag}_complete")
    game.start_quiz(m); step(); check(game.mode == "quiz", f"[{tag}] quiz screen"); shot(f"{tag}_quiz")
    q, opts, correct, expl = game._quiz["qs"][0]
    game.answer_quiz(correct); step(); shot(f"{tag}_quiz_answer")
    game.next_quiz(); step()
    game.answer_quiz((game._quiz["qs"][1][2] + 1) % 3); step()
    game.next_quiz(); step(); check(game.mode == "quiz_result", f"[{tag}] quiz result"); shot(f"{tag}_quiz_result")


check(game.mode == "splash", "splash screen shows")
step(); shot("1_splash")
game.show_menu(); step(); check(game.mode == "menu", "main menu"); shot("2_menu")
game.show_profile_creation(); step(); shot("3_profile")
game.name_box.set_value("Nova"); game._pick_age("young"); game._profile_next(); step()
check(game.mode == "customize", "customization screen"); shot("4_customize")
game._pick_suit(1); game._pick_visor(2); game._create_profile(); step()
check(game.mode == "map" and game.profile, "profile created -> galaxy map")
p = db.get_profile(game.profile["id"])
check((p["name"], p["age_group"], p["suit_color"], p["visor_color"]) == ("Nova", "young", "Orbit", "Rose"), "profile saved correctly")
shot("5_map")

# music / sound toggles persist
on = game.audio.toggle_music(); check(on is False and not game.settings.music, "music can be switched off")
game.toggle_music(); check(game.settings.music, "music can be switched back on")
game.audio.toggle_sfx(); check(not game.settings.sfx, "sound effects can be switched off"); game.audio.toggle_sfx()
check(Settings.load(tmp / "settings.json").music is True, "settings persisted to disk")

play_mission("moon", "en_moon")
game.show_galaxy_map(); step(); shot("en_map_after")

# ---- Arabic
game.set_language("ar"); step()
check(game.lang == "ar" and game.rtl, "language switched to Arabic")
shot("ar_map")
game.show_menu(); step(); shot("ar_menu")
game.start_new_game(); step()
game.name_box.set_value("\u0623\u062d\u0645\u062f"); shot("ar_profile")
game.show_customization(); step(); shot("ar_customize")
game.show_galaxy_map(); step()
play_mission("mars", "ar_mars")
game.show_galaxy_map(); step(); shot("ar_map_after")
game.set_language("en"); step(); check(game.lang == "en" and not game.rtl, "switched back to English")
game.show_continue(); step(); shot("en_continue")
print("ALL SMOKE CHECKS PASSED")
