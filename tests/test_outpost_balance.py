"""Gameplay balance guardrails for Outpost Command (Phase 7).

These tests play many seeded runs with simple, fixed strategies and check the PROPERTIES the balance is meant to have
(careless play loses, careful play wins, every resource matters, difficulty rises, Hard is still winnable). They do not pin
exact numbers: the margins leave room for small tuning, but a change that breaks the design intent will fail here.

Measured with 300-seed runs when these margins were chosen (see the Phase 7 report); each test uses 120 seeds so the whole
module takes a few seconds. Everything is deterministic: seeds are fixed, so a failure is always reproducible."""
import random
from collections import Counter

import pytest

from astro import outpost as O
from astro import outpost_config as C

SEEDS = range(120)
SITES = tuple(C.SITES)


# ----------------------------------------------------------------------------------------------- strategies and harness
def fit(available, wants):
    out, left = {}, available
    for cat, want in wants:
        x = max(0, min(want, left, C.ALLOC_LIMIT[cat]))
        out[cat], left = x, left - x
    return out


def static(ls=12, sh=6, comms=0, sci=8, focus=0.5, boost=None):
    """The same plan every sol. With ``boost``, shielding goes up when the forecast names a storm."""
    def strategy(state, available, category, hint):
        storm = boost is not None and (category == "solar_storm" or hint == "radiation")
        return fit(available, [("shielding", boost if storm else sh), ("life_support", ls), ("comms", comms),
                               ("science", sci)]), focus
    return strategy


def follow(ls=18, sh=8, comms=4, sci=0, boost=14):
    """The best plan found by search: radio on, shield up for forecast storms, Life Support follows the lower supply."""
    def strategy(state, available, category, hint):
        storm = category == "solar_storm" or hint == "radiation"
        low = min(state.oxygen, state.food) < 45
        focus = 1.0 if state.oxygen + 5 < state.food else 0.0 if state.food + 5 < state.oxygen else 0.5
        return fit(available, [("shielding", boost if storm else sh), ("life_support", min(20, ls + (6 if low else 0))),
                               ("comms", comms), ("science", sci)]), focus
    return strategy


def science_first(sci=10, keep=None):
    """Spend on science before anything else (the safe plan gets whatever power is left)."""
    safe = keep or follow(sci=0)

    def strategy(state, available, category, hint):
        wanted, focus = safe(state, available, category, hint)
        return fit(available, [("science", sci), ("shielding", wanted.get("shielding", 0)),
                               ("life_support", wanted.get("life_support", 0)), ("comms", wanted.get("comms", 0))]), focus
    return strategy


IDLE = static(0, 0, 0, 0)
ALL_SCIENCE = static(0, 0, 0, 99)
LIFE_FIRST = static(20, 8, 5, 8, 0.55)


def play(site, difficulty, seed, strategy, solar=C.SOLAR_ACTIVITY_DEFAULT):
    state, rng = O.new_state(site, difficulty), random.Random(seed)
    while state.status == O.RUNNING:
        event = O.roll_event(state, rng, solar)
        allocation, focus = strategy(state, O.available_power(state), O.forecast(state, event),
                                     O.forecast_hint(state, event))
        state = O.step_sol(state, allocation, event, focus)
    return state


def runs(site, difficulty, strategy, solar=C.SOLAR_ACTIVITY_DEFAULT, seeds=SEEDS):
    return [play(site, difficulty, s, strategy, solar) for s in seeds]


def win_rate(rs):
    return 100.0 * sum(r.status == O.WON for r in rs) / len(rs)


def avg_score(rs):
    return sum(r.score for r in rs) / len(rs)


# ----------------------------------------------------------------------------------------------- careless play loses
@pytest.mark.parametrize("site", SITES)
def test_doing_nothing_loses_normal_and_hard(site):
    assert win_rate(runs(site, "normal", IDLE)) < 20
    assert win_rate(runs(site, "hard", IDLE)) < 5


