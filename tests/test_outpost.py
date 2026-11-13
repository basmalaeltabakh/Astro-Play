"""Outpost Command simulation tests (pure logic: no Ursina, no network, no database)."""
import ast
import random
import re
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from astro import i18n
from astro import outpost as O
from astro import outpost_config as C
from astro.outpost import LOST, RUNNING, WON, new_state, step_sol

ROOT = Path(__file__).resolve().parent.parent


def play(site, diff, seed, strategy, solar=C.SOLAR_ACTIVITY_DEFAULT):
    s, rng = new_state(site, diff), random.Random(seed)
    while s.status == RUNNING:
        ev = O.roll_event(s, rng, solar)
        alloc, focus = strategy(s, O.available_power(s), O.forecast(s, ev), O.forecast_hint(s, ev))
        s = step_sol(s, alloc, ev, focus)
    return s


def fit(avail, wants):
    out, left = {}, avail
    for k, v in wants:
        x = max(0, min(v, left, C.ALLOC_LIMIT[k]))
        out[k] = x
        left -= x
    return out


def balanced(s, a, f, h=None):
    return fit(a, [("life_support", 12), ("shielding", 4), ("comms", 3), ("science", 8)]), 0.55


def science_only(s, a, f, h=None):
    return fit(a, [("science", 10)]), 0.5


def smart(s, a, f, h=None):
    threat = f == "solar_storm" or h == "radiation"
    sh = 10 if threat or s.shielding < 45 else 4
    return fit(a, [("shielding", sh), ("life_support", 12), ("comms", C.COMMS_FORECAST_FULL),
                   ("science", 6)]), 0.55


def rate(strategy, diff, site="moon", n=60):
    return sum(play(site, diff, sd, strategy).status == WON for sd in range(n)) / n


def quiet(site="moon", diff="normal", **kw):
    return replace(new_state(site, diff), **kw)


def keys(state):
    return [k for k, _ in state.log]


# ---------------------------------------------------------------- structure rules
def test_exactly_three_core_resources():
    assert C.RESOURCES == ("power", "life_support", "shielding")
    assert set(O.resources(new_state())) == set(C.RESOURCES)


def test_oxygen_and_food_are_life_support_sub_values():
    assert C.LIFE_SUPPORT_PARTS == ("oxygen", "food")
    s = quiet(oxygen=70.0, food=40.0)
    assert not {"oxygen", "food"} & set(O.resources(s))
    assert O.life_support(s) == 40.0                    # the weakest part defines Life Support


def test_comms_and_science_are_allocations_not_resources():
    assert set(C.ALLOCATIONS) == {"life_support", "shielding", "comms", "science"}
    assert not {"comms", "science", "crew_health"} & set(C.RESOURCES)
    assert not {"comms", "science", "crew_health"} & set(O.resources(new_state("mars")))


def test_simulation_modules_have_no_ui_engine_network_or_db_imports():
    for name in ("outpost.py", "outpost_config.py"):
        tree = ast.parse((ROOT / "astro" / name).read_text(encoding="utf-8"))
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                mods.add(n.module.split(".")[0])
        assert not mods & {"ursina", "panda3d", "requests", "sqlite3"}, (name, mods)


