# -*- coding: utf-8 -*-
"""Tests for the astronaut update: oxygen + tool batteries, habitat lab, footsteps/breathing, new audio assets."""
import re
from pathlib import Path

import pytest

from astro import config
from astro.audio import AudioManager, SuitSounds, SURFACE_BY_MISSION
from astro.missions import MissionState, get_missions
from astro.settings import Settings
from astro.suit import (CRITICAL, EMERGENCY_O2, LOW, REFILL_RATE, TIER_DRAIN, TOOL_COST, Suit)


# ----------------------------------------------------------------------------- oxygen
def test_oxygen_drains_faster_walking_than_resting_and_not_inside():
    walk, rest, inside = Suit(), Suit(), Suit()
    for _ in range(600):
        walk.tick(0.1, True, False)
        rest.tick(0.1, False, False)
        inside.tick(0.1, True, True)
    assert walk.oxygen < rest.oxygen < 100.0
    assert inside.oxygen == 100.0                       # the habitat is pressurised: no drain inside


def test_oxygen_lasts_about_eleven_minutes_walking_and_scales_with_difficulty():
    s = Suit("normal")
    t = 0.0
    while s.oxygen > 0:
        s.tick(1.0, True, False)
        t += 1.0
    assert 9 * 60 < t < 13 * 60
    easy, hard = Suit("easy"), Suit("hard")
    for _ in range(100):
        easy.tick(1.0, True, False)
        hard.tick(1.0, True, False)
    assert easy.oxygen > hard.oxygen and TIER_DRAIN["easy"] < TIER_DRAIN["hard"]


def test_oxygen_events_fire_once_each_in_order_and_status_follows():
    s = Suit()
    events = []
    for _ in range(4000):
        events += s.tick(0.5, True, False)
    assert events == ["low", "critical", "empty"]
    assert s.status == "empty" and s.oxygen == 0.0


def test_status_thresholds():
    s = Suit()
    s.oxygen = LOW + 1
    assert s.status == "ok"
    s.oxygen = LOW
    assert s.status == "low"
    s.oxygen = CRITICAL
    assert s.status == "critical"
    s.oxygen = 0
    assert s.status == "empty"


def test_refill_restores_oxygen_and_rearms_warnings():
    s = Suit()
    s.oxygen = 12.0
    s.tick(0.01, True, False)
    s._fired.update({"low", "critical"})
    full = False
    for _ in range(100):
        full = s.refill(0.1)
        if full:
            break
    assert full and s.oxygen == 100.0
    ev = []
    for _ in range(4000):
        ev += s.tick(0.5, True, False)
    assert "low" in ev and "critical" in ev            # warns again on the next descent
    assert REFILL_RATE > 5


def test_emergency_reset_counts_and_restores_some_oxygen():
    s = Suit()
    s.tick(1, True, False)
    s.oxygen = 0
    s.emergency_reset()
    assert s.emergencies == 1 and s.oxygen == EMERGENCY_O2 and s.status == "ok"


# ----------------------------------------------------------------------------- tool batteries
def test_tool_batteries_consume_block_and_recharge():
    s = Suit()
    for _ in range(int(100 / TOOL_COST["sampler"])):
        assert s.can_use("sampler")
        s.consume("sampler")
    assert not s.can_use("sampler") and s.can_use("scanner")
    assert s.recharge_all() is True and s.can_use("sampler")
    assert s.recharge_all() is False                    # nothing to do when already full


def test_tool_batteries_trickle_back_outside_only():
    out, ins = Suit(), Suit()
    out.charges["scanner"] = ins.charges["scanner"] = 10.0
    for _ in range(100):
        out.tick(1.0, False, False)
        ins.tick(1.0, False, True)
    assert out.charges["scanner"] > 30 and ins.charges["scanner"] == 10.0


def test_a_mission_is_completable_on_one_charge():
    """Normal play must not require the locker: the minimum tool uses fit in the starting batteries."""
    needs = {"scanner": 3, "sampler": 1, "analyzer": 1, "wrench": 1}
    for tool, n in needs.items():
        assert n * TOOL_COST[tool] <= 100


# ----------------------------------------------------------------------------- habitat laboratory
def _state(lang="en", mission=0):
    return MissionState(get_missions(lang, "mid")[mission], "normal", lang, "mid")


def test_lab_needs_a_sample_first():
    st = _state()
    res = st.lab_analyze()
    assert not res.ok and "sample" in res.message.lower()


def test_lab_completes_the_pending_analysis_objective():
    st = _state()
    st.use_tool("sampler", "regolith")
    assert "analyze" not in st.done
    res = st.lab_analyze()
    assert res.ok and res.completed_objective == "analyze" and "analyze" in st.done
    assert any("lab" in e.lower() or "analysis" in e.lower() for e in st.evidence)


