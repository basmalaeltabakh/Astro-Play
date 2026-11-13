"""Outpost Command Phase 3: events, forecasting, fairness and replayability (pure logic, no UI)."""
import random
from dataclasses import replace

import pytest

from astro import i18n
from astro import outpost as O
from astro import outpost_config as C
from astro.outpost import LOST, RUNNING, WON, new_state, step_sol
from tests.test_outpost import balanced, fit, keys, quiet

HAZARDS = [e for e, v in C.EVENTS.items() if v["kind"] == "hazard"]
OPPORTUNITIES = [e for e, v in C.EVENTS.items() if v["kind"] == "opportunity"]
EXPECTED_EVENTS = {"solar_storm", "micrometeorite", "dust_storm", "dust_accumulation", "equipment_fault",
                   "crop_blight", "comms_blackout", "comms_window", "supply_cache", "science_discovery"}
RESOURCE_FIELDS = ("power", "oxygen", "food", "shielding", "crew_health")


def in_range(s):
    return (0 <= s.power <= C.CAP["power"] and 0 <= s.shielding <= C.CAP["shielding"]
            and 0 <= s.oxygen <= C.CAP["oxygen"] and 0 <= s.food <= C.CAP["food"]
            and 0 <= s.crew_health <= C.CAP["crew_health"])


def rolls(state, seed, n):
    rng = random.Random(seed)
    return [O.roll_event(state, rng) for _ in range(n)]


def sequence(site, diff, seed):
    """The event sequence of a whole mission played with a fixed sensible strategy."""
    s, rng, out = new_state(site, diff), random.Random(seed), []
    while s.status == RUNNING:
        ev = O.roll_event(s, rng)
        out.append(ev)
        s = step_sol(s, balanced(s, O.available_power(s), None)[0], ev)
    return out


# ---------------------------------------------------------------- catalogue
def test_all_supported_event_types_exist():
    assert set(C.EVENTS) == EXPECTED_EVENTS
    assert len(HAZARDS) >= 5 and len(OPPORTUNITIES) >= 3


@pytest.mark.parametrize("eid", sorted(EXPECTED_EVENTS))
def test_every_event_is_fully_defined(eid):
    ev = C.EVENTS[eid]
    assert ev["kind"] in ("hazard", "opportunity")
    assert ev["category"] in C.FORECAST_CATEGORIES
    assert ev["severity"] in ("low", "medium", "high")
    assert ev["weight"] > 0 and ev["min_sol"] >= 1 and ev["cooldown"] >= 0
    effects = set(ev) - {"kind", "category", "severity", "weight", "min_sol", "cooldown"}
    assert effects, "an event with no effects would be meaningless"
    known = {"radiation", "dust_sols", "dust_factor", "shield_damage", "battery_loss", "oxygen_leak", "food_loss",
             "comms_down_sols", "resupply", "bonus", "discovery"}
    assert effects <= known


@pytest.mark.parametrize("eid", sorted(EXPECTED_EVENTS))
def test_every_event_has_english_and_arabic_descriptions(eid):
    key = f"op_event_{eid}"
    en, ar = i18n.t(key, "en"), i18n.t(key, "ar")
    assert i18n.has_key(key, "en") and i18n.has_key(key, "ar")
    assert len(en) > 25 and en != ar and i18n.has_arabic(ar) and not i18n.has_arabic(en)
    assert key in keys(step_sol(quiet(sol=3), {}, eid))


def test_forecast_texts_exist_in_both_languages():
    for k in [f"op_forecast_{c}" for c in C.FORECAST_CATEGORIES] + ["op_forecast_off", "op_forecast_exact",
                                                                   "op_msg_discovery", "op_msg_discovery_small"]:
        en, ar = i18n.t(k, "en", event="X", points=1), i18n.t(k, "ar", event="X", points=1)
        assert en != ar and i18n.has_arabic(ar), k


# ---------------------------------------------------------------- effects of each event on the state
def test_solar_storm_harms_every_variable_when_shielding_is_low():
    base, hit = step_sol(quiet(shielding=10.0), {}), step_sol(quiet(shielding=10.0), {}, "solar_storm")
    for f in RESOURCE_FIELDS:
        assert getattr(hit, f) < getattr(base, f), f