@pytest.mark.parametrize("site", SITES)
def test_doing_nothing_survives_easy_but_almost_always_earns_only_one_star(site):
    """Easy is a forgiving first mission: idling can survive, but it never earns more than the 1-star 'you made it'."""
    wins = [r for r in runs(site, "easy", IDLE) if r.status == O.WON]
    assert len(wins) > 60 and sum(O.rating(r) == 1 for r in wins) / len(wins) >= 0.9


@pytest.mark.parametrize("site", SITES)
def test_ignoring_survival_for_science_does_not_work_on_normal_or_hard(site):
    assert win_rate(runs(site, "normal", ALL_SCIENCE)) < 20
    assert win_rate(runs(site, "hard", ALL_SCIENCE)) < 5


@pytest.mark.parametrize("site", SITES)
def test_a_single_resource_is_never_enough_on_hard(site):
    for plan in (static(99, 0, 0, 0), static(0, 99, 0, 0)):
        assert win_rate(runs(site, "hard", plan)) < 65


# ----------------------------------------------------------------------------------------------- careful play wins
@pytest.mark.parametrize("site", SITES)
def test_a_sensible_fixed_plan_wins_almost_every_easy_and_normal_mission(site):
    plan = static(12, 6, 5, 8, 0.55, boost=12)
    assert win_rate(runs(site, "easy", plan)) >= 98
    assert win_rate(runs(site, "normal", plan)) >= 95


def test_hard_is_winnable_with_the_best_known_plan_on_both_sites():
    assert win_rate(runs("moon", "hard", follow())) >= 90
    assert win_rate(runs("mars", "hard", follow())) >= 82


def test_hard_mars_is_not_decided_by_luck_alone():
    """Different good plans win different seeds, so almost every seed is winnable by SOME sensible plan."""
    plans = [follow(), follow(20, 8, 4, 0, 14), static(16, 8, 5, 6, 0.55, boost=14), LIFE_FIRST, follow(14, 8, 4, 0, 14)]
    seeds = range(60)
    won = [any(play("mars", "hard", s, p).status == O.WON for p in plans) for s in seeds]
    assert sum(won) / len(won) >= 0.9


# ----------------------------------------------------------------------------------------------- every choice matters
@pytest.mark.parametrize("site", SITES)
def test_shielding_matters_without_it_normal_missions_are_lost(site):
    none, some = (win_rate(runs(site, "normal", static(12, sh, 0, 8, 0.5))) for sh in (0, 6))
    assert some - none >= 15


@pytest.mark.parametrize("site", SITES)
def test_life_support_matters(site):
    low, high = (win_rate(runs(site, "hard", static(ls, 6, 0, 8, 0.5))) for ls in (6, 16))
    assert high - low >= 25


@pytest.mark.parametrize("site", SITES)
def test_the_radio_pays_off_on_hard(site):
    """Communications cost power and score, but forecasts + resupply windows make Hard noticeably safer."""
    off, on = (win_rate(runs(site, "hard", static(12, 6, c, 8, 0.55, boost=12))) for c in (0, 5))
    assert on - off >= 10
    off_score = avg_score(runs(site, "hard", static(12, 6, 0, 8, 0.55, boost=12)))
    on_score = avg_score(runs(site, "hard", static(12, 6, 5, 8, 0.55, boost=12)))
    assert on_score < off_score                                             # a real cost, not a free lunch


@pytest.mark.parametrize("site", SITES)
def test_a_fixed_oxygen_only_or_food_only_focus_is_a_trap(site):
    balanced = win_rate(runs(site, "normal", static(12, 6, 0, 8, 0.5)))
    oxygen = win_rate(runs(site, "normal", static(12, 6, 0, 8, 1.0)))
    food = win_rate(runs(site, "normal", static(12, 6, 0, 8, 0.0)))
    assert balanced - oxygen >= 15 and balanced - food >= 40