def test_lab_gives_one_time_bonus_afterwards_and_never_changes_requirements():
    st = _state()
    st.use_tool("sampler", "regolith")
    st.use_tool("analyzer", "regolith")                 # the normal way
    before = st.base_xp
    bonus = st.lab_analyze()
    assert bonus.ok and bonus.xp == MissionState.LAB_BONUS_XP and st.base_xp == before + MissionState.LAB_BONUS_XP
    again = st.lab_analyze()
    assert not again.ok and st.base_xp == before + MissionState.LAB_BONUS_XP
    assert "analyze" in st.done and not st.complete       # the bonus never completes or skips anything


def test_lab_works_in_arabic():
    st = _state("ar")
    st.use_tool("sampler", "regolith")
    res = st.lab_analyze()
    assert res.ok and re.search("[\u0600-\u06FF]", res.message)


# ----------------------------------------------------------------------------- footsteps, breathing
class Spy:
    def __init__(self):
        self.calls = []

    def sfx(self, name, volume=1.0, rate=1.0):
        self.calls.append(name)


def run(sounds, seconds, **kw):
    for _ in range(int(seconds / 0.016)):
        sounds.update(0.016, **kw)


def test_footsteps_only_when_walking_on_the_ground():
    a = Spy()
    s = SuitSounds(a, "mars")
    run(s, 2, moving=False, grounded=True)
    assert not any(c.startswith("step_") for c in a.calls)
    run(s, 2, moving=True, grounded=False)
    assert not any(c.startswith("step_") for c in a.calls)
    run(s, 3, moving=True, grounded=True)
    steps = [c for c in a.calls if c.startswith("step_")]
    assert 5 <= len(steps) <= 8 and all(c.startswith("step_gravel_") for c in steps)


@pytest.mark.parametrize("mission,surface", [("moon", "dust"), ("mars", "gravel"), ("orbital", "metal"), ("europa", "ice")])
def test_footstep_surface_follows_the_world(mission, surface):
    a = Spy()
    run(SuitSounds(a, mission), 1.5, moving=True, grounded=True)
    assert SURFACE_BY_MISSION[mission] == surface
    assert any(c.startswith(f"step_{surface}_") for c in a.calls)


def test_footsteps_are_hollow_metal_inside_the_habitat():
    a = Spy()
    run(SuitSounds(a, "moon"), 1.5, moving=True, grounded=True, inside=True)
    assert any(c.startswith("step_metal_") for c in a.calls) and not any(c.startswith("step_dust_") for c in a.calls)


def test_landing_thud_after_a_jump():
    a = Spy()
    s = SuitSounds(a, "moon")
    run(s, 0.6, moving=False, grounded=False)
    s.update(0.016, moving=False, grounded=True)
    assert "land" in a.calls


def test_breathing_speeds_up_as_oxygen_drops():
    counts = {}
    for status in ("ok", "low", "critical"):
        a = Spy()
        run(SuitSounds(a, "moon"), 20, moving=False, grounded=True, status=status)
        counts[status] = sum(c.startswith("breath") for c in a.calls)
    assert counts["ok"] < counts["low"] < counts["critical"]
    a = Spy()
    run(SuitSounds(a, "moon"), 8, moving=False, grounded=True, status="critical")
    assert "breath_fast" in a.calls


# ----------------------------------------------------------------------------- audio plumbing + assets
def test_loop_sfx_is_safe_without_an_audio_device(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "s.json")
    am = AudioManager(Settings(), loader=None)
    am.loop_sfx("o2fill", True)
    am.loop_sfx("o2fill", False)
    am.stop_sfx("nothing")


def test_every_sound_the_game_asks_for_exists():
    audio = config.ASSETS_DIR / "audio"
    code = "\n".join(p.read_text(encoding="utf-8") for p in (Path(config.ROOT) / "astro").rglob("*.py"))
    names = set(re.findall(r'sfx\(\s*"([a-z0-9_]+)"', code)) | set(re.findall(r'loop_sfx\(\s*"([a-z0-9_]+)"', code))
    names |= {f"step_{s}_{i}" for s in ("dust", "gravel", "ice", "metal") for i in range(3)}
    names |= {"breath", "breath_fast", "land"}
    missing = [n for n in sorted(names) if not (audio / f"sfx_{n}.wav").exists()]
    assert not missing, missing


def test_original_audio_files_are_still_present():
    for n in ("music_menu.wav", "music_mission.wav", "sfx_scan.wav", "sfx_collect.wav", "sfx_analyze.wav", "sfx_repair.wav",
              "sfx_error.wav", "sfx_click.wav", "sfx_success.wav", "sfx_launch.wav", "sfx_fanfare.wav"):
        assert (config.ASSETS_DIR / "audio" / n).stat().st_size > 1000