def test_micrometeorite_only_damages_shielding():
    base, hit = step_sol(quiet(), {}), step_sol(quiet(), {}, "micrometeorite")
    assert hit.shielding < base.shielding
    for f in ("power", "oxygen", "food", "crew_health"):
        assert getattr(hit, f) == getattr(base, f)


def test_equipment_fault_costs_power_and_oxygen_but_not_food():
    base, hit = step_sol(quiet(), {}), step_sol(quiet(), {}, "equipment_fault")
    assert hit.power < base.power and hit.oxygen < base.oxygen and hit.food == base.food


def test_crop_blight_costs_only_food_and_can_starve_a_crew():
    base, hit = step_sol(quiet(), {}), step_sol(quiet(), {}, "crop_blight")
    assert hit.food < base.food and hit.oxygen == base.oxygen and hit.power == base.power
    assert step_sol(quiet(food=10.0), {}, "crop_blight").fail_reason == "food"


def test_dust_accumulation_is_milder_but_longer_than_a_dust_storm():
    acc, storm = C.EVENTS["dust_accumulation"], C.EVENTS["dust_storm"]
    assert acc["dust_factor"] > storm["dust_factor"] and acc["dust_sols"] > storm["dust_sols"]
    s = step_sol(quiet(), {}, "dust_accumulation")
    full = C.SITES["moon"]["gen"]
    for _ in range(acc["dust_sols"]):
        assert O.generation(s) == round(full * acc["dust_factor"])
        s = step_sol(s, {})
    assert O.generation(s) == full and s.dust_factor == 1.0


def test_dust_effects_stack_with_the_weakest_factor_and_longest_duration():
    s = step_sol(quiet(), {}, "dust_accumulation")
    s = step_sol(s, {}, "dust_storm")
    assert s.dust_factor == C.EVENTS["dust_storm"]["dust_factor"]
    assert s.dust_left == max(C.EVENTS["dust_storm"]["dust_sols"], C.EVENTS["dust_accumulation"]["dust_sols"] - 1)


def test_comms_blackout_wastes_comms_power_and_removes_the_forecast():
    s = step_sol(quiet(), {"comms": C.COMMS_FORECAST_FULL}, "comms_blackout")
    assert s.comms_down_left == C.EVENTS["comms_blackout"]["comms_down_sols"]
    assert s.comms_level == 0 and O.forecast(s, "solar_storm") is None and O.forecast_hint(s, "solar_storm") is None
    for _ in range(C.EVENTS["comms_blackout"]["comms_down_sols"]):
        s = step_sol(s, {"comms": C.COMMS_FORECAST_FULL})            # paid for, but wasted
        assert s.comms_level == 0
    assert s.comms_down_left == 0
    s = step_sol(s, {"comms": C.COMMS_FORECAST_FULL})
    assert O.forecast(s, "solar_storm") == "solar_storm"              # the link is back


def test_blackout_also_blocks_resupply_windows():
    s = step_sol(quiet(), {}, "comms_blackout")
    assert "op_msg_resupply_missed" in keys(step_sol(s, {"comms": C.COMMS_WINDOW_MIN}, "comms_window"))


def test_supply_cache_helps_power_and_shielding_and_respects_caps():
    base, hit = step_sol(quiet(), {}), step_sol(quiet(), {}, "supply_cache")
    assert hit.power > base.power and hit.shielding > base.shielding and hit.oxygen == base.oxygen
    full = step_sol(quiet(power=C.CAP["power"], shielding=C.CAP["shielding"]), {}, "supply_cache")
    assert full.power == C.CAP["power"] and full.shielding == C.CAP["shielding"]


def test_science_discovery_rewards_having_science_power_ready():
    d = C.EVENTS["science_discovery"]["discovery"]
    base = step_sol(quiet(), {"science": d["min_science"]})
    ready = step_sol(quiet(), {"science": d["min_science"]}, "science_discovery")
    unready = step_sol(quiet(), {"science": d["min_science"] - 1}, "science_discovery")
    nothing = step_sol(quiet(), {"science": d["min_science"] - 1})
    assert ready.score - base.score == pytest.approx(d["score"]) and "op_msg_discovery" in keys(ready)
    assert unready.score - nothing.score == pytest.approx(d["missed"]) and "op_msg_discovery_small" in keys(unready)
    assert d["score"] > d["missed"]