@pytest.mark.parametrize("site", SITES)
def test_science_is_rewarded_and_is_a_real_gamble_on_hard(site):
    """Science always raises the score. Put LAST (leftover power) it is nearly free; put FIRST on Hard it costs survival.
    (On Normal Moon, science-first is also nearly free: the Moon is the generous beginner site, by design.)"""
    for diff in ("normal", "hard"):
        assert avg_score(runs(site, diff, static(12, 6, 0, 8))) - avg_score(runs(site, diff, static(12, 6, 0, 0))) >= 40
    safe = win_rate(runs(site, "hard", follow(sci=0)))
    greedy = win_rate(runs(site, "hard", science_first(10)))
    assert safe - greedy >= 30                                              # science FIRST starves the habitat on Hard


@pytest.mark.parametrize("site", SITES)
def test_more_science_means_more_stars_for_winners_on_normal(site):
    def stars(sci):
        wins = [r for r in runs(site, "normal", static(12, 6, 0, sci)) if r.status == O.WON]
        return sum(O.rating(r) for r in wins) / len(wins)
    assert stars(0) <= 1.2 < stars(4) < stars(14) + 0.01 and stars(14) >= 2.0


# ----------------------------------------------------------------------------------------------- difficulty progression
@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("plan,gap", [(static(12, 6, 0, 8, 0.55), 25), (static(16, 8, 5, 6, 0.55, boost=14), 0),
                                      (LIFE_FIRST, 0), (follow(), 0)], ids=["plain", "radio", "life-first", "follow"])
def test_the_same_plan_does_worse_as_difficulty_rises(site, plan, gap):
    """Never easier on a harder setting; a plain plan must also lose real ground (strong plans may stay near 100%)."""
    easy, normal, hard = (win_rate(runs(site, d, plan)) for d in ("easy", "normal", "hard"))
    assert easy >= normal - 1 and normal >= hard - 1 and easy - hard >= gap


@pytest.mark.parametrize("difficulty", list(C.DIFFICULTY))
def test_the_moon_is_never_harder_than_mars_for_the_same_plan(difficulty):
    plan = static(12, 6, 5, 8, 0.55, boost=12)
    assert win_rate(runs("moon", difficulty, plan)) >= win_rate(runs("mars", difficulty, plan)) - 3


def test_missions_get_longer_with_difficulty():
    sols = [C.DIFFICULTY[d]["sols"] for d in ("easy", "normal", "hard")]
    assert sols == sorted(sols) and len(set(sols)) == 3


# ----------------------------------------------------------------------------------------------- solar activity (DONKI input)
@pytest.mark.parametrize("site", SITES)
def test_stormier_space_weather_never_makes_a_good_plan_easier_and_never_makes_hard_unfair(site):
    plan = follow()
    calm, mid, stormy = (win_rate(runs(site, "hard", plan, solar)) for solar in (0.0, 0.5, 1.0))
    assert calm + 4 >= mid >= stormy - 4                                    # monotone within noise
    assert stormy >= 78                                                     # the stormiest NASA window stays winnable


@pytest.mark.parametrize("difficulty", ("easy", "normal"))
def test_solar_activity_cannot_break_easy_or_normal(difficulty):
    plan = static(12, 6, 5, 8, 0.55, boost=12)
    assert all(win_rate(runs("mars", difficulty, plan, solar)) >= 95 for solar in (0.0, 1.0))