def test_balance_numbers_live_only_in_the_config():
    """The engine may only use trivial literals (0, 1, 0.0, 1.0); every balance number must come from config."""
    tree = ast.parse((ROOT / "astro" / "outpost.py").read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            assert n.value in (0, 1, 0.0, 1.0), f"magic number {n.value} at line {n.lineno}"


# ---------------------------------------------------------------- initialization
def test_state_initialization_uses_the_config():
    for diff, d in C.DIFFICULTY.items():
        s = new_state("moon", diff)
        assert (s.sol, s.score, s.status, s.fail_reason) == (1, 0.0, RUNNING, None)
        assert s.power == d["start_power"] and s.total_sols == d["sols"]
        assert (s.oxygen, s.food, s.shielding, s.crew_health) == (
            C.START["oxygen"], C.START["food"], C.START["shielding"], C.START["crew_health"])


def test_state_is_immutable_and_step_does_not_mutate_input():
    s = new_state()
    with pytest.raises(FrozenInstanceError):
        s.power = 99
    before = replace(s)
    step_sol(s, {"science": 3})
    assert s == before


def test_unknown_site_or_difficulty_rejected():
    with pytest.raises(ValueError):
        new_state("venus")
    with pytest.raises(ValueError):
        new_state("moon", "nightmare")


# ---------------------------------------------------------------- allocation validation
def test_invalid_allocations_are_rejected_without_side_effects():
    s = new_state()
    bad = [{"nuclear": 1}, {"science": -1}, {"science": 1.5}, {"science": "3"}, {"science": True},
           {"science": C.ALLOC_LIMIT["science"] + 1},
           {k: C.ALLOC_LIMIT[k] for k in C.ALLOCATIONS}]       # sum above the power budget
    for alloc in bad:
        with pytest.raises(ValueError):
            step_sol(s, alloc)
    assert s.sol == 1


def test_total_allocation_may_equal_but_not_exceed_available_power():
    s = new_state()
    avail = O.available_power(s)
    assert avail < sum(C.ALLOC_LIMIT.values())                  # the budget, not the limits, is what binds
    exact = fit(avail, [(k, C.ALLOC_LIMIT[k]) for k in C.ALLOCATIONS])
    assert sum(exact.values()) == avail
    step_sol(s, exact)                                          # spending exactly the budget is allowed
    poor = quiet(power=0.0)                                     # less in the battery, smaller budget
    over = {k: C.ALLOC_LIMIT[k] for k in ("life_support", "shielding")}
    assert sum(over.values()) > O.available_power(poor)
    with pytest.raises(ValueError):
        step_sol(poor, over)


def test_unknown_event_and_finished_mission_rejected():
    with pytest.raises(ValueError):
        step_sol(new_state(), {}, "alien_invasion")
    with pytest.raises(RuntimeError):
        step_sol(replace(new_state(), status=LOST), {})


# ---------------------------------------------------------------- consumption, gains and losses
def test_daily_consumption_of_oxygen_and_food_when_nothing_is_funded():
    s = step_sol(new_state(), {})
    assert s.oxygen == C.START["oxygen"] - C.CONSUME["oxygen"]
    assert s.food == C.START["food"] - C.CONSUME["food"]
    assert s.sol == 2


def test_base_load_is_paid_and_leftover_charges_the_battery_up_to_the_cap():
    s0 = new_state()
    s = step_sol(s0, {"science": 5})
    assert s.power == pytest.approx(s0.power + O.generation(s0) - C.BASE_LOAD - 5)
    assert step_sol(quiet(power=C.CAP["power"]), {}).power == C.CAP["power"]


def test_life_support_power_recovers_oxygen_and_food_and_focus_trades_them():
    base = step_sol(new_state(), {})
    o = step_sol(new_state(), {"life_support": 10}, ls_focus=1.0)
    f = step_sol(new_state(), {"life_support": 10}, ls_focus=0.0)
    assert o.oxygen == pytest.approx(base.oxygen + 10 * C.LIFE_SUPPORT_RATE["oxygen"])
    assert f.food == pytest.approx(base.food + 10 * C.LIFE_SUPPORT_RATE["food"])
    assert o.oxygen > f.oxygen and o.food < f.food


def test_science_allocation_earns_score_and_costs_survival():
    sci, none = step_sol(new_state(), {"science": 10}), step_sol(new_state(), {})
    assert sci.score - none.score == pytest.approx(10 * C.SCORE["science"])
    assert sci.power < none.power                       # the power is gone
    assert sci.shielding == none.shielding              # and it did not strengthen anything else


def test_every_allocation_has_a_distinct_benefit_and_a_cost():
    base = step_sol(new_state(), {})
    ls = step_sol(new_state(), {"life_support": 6})
    sh = step_sol(new_state(), {"shielding": 6})
    co = step_sol(new_state(), {"comms": 6})
    sc = step_sol(new_state(), {"science": 6})
    assert ls.oxygen > base.oxygen and ls.shielding == base.shielding and ls.score == base.score
    assert sh.shielding > base.shielding and sh.oxygen == base.oxygen and sh.score == base.score
    assert co.comms_ok and not base.comms_ok and co.oxygen == base.oxygen and co.score == base.score
    assert sc.score > base.score and sc.oxygen == base.oxygen
    for s in (ls, sh, co, sc):
        assert s.power == pytest.approx(base.power - 6)  # nothing is free


def test_blackout_when_base_load_cannot_be_paid(monkeypatch):
    monkeypatch.setitem(C.SITES["moon"], "gen", 3)
    s = quiet(power=2.0)
    assert O.is_blackout(s) and O.available_power(s) == 0
    with pytest.raises(ValueError):
        step_sol(s, {"science": 1})                      # nothing can be allocated in a blackout
    nxt = step_sol(s, {})
    assert "op_msg_blackout" in keys(nxt)
    assert nxt.power == 0.0
    assert nxt.crew_health == s.crew_health - C.HEALTH["blackout_penalty"]


# ---------------------------------------------------------------- shielding
def test_shielding_wears_and_power_rebuilds_it():
    worn, built = step_sol(new_state(), {}), step_sol(new_state(), {"shielding": 8})
    assert worn.shielding == C.START["shielding"] - C.SHIELD_WEAR
    assert built.shielding == pytest.approx(worn.shielding + 8 * C.SHIELD_RATE)


def test_shielding_absorbs_radiation_and_unabsorbed_radiation_hurts_everything():
    strong = step_sol(quiet(shielding=100.0), {}, "solar_storm")
    weak = step_sol(quiet(shielding=10.0), {}, "solar_storm")
    assert "op_msg_radiation_leaked" in keys(weak)
    assert strong.oxygen > weak.oxygen and strong.food > weak.food
    assert strong.power > weak.power and strong.crew_health > weak.crew_health
    assert strong.shielding > weak.shielding


def test_full_shielding_can_completely_block_a_storm_on_easy():
    s = step_sol(quiet(diff="easy", shielding=100.0), {}, "solar_storm")
    assert "op_msg_radiation_blocked" in keys(s) and "op_msg_radiation_leaked" not in keys(s)
    assert s.crew_health == C.CAP["crew_health"] and s.oxygen == C.START["oxygen"] - C.CONSUME["oxygen"]


def _storm_damage(diff, shielding):
    """(unabsorbed radiation, total oxygen+food+power+health lost to the storm) for an otherwise identical outpost."""
    s0 = quiet(diff=diff, shielding=shielding)
    base, hit = step_sol(s0, {}), step_sol(s0, {}, "solar_storm")
    leak = next(p["leak"] for k, p in hit.log if k.startswith("op_msg_radiation"))
    loss = sum(getattr(base, f) - getattr(hit, f) for f in ("oxygen", "food", "power", "crew_health"))
    return leak, loss


SIGNIFICANT_REDUCTION = 0.60            # full shielding must remove at least this share of a storm's damage


@pytest.mark.parametrize("diff", ["normal", "hard"])
def test_full_shielding_significantly_reduces_storm_damage_on_normal_and_hard(diff):
    """Normal / hard keep their pressure (a storm may still get through) but shielding must clearly matter."""
    full_leak, full_loss = _storm_damage(diff, C.CAP["shielding"])
    none_leak, none_loss = _storm_damage(diff, 0.0)
    assert none_leak > 0 and none_loss > 0                           # an unshielded outpost is really hurt
    assert full_leak < none_leak and full_loss < none_loss           # strictly lower with full shielding
    assert full_leak <= none_leak * (1 - SIGNIFICANT_REDUCTION)
    assert full_loss <= none_loss * (1 - SIGNIFICANT_REDUCTION)


def test_storm_damage_never_increases_as_shielding_grows():
    for diff in C.DIFFICULTY:
        losses = [_storm_damage(diff, sh)[1] for sh in range(0, int(C.CAP["shielding"]) + 1, 10)]
        assert losses == sorted(losses, reverse=True), diff
        assert losses[0] > losses[-1]


def test_full_shielding_beats_no_shielding_on_every_difficulty():
    for diff in C.DIFFICULTY:
        assert _storm_damage(diff, C.CAP["shielding"])[1] < _storm_damage(diff, 0.0)[1], diff


def test_easy_full_shielding_still_blocks_a_storm_completely_while_none_hurts():
    full_leak, full_loss = _storm_damage("easy", C.CAP["shielding"])
    none_leak, none_loss = _storm_damage("easy", 0.0)
    assert (full_leak, full_loss) == (0, 0) and none_leak > 0 and none_loss > 0


def test_more_shielding_means_less_radiation_damage():
    leaks = []
    for sh in (20.0, 40.0, 60.0, 80.0):
        s = step_sol(quiet(shielding=sh), {}, "solar_storm")
        leaks.append(next(p["leak"] for k, p in s.log if k.startswith("op_msg_radiation")))
    assert leaks == sorted(leaks, reverse=True) and leaks[0] > leaks[-1]


# ---------------------------------------------------------------- other events
def test_dust_storm_cuts_generation_for_exactly_its_duration():
    s = quiet("mars")
    full = O.generation(s)
    s = step_sol(s, {}, "dust_storm")
    for _ in range(C.EVENTS["dust_storm"]["dust_sols"]):
        assert O.generation(s) < full
        s = step_sol(s, {})
    assert O.generation(s) == full


def test_micrometeorite_equipment_fault_and_comms_window():
    base = step_sol(quiet(), {})
    assert step_sol(quiet(), {}, "micrometeorite").shielding < base.shielding
    e = step_sol(quiet(), {}, "equipment_fault")
    assert e.power < base.power and e.oxygen < base.oxygen
    on = step_sol(quiet(), {"comms": C.COMMS_WINDOW_MIN}, "comms_window")
    off = step_sol(quiet(), {}, "comms_window")
    assert "op_msg_resupply_received" in keys(on) and "op_msg_resupply_missed" in keys(off)
    assert on.food > off.food


def test_forecast_requires_communications():
    s = new_state()
    assert O.forecast_hint(s, "solar_storm") == "radiation"          # sol 1 starts with a basic forecast
    s = step_sol(s, {"comms": 0})
    assert O.forecast(s, "solar_storm") is None and O.forecast_hint(s, "solar_storm") is None
    s = step_sol(s, {"comms": C.COMMS_FORECAST_MIN})
    assert O.forecast_hint(s, "solar_storm") == "radiation"          # basic comms: only the category
    assert O.forecast(s, "solar_storm") is None
    s = step_sol(s, {"comms": C.COMMS_FORECAST_FULL})
    assert O.forecast(s, "solar_storm") == "solar_storm"             # strong comms: the exact event
    assert O.forecast(s, None) is None and O.forecast_hint(s, None) is None


# ---------------------------------------------------------------- crew health
def test_low_oxygen_or_food_damages_health_and_each_counts():
    fine = C.LOW_LEVEL + 20
    low_o = C.LOW_LEVEL - 1 + C.CONSUME["oxygen"]               # ends the sol just below the low level
    low_f = C.LOW_LEVEL - 1 + C.CONSUME["food"]
    ok = step_sol(quiet(oxygen=fine, food=fine), {})
    one = step_sol(quiet(oxygen=low_o, food=fine), {})
    two = step_sol(quiet(oxygen=low_o, food=low_f), {})
    assert ok.crew_health == C.CAP["crew_health"]
    assert one.crew_health == C.CAP["crew_health"] - C.HEALTH["low_supply_penalty"]
    assert two.crew_health == C.CAP["crew_health"] - 2 * C.HEALTH["low_supply_penalty"]
    assert "op_msg_low_oxygen" in keys(one) and "op_msg_low_food" in keys(two)


def test_health_recovers_only_when_supplies_are_healthy_and_nothing_hurt():
    healed = step_sol(quiet(crew_health=50.0), {"life_support": 12}, ls_focus=0.55)
    assert healed.crew_health == 50.0 + C.HEALTH["recovery"]
    thin = quiet(crew_health=50.0, oxygen=C.HEALTH["recovery_min_supply"], food=C.HEALTH["recovery_min_supply"])
    assert step_sol(thin, {}).crew_health == 50.0           # supplies dip below the recovery level: no healing


def test_health_stays_within_zero_and_the_cap():
    assert step_sol(quiet(crew_health=100.0), {"life_support": 12}).crew_health == C.CAP["crew_health"]
    assert step_sol(quiet(crew_health=1.0, oxygen=C.LOW_LEVEL, food=C.LOW_LEVEL), {}).crew_health == 0.0


# ---------------------------------------------------------------- win / lose
@pytest.mark.parametrize("start,reason", [
    ({"oxygen": 1.0}, "oxygen"), ({"food": 1.0}, "food"),
    ({"crew_health": 1.0, "oxygen": C.LOW_LEVEL, "food": C.LOW_LEVEL}, "crew_health")])
def test_mission_is_lost_when_oxygen_food_or_health_reach_zero(start, reason):
    s = step_sol(quiet(**start), {})
    assert s.status == LOST and s.fail_reason == reason
    assert "op_msg_lost" in keys(s)
    assert s.sol == 2 and s.score == 0.0                       # a lost sol earns nothing


def test_surviving_every_sol_wins_with_a_bonus_and_stars():
    s = play("moon", "easy", 2, lambda st, a, f, h=None: (fit(a, [("life_support", 16), ("shielding", 12)]), 0.55))
    assert s.status == WON and s.sol == s.total_sols + 1 and s.fail_reason is None
    assert "op_msg_won" in keys(s)
    assert O.rating(s) in (1, 2, 3) and O.rating(new_state()) == 0
    lo, hi = C.SCORE["stars_per_sol"]
    assert O.rating(replace(s, score=hi * s.total_sols)) == 3
    assert O.rating(replace(s, score=lo * s.total_sols)) == 2
    assert O.rating(replace(s, score=0.0)) == 1


def test_mission_duration_follows_difficulty():
    for diff, d in C.DIFFICULTY.items():
        s, n = new_state("moon", diff), 0
        while s.status == RUNNING:
            s, n = step_sol(replace(s, oxygen=100.0, food=100.0, shielding=100.0, power=60.0), {}), n + 1
        assert s.status == WON and n == d["sols"]


def test_failure_explanations_are_educational_and_bilingual():
    for reason in ("oxygen", "food", "crew_health"):
        lost = replace(new_state(), status=LOST, fail_reason=reason)
        assert O.failure_key(lost) == f"op_fail_{reason}"
        en, ar = O.failure_explanation(lost, "en"), O.failure_explanation(lost, "ar")
        assert len(en) > 60 and en != ar and i18n.has_arabic(ar)
    assert O.failure_explanation(new_state()) == "" and O.failure_key(new_state()) is None


def test_every_message_key_the_simulation_can_emit_is_translated():
    needed = {f"op_event_{e}" for e in C.EVENTS} | {f"op_fail_{r}" for r in ("oxygen", "food", "crew_health")}
    needed |= set(re.findall(r'"(op_msg_[a-z_]+)"', (ROOT / "astro" / "outpost.py").read_text(encoding="utf-8")))
    needed |= {f"op_{k}" for k in ("power", "life_support", "shielding", "oxygen", "food", "crew_health", "score",
                                   "comms", "science", "sol")}
    needed |= {f"op_forecast_{c}" for c in C.FORECAST_CATEGORIES} | {"op_forecast_off", "op_forecast_exact"}
    assert len(needed) > 20
    for k in needed:
        assert i18n.has_key(k, "en") and i18n.has_key(k, "ar"), k


# ---------------------------------------------------------------- determinism
def test_step_sol_is_deterministic():
    s = new_state("mars", "hard")
    assert step_sol(s, {"life_support": 8, "science": 3}, "solar_storm", 0.7) == \
        step_sol(s, {"life_support": 8, "science": 3}, "solar_storm", 0.7)


def test_same_seed_gives_same_run_and_different_seeds_differ():
    run = lambda sd: play("mars", "normal", sd, balanced)
    assert run(7) == run(7)
    assert any(run(7) != run(sd) for sd in range(8, 20))


def test_solar_activity_raises_solar_storm_frequency_and_is_clamped():
    def storms(act):
        s, rng = quiet(sol=4), random.Random(5)                     # solar storms are not allowed before min_sol
        return sum(O.roll_event(s, rng, act) == "solar_storm" for _ in range(600))
    assert storms(1.0) > storms(0.0)
    s, a, b = quiet(sol=4), random.Random(3), random.Random(3)
    assert [O.roll_event(s, a, 99) for _ in range(30)] == [O.roll_event(s, b, 1.0) for _ in range(30)]


# ---------------------------------------------------------------- balance
def test_balance_rewards_planning_and_punishes_neglect():
    assert rate(smart, "normal") >= 0.9
    assert rate(smart, "hard") < 1.0
    assert rate(smart, "easy") >= rate(smart, "hard")
    assert rate(science_only, "normal", "mars") < rate(smart, "normal", "mars")     # neglecting survival costs


def test_playthroughs_keep_every_value_in_range():
    for site in C.SITES:
        for diff in C.DIFFICULTY:
            for sd in range(10):
                s = play(site, diff, sd, balanced)
                assert s.status in (WON, LOST)
                assert 0 <= s.power <= C.CAP["power"] and 0 <= s.shielding <= C.CAP["shielding"]
                assert 0 <= s.oxygen <= C.CAP["oxygen"] and 0 <= s.food <= C.CAP["food"]
                assert 0 <= s.crew_health <= C.CAP["crew_health"]