def test_opportunities_never_reduce_any_resource():
    for eid in OPPORTUNITIES:
        base, hit = step_sol(quiet(), {}), step_sol(quiet(), {}, eid)
        for f in RESOURCE_FIELDS:
            assert getattr(hit, f) >= getattr(base, f), (eid, f)


def test_hazard_damage_scales_with_difficulty_severity():
    for eid in ("micrometeorite", "equipment_fault", "crop_blight"):
        lost = {}
        for diff in C.DIFFICULTY:
            base, hit = step_sol(quiet(diff=diff), {}), step_sol(quiet(diff=diff), {}, eid)
            lost[diff] = sum(getattr(base, f) - getattr(hit, f) for f in ("power", "oxygen", "food", "shielding"))
        assert lost["easy"] <= lost["normal"] <= lost["hard"] and lost["easy"] < lost["hard"], eid


# ---------------------------------------------------------------- invalid and extreme inputs
@pytest.mark.parametrize("bad", ["", "SOLAR_STORM", "meteor", 5, ["solar_storm"], {"a": 1}, b"x", 1.5])
def test_invalid_event_inputs_are_rejected_cleanly(bad):
    s = new_state()
    with pytest.raises(ValueError):
        step_sol(s, {}, bad)
    assert s.sol == 1


@pytest.mark.parametrize("activity", [float("inf"), float("-inf"), -5, 5, 1e308, True])
def test_extreme_solar_activity_is_safe(activity):
    rng = random.Random(1)
    for _ in range(40):
        assert O.roll_event(quiet(sol=4), rng, activity) in [None, *C.EVENTS]


def test_every_event_on_the_weakest_possible_outpost_stays_valid():
    for eid in C.EVENTS:
        for diff in C.DIFFICULTY:
            s = step_sol(quiet(diff=diff, power=0.0, oxygen=C.CONSUME["oxygen"] + 1, food=C.CONSUME["food"] + 1,
                               shielding=0.0, crew_health=1.0, sol=3), {}, eid)
            assert in_range(s) and s.status in (RUNNING, LOST, WON)


def test_events_cannot_break_state_even_with_absurd_severity(monkeypatch):
    monkeypatch.setitem(C.DIFFICULTY["normal"], "severity_mult", 1000.0)
    for eid in C.EVENTS:
        assert in_range(step_sol(quiet(sol=3), {}, eid))


def test_fuzzed_playthroughs_keep_every_invariant():
    rng = random.Random(99)
    for _ in range(150):
        s = new_state(rng.choice(list(C.SITES)), rng.choice(list(C.DIFFICULTY)))
        while s.status == RUNNING:
            alloc, left = {}, O.available_power(s)
            for k in rng.sample(C.ALLOCATIONS, len(C.ALLOCATIONS)):
                x = rng.randint(0, min(left, C.ALLOC_LIMIT[k]))
                alloc[k], left = x, left - x
            ev = rng.choice([None, *C.EVENTS])                       # any event, even ones fairness would block
            s = step_sol(s, alloc, ev, rng.random())
            assert in_range(s)
            assert len(s.recent_events) <= C.FAIRNESS["history"]
            assert s.dust_left >= 0 and s.comms_down_left >= 0 and 0 < s.dust_factor <= 1.0


# ---------------------------------------------------------------- determinism and variety
def test_roll_event_always_consumes_exactly_two_random_numbers():
    for st in (new_state(), quiet(sol=6), quiet(diff="hard", sol=9)):
        a, b = random.Random(4), random.Random(4)
        O.roll_event(st, a)
        b.random()
        b.random()
        assert a.getstate() == b.getstate()


def test_identical_seed_and_inputs_reproduce_the_whole_event_sequence():
    for site in C.SITES:
        for diff in C.DIFFICULTY:
            assert sequence(site, diff, 123) == sequence(site, diff, 123)