# ----------------------------------------------------------------------------------------------- fairness and pacing
@pytest.mark.parametrize("difficulty", list(C.DIFFICULTY))
@pytest.mark.parametrize("site", SITES)
def test_event_pacing_rules_hold_for_every_seed(site, difficulty):
    cfg = C.DIFFICULTY[difficulty]
    for seed in SEEDS:
        state, rng, seq = O.new_state(site, difficulty), random.Random(seed), []
        while state.status == O.RUNNING:
            event = O.roll_event(state, rng, 1.0)                          # the stormiest sky is the hardest case
            seq.append(event)
            state = O.step_sol(state, fit(O.available_power(state), [("life_support", 12), ("shielding", 6)]), event, 0.5)
        hazards = [bool(e) and C.EVENTS[e]["kind"] == "hazard" for e in seq]
        assert not any(hazards[:cfg["grace_sols"]]), "no hazards in the grace sols"
        streak = best = 0
        for h in hazards:
            streak = streak + 1 if h else 0
            best = max(best, streak)
        assert best <= cfg["max_consecutive_hazards"]
        highs = [i for i, e in enumerate(seq) if e and C.EVENTS[e]["severity"] == "high" and C.EVENTS[e]["kind"] == "hazard"]
        assert all(b - a > C.FAIRNESS["high_hazard_gap"] - 1 for a, b in zip(highs, highs[1:]))


@pytest.mark.parametrize("difficulty", list(C.DIFFICULTY))
def test_every_event_type_can_happen_and_hazards_are_not_the_only_thing_players_see(difficulty):
    seen = Counter()
    for site in SITES:
        for seed in range(150):
            state, rng = O.new_state(site, difficulty), random.Random(seed)
            while state.status == O.RUNNING:
                event = O.roll_event(state, rng, 0.3)
                seen[event] += 1
                state = O.step_sol(state, fit(O.available_power(state), [("life_support", 12), ("shielding", 6)]), event, 0.5)
    assert set(C.EVENTS) <= set(seen)
    kinds = Counter(C.EVENTS[e]["kind"] for e in seen.elements() if e)
    assert kinds["opportunity"] / sum(kinds.values()) >= 0.2                 # helpful events are common enough to matter


# ----------------------------------------------------------------------------------------------- edge cases
@pytest.mark.parametrize("difficulty", list(C.DIFFICULTY))
@pytest.mark.parametrize("site", SITES)
def test_runs_always_end_in_win_or_loss_within_the_mission_length(site, difficulty):
    for r in runs(site, difficulty, static(12, 6, 5, 8, 0.55), seeds=range(40)):
        assert r.status in (O.WON, O.LOST) and r.sol - 1 <= C.DIFFICULTY[difficulty]["sols"]
        assert (r.status == O.WON) == (O.failure_key(r) is None)
        assert 0 <= r.oxygen <= C.CAP["oxygen"] and 0 <= r.food <= C.CAP["food"] and 0 <= r.power <= C.CAP["power"]
        assert 0 <= r.shielding <= C.CAP["shielding"] and 0 <= r.crew_health <= C.CAP["crew_health"]


def test_a_lost_mission_always_explains_why_and_score_is_never_negative():
    for site in SITES:
        finished = runs(site, "hard", IDLE, seeds=range(40))
        assert sum(r.status == O.LOST for r in finished) >= 38                # idling on Hard all but always loses
        for r in finished:
            assert r.score >= 0 and r.status in (O.WON, O.LOST)
            if r.status == O.LOST:
                assert O.failure_key(r) and O.failure_explanation(r)


@pytest.mark.parametrize("site", SITES)
def test_same_seed_and_plan_always_give_the_same_result(site):
    a = play(site, "hard", 7, follow())
    b = play(site, "hard", 7, follow())
    assert a == b


def test_overspending_power_is_rejected_not_silently_allowed():
    state = O.new_state("moon", "hard")
    with pytest.raises(ValueError):
        O.step_sol(state, {"life_support": 20, "shielding": 16, "science": 14}, None, 0.5)


def test_hoarding_power_is_not_a_winning_strategy_on_hard():
    """Spending only the bare minimum (the battery fills up unused) loses most Hard missions."""
    for site in SITES:
        assert win_rate(runs(site, "hard", static(7, 5, 0, 0))) < 40