def test_different_seeds_give_different_event_sequences():
    seqs = {tuple(sequence("moon", "normal", sd)) for sd in range(40)}
    assert len(seqs) > 30                                                # replayable but varied
    kinds = {e for sd in range(40) for e in sequence("moon", "normal", sd) if e}
    assert len(kinds) >= 8                                               # most of the catalogue shows up


def test_same_seed_and_state_give_the_same_event():
    assert rolls(quiet(sol=5), 8, 20) == rolls(quiet(sol=5), 8, 20)
    assert rolls(quiet(sol=5), 8, 20) != rolls(quiet(sol=5), 9, 20)


def test_forecast_and_hint_do_not_change_state_or_random_stream():
    s, rng = quiet(sol=5, comms_level=C.COMMS_FORECAST_FULL), random.Random(2)
    ev = O.roll_event(s, rng)
    snap, rng_state = replace(s), rng.getstate()
    for _ in range(5):
        O.forecast(s, ev)
        O.forecast_hint(s, ev)
    assert s == snap and rng.getstate() == rng_state


# ---------------------------------------------------------------- forecasting
def test_forecast_tiers_reveal_progressively_more():
    levels = {0: (False, False), C.COMMS_FORECAST_MIN - 1: (False, False), C.COMMS_FORECAST_MIN: (False, True),
              C.COMMS_FORECAST_FULL - 1: (False, True), C.COMMS_FORECAST_FULL: (True, True)}
    for level, (exact, hint) in levels.items():
        s = quiet(sol=5, comms_level=level)
        assert (O.forecast(s, "dust_storm") is not None) == exact, level
        assert (O.forecast_hint(s, "dust_storm") is not None) == hint, level


def test_basic_forecast_names_only_a_category_not_the_event():
    assert len([e for e, v in C.EVENTS.items() if v["category"] == "weather"]) >= 2
    assert len([e for e, v in C.EVENTS.items() if v["category"] == "damage"]) >= 2
    s = quiet(sol=5, comms_level=C.COMMS_FORECAST_MIN)
    for eid, v in C.EVENTS.items():
        hint = O.forecast_hint(s, eid)
        assert hint == v["category"] and hint != eid and hint in C.FORECAST_CATEGORIES


def test_forecast_is_hidden_when_the_mission_is_over_or_no_event_is_due():
    s = quiet(comms_level=C.COMMS_FORECAST_FULL, status=LOST)
    assert O.forecast(s, "solar_storm") is None and O.forecast_hint(s, "solar_storm") is None
    s = quiet(comms_level=C.COMMS_FORECAST_FULL)
    assert O.forecast(s, None) is None and O.forecast_hint(s, None) is None


def test_forecast_matches_what_actually_happens():
    s, rng = new_state(), random.Random(11)
    while s.status == RUNNING:
        ev = O.roll_event(s, rng)
        strong, hint = O.forecast(s, ev), O.forecast_hint(s, ev)
        if strong:
            assert strong == ev
        if hint:
            assert hint == C.EVENTS[ev]["category"]
        s = step_sol(s, {"comms": C.COMMS_FORECAST_FULL, "life_support": 12}, ev)


def test_comms_level_follows_last_sols_working_comms_power():
    s = step_sol(new_state(), {"comms": 6})
    assert s.comms_level == 6 and s.comms_ok
    s = step_sol(s, {"comms": 0})
    assert s.comms_level == 0 and not s.comms_ok


# ---------------------------------------------------------------- probability configuration
def test_event_chance_zero_means_a_quiet_mission(monkeypatch):
    monkeypatch.setitem(C.DIFFICULTY["normal"], "event_chance", 0.0)
    assert set(rolls(quiet(sol=5), 1, 200)) == {None}


def test_event_chance_is_capped_and_ramps_with_mission_progress():
    early, late = quiet(sol=1), quiet(sol=new_state().total_sols)
    assert O.event_chance(late) > O.event_chance(early)
    ramped = C.DIFFICULTY["normal"]["event_chance"] * (1 + C.FAIRNESS["chance_ramp"])
    assert O.event_chance(late) == pytest.approx(min(C.FAIRNESS["max_chance"], ramped))
    for diff in C.DIFFICULTY:
        for sol in range(1, C.DIFFICULTY[diff]["sols"] + 1):
            assert 0 < O.event_chance(quiet(diff=diff, sol=sol)) <= C.FAIRNESS["max_chance"]


def test_event_chance_drops_right_after_a_hazard():
    plain = quiet(sol=5, recent_events=("",))
    after = quiet(sol=5, recent_events=("micrometeorite",))
    assert O.event_chance(after) == pytest.approx(O.event_chance(plain) * C.FAIRNESS["after_hazard_chance_mult"])


def _always_event(monkeypatch):
    monkeypatch.setitem(C.DIFFICULTY["normal"], "event_chance", 1.0)
    monkeypatch.setitem(C.FAIRNESS, "max_chance", 1.0)
    monkeypatch.setitem(C.FAIRNESS, "after_hazard_chance_mult", 1.0)


def test_event_weights_are_configurable(monkeypatch):
    _always_event(monkeypatch)
    monkeypatch.setitem(C.EVENTS["supply_cache"], "weight", 1e9)
    got = [e for e in rolls(quiet(sol=6), 3, 300) if e]
    assert got.count("supply_cache") > 0.95 * len(got)


def test_zero_weight_events_never_happen(monkeypatch):
    _always_event(monkeypatch)
    for eid in C.EVENTS:
        if eid != "dust_storm":
            monkeypatch.setitem(C.EVENTS[eid], "weight", 0.0)
    assert {e for e in rolls(quiet("mars", sol=6), 1, 100) if e} <= {"dust_storm"}


def test_all_weights_zero_means_no_events_and_no_crash(monkeypatch):
    _always_event(monkeypatch)
    for eid in C.EVENTS:
        monkeypatch.setitem(C.EVENTS[eid], "weight", 0.0)
    assert set(rolls(quiet(sol=6), 1, 50)) == {None}


def test_site_changes_which_events_are_likely():
    count = lambda site, eid: sum(e == eid for sd in range(20) for e in rolls(quiet(site, sol=6), sd, 40))
    assert count("mars", "dust_storm") > count("moon", "dust_storm")
    assert count("moon", "micrometeorite") > count("mars", "micrometeorite")


# ---------------------------------------------------------------- difficulty and mission progression
def test_harder_difficulties_have_more_hazards_and_fewer_opportunities():
    def tally(diff):
        h = o = played = 0
        for sd in range(150):
            seq = sequence("moon", diff, sd)
            played += len(seq)
            h += sum(e in HAZARDS for e in seq)
            o += sum(e in OPPORTUNITIES for e in seq)
        return h / played, o / played                       # per sol actually played
    easy, normal, hard = tally("easy"), tally("normal"), tally("hard")
    assert easy[0] < normal[0] < hard[0]
    assert easy[1] > hard[1]


def test_difficulty_table_is_ordered_sensibly():
    d = C.DIFFICULTY
    for key in ("event_chance", "severity_mult", "hazard_mult", "sols"):
        assert d["easy"][key] <= d["normal"][key] <= d["hard"][key], key
    assert d["easy"]["grace_sols"] >= d["hard"]["grace_sols"]
    assert d["easy"]["max_consecutive_hazards"] <= d["hard"]["max_consecutive_hazards"]
    assert d["easy"]["opportunity_mult"] >= d["hard"]["opportunity_mult"]


def test_no_hazards_during_the_grace_period():
    for diff, d in C.DIFFICULTY.items():
        for sol in range(1, d["grace_sols"] + 1):
            assert not [e for e in O.eligible_events(quiet(diff=diff, sol=sol)) if e in HAZARDS], (diff, sol)
        assert [e for e in O.eligible_events(quiet(diff=diff, sol=d["grace_sols"] + 3)) if e in HAZARDS]
    for sd in range(100):
        assert sequence("moon", "normal", sd)[0] not in HAZARDS            # sol 1 is a safe start


def test_events_respect_their_earliest_sol():
    for eid, v in C.EVENTS.items():
        if v["min_sol"] > 1:
            assert eid not in O.eligible_events(quiet(sol=v["min_sol"] - 1))
    assert "solar_storm" not in O.eligible_events(quiet(sol=1))


# ---------------------------------------------------------------- fairness
def test_hazards_never_exceed_the_consecutive_limit():
    for diff, d in C.DIFFICULTY.items():
        for site in C.SITES:
            for sd in range(80):
                streak = worst = 0
                for e in sequence(site, diff, sd):
                    streak = streak + 1 if e in HAZARDS else 0
                    worst = max(worst, streak)
                assert worst <= d["max_consecutive_hazards"], (diff, site, sd)


def test_the_same_event_respects_its_cooldown():
    for diff in C.DIFFICULTY:
        for sd in range(60):
            seq = sequence("mars", diff, sd)
            for i, e in enumerate(seq):
                if e:
                    assert e not in seq[max(0, i - C.EVENTS[e]["cooldown"]):i], (diff, sd, e)


def test_high_severity_hazards_are_spaced_out():
    gap = C.FAIRNESS["high_hazard_gap"]
    highs = [e for e, v in C.EVENTS.items() if v["severity"] == "high" and v["kind"] == "hazard"]
    assert highs
    for sd in range(100):
        idx = [i for i, e in enumerate(sequence("moon", "hard", sd)) if e in highs]
        assert all(b - a >= gap for a, b in zip(idx, idx[1:]))


def test_blocked_events_are_removed_from_the_pool():
    assert "solar_storm" not in O.eligible_events(quiet(sol=6, recent_events=("solar_storm",)))
    easy = quiet(diff="easy", sol=6, recent_events=("micrometeorite",))          # easy allows 1 hazard in a row
    pool = O.eligible_events(easy)
    assert not [e for e in pool if e in HAZARDS] and [e for e in pool if e in OPPORTUNITIES]


def test_history_records_quiet_sols_and_stays_bounded():
    s = new_state()
    for _ in range(3):
        s = step_sol(s, {"life_support": 12}, None)
    assert s.recent_events == ("", "", "")
    s = new_state()
    for _ in range(C.FAIRNESS["history"] + 3):
        if s.status != RUNNING:
            break
        s = step_sol(replace(s, oxygen=100.0, food=100.0, power=C.CAP["power"]), {}, "supply_cache")
    assert len(s.recent_events) == C.FAIRNESS["history"]
    assert set(s.recent_events) == {"supply_cache"}


def adaptive(s, a, f, h):
    threat = f == "solar_storm" or h == "radiation"
    sh = 12 if threat or s.shielding < 50 else 4
    ls = 16 if min(s.oxygen, s.food) < 55 else 12
    return fit(a, [("life_support", ls), ("shielding", sh), ("comms", C.COMMS_FORECAST_FULL), ("science", 6)]), \
        (0.7 if s.oxygen < s.food else 0.35)


def worst_case(site, diff):
    """An adversary picks the most damaging *legal* hazard every single sol."""
    metric = lambda s: s.oxygen + s.food + s.shielding + s.power + 2 * s.crew_health - (1000 if s.status == LOST else 0)
    s = new_state(site, diff)
    while s.status == RUNNING:
        a = O.available_power(s)
        plan, focus = adaptive(s, a, None, None)
        pool = [e for e in O.eligible_events(s) if e in HAZARDS]
        ev = min(pool, key=lambda e: metric(step_sol(s, plan, e, focus)), default=None)
        plan, focus = adaptive(s, a, O.forecast(s, ev), O.forecast_hint(s, ev))
        s = step_sol(s, plan, ev, focus)
    return s


@pytest.mark.parametrize("site", sorted(C.SITES))
@pytest.mark.parametrize("diff", ["easy", "normal"])
def test_a_careful_player_survives_even_the_worst_legal_event_sequence(site, diff):
    """Fairness guarantee: bad luck alone cannot make easy or normal unwinnable."""
    assert worst_case(site, diff).status == WON


def test_event_density_stays_reasonable():
    for diff, d in C.DIFFICULTY.items():
        counts = [sum(e is not None for e in sequence("moon", diff, sd)) / d["sols"] for sd in range(100)]
        avg = sum(counts) / len(counts)
        assert 0.25 <= avg <= 0.85, (diff, avg)            # neither empty nor relentless
