"""Outpost Command simulation. Pure logic: no Ursina, no UI, no network, no database.

State is an immutable ``OutpostState``.  ``step_sol(state, allocation, event)`` is a pure function that returns the
next state (it never mutates its input and uses no hidden randomness).  Randomness lives only in ``roll_event``,
which takes a caller-owned ``random.Random`` so runs are reproducible from a seed.

Turn loop (one turn = one sol)::

    state = new_state("moon", "normal")
    rng = random.Random(seed)
    while state.status == RUNNING:
        event = roll_event(state, rng, solar_activity)         # decided up front ...
        hint = forecast(state, event)                            # ... but only visible if comms are working
        state = step_sol(state, {"life_support": 10, "shielding": 4, "comms": 3, "science": 2}, event)

Exactly three core resources exist (power, life support with oxygen and food, shielding).  ``crew_health`` is a
vital sign, not a resource.  Communications and Science are only power allocations.
Every balance number is in ``outpost_config`` (game-balance decisions, not NASA measurements).
Messages carry i18n *keys* plus parameters, never display text, so the UI can show them in English or Arabic.
"""
import random
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from . import outpost_config as C

RUNNING, WON, LOST = "running", "won", "lost"


@dataclass(frozen=True)
class OutpostState:
    sol: int                         # the sol about to be played (1-based)
    power: float                     # core resource 1: battery
    oxygen: float                    # core resource 2: life support, sub-value
    food: float                      # core resource 2: life support, sub-value
    shielding: float                 # core resource 3
    crew_health: float               # vital sign (not a resource)
    score: float
    site: str = "moon"
    difficulty: str = "normal"
    dust_left: int = 0               # sols of reduced power generation still to come
    dust_factor: float = 1.0         # generation multiplier while dust_left > 0
    comms_level: int = 0             # comms power that worked last sol (0 during a blackout): sets forecast detail
    comms_down_left: int = 0         # sols of communications blackout still to come
    recent_events: Tuple[str, ...] = ()          # the last sols' events ("" = quiet sol), used by the fairness rules
    status: str = RUNNING
    fail_reason: Optional[str] = None            # "oxygen" | "food" | "crew_health" when lost
    log: Tuple[Tuple[str, Dict[str, Any]], ...] = ()   # (i18n key, params) of the sol just played

    @property
    def total_sols(self) -> int:
        return C.DIFFICULTY[self.difficulty]["sols"]

    @property
    def comms_ok(self) -> bool:
        """True when communications are good enough for at least a basic forecast."""
        return self.comms_level >= C.COMMS_FORECAST_MIN


# ---------------------------------------------------------------------------------------------- read-only helpers
def new_state(site: str = "moon", difficulty: str = "normal") -> OutpostState:
    if site not in C.SITES:
        raise ValueError(f"site must be one of {tuple(C.SITES)}")
    if difficulty not in C.DIFFICULTY:
        raise ValueError(f"difficulty must be one of {tuple(C.DIFFICULTY)}")
    return OutpostState(sol=1, power=float(C.DIFFICULTY[difficulty]["start_power"]), oxygen=C.START["oxygen"],
                        food=C.START["food"], shielding=C.START["shielding"], crew_health=C.START["crew_health"],
                        score=0.0, site=site, difficulty=difficulty, comms_level=C.START["comms_level"])


def life_support(state: OutpostState) -> float:
    """Life Support level = its weakest sub-value, so neglecting either oxygen or food shows."""
    return min(state.oxygen, state.food)


def resources(state: OutpostState) -> Dict[str, float]:
    return {"power": state.power, "life_support": life_support(state), "shielding": state.shielding}


def generation(state: OutpostState) -> int:
    """Power produced this sol (reduced while a dust storm lingers)."""
    f = state.dust_factor if state.dust_left > 0 else 1.0
    return round(C.SITES[state.site]["gen"] * f)


def is_blackout(state: OutpostState) -> bool:
    return int(state.power) + generation(state) < C.BASE_LOAD


def available_power(state: OutpostState) -> int:
    """Power that may be allocated this sol (0 = blackout: even the base load cannot be paid)."""
    return 0 if is_blackout(state) else int(state.power) + generation(state) - C.BASE_LOAD


def forecast(state: OutpostState, event: Optional[str]) -> Optional[str]:
    """Strong forecast: the exact event id, only when last sol's comms power reached COMMS_FORECAST_FULL."""
    if event is None or state.status != RUNNING or state.comms_level < C.COMMS_FORECAST_FULL:
        return None
    return event


def forecast_hint(state: OutpostState, event: Optional[str]) -> Optional[str]:
    """Basic forecast: only the event's CATEGORY (radiation, weather, damage, comms, opportunity), available from
    COMMS_FORECAST_MIN.  The player learns what kind of thing is coming, not exactly what or how bad.
    Below that level, or with no event due, nothing is revealed.  Pure: never changes any state."""
    if event is None or state.status != RUNNING or not state.comms_ok:
        return None
    return C.EVENTS[event]["category"]


def rating(state: OutpostState) -> int:
    """0 unless the mission was won; then 1-3 stars from the average score per sol."""
    if state.status != WON:
        return 0
    lo, hi = C.SCORE["stars_per_sol"]
    per_sol = state.score / state.total_sols
    return 1 + (per_sol >= lo) + (per_sol >= hi)


def failure_key(state: OutpostState) -> Optional[str]:
    """i18n key of the educational explanation shown when the mission is lost."""
    return f"op_fail_{state.fail_reason}" if state.status == LOST and state.fail_reason else None


def failure_explanation(state: OutpostState, lang: Optional[str] = None) -> str:
    """Educational, localized explanation of why the mission failed ('' if it did not fail)."""
    key = failure_key(state)
    if key is None:
        return ""
    from . import i18n
    return i18n.t(key, lang)


# ---------------------------------------------------------------------------------------------- randomness
def _is_hazard(eid: str) -> bool:
    return C.EVENTS[eid]["kind"] == "hazard"


def _last(hist: Tuple[str, ...], n: int) -> Tuple[str, ...]:
    """The last n entries of the event history (empty for n <= 0)."""
    return hist[max(0, len(hist) - n):] if n > 0 else ()


def eligible_events(state: OutpostState) -> List[str]:
    """Events allowed this sol under the fairness rules (the pool ``roll_event`` draws from)."""
    d = C.DIFFICULTY[state.difficulty]
    hist = state.recent_events
    streak = 0                                              # hazards in a row, newest first
    for e in reversed(hist):
        if e and _is_hazard(e):
            streak += 1
        else:
            break
    recent_high = any(e and _is_hazard(e) and C.EVENTS[e]["severity"] == "high"
                      for e in _last(hist, C.FAIRNESS["high_hazard_gap"] - 1))
    out = []
    for eid, ev in C.EVENTS.items():
        if state.sol < ev["min_sol"]:
            continue
        if eid in _last(hist, ev["cooldown"]):
            continue
        if ev["kind"] == "hazard":
            if state.sol <= d["grace_sols"] or streak >= d["max_consecutive_hazards"]:
                continue
            if ev["severity"] == "high" and recent_high:
                continue
        out.append(eid)
    return out


def event_chance(state: OutpostState) -> float:
    """Chance that something happens this sol: difficulty base, rising slightly through the mission."""
    base = C.DIFFICULTY[state.difficulty]["event_chance"]
    progress = (state.sol - 1) / max(1, state.total_sols - 1)
    chance = base * (1.0 + C.FAIRNESS["chance_ramp"] * min(1.0, progress))
    if state.recent_events and state.recent_events[-1] and _is_hazard(state.recent_events[-1]):
        chance *= C.FAIRNESS["after_hazard_chance_mult"]
    return min(C.FAIRNESS["max_chance"], chance)


def event_weights(state: OutpostState, solar_activity: float = C.SOLAR_ACTIVITY_DEFAULT) -> Dict[str, float]:
    """Relative weight of every eligible event this sol (difficulty, site and solar activity applied)."""
    activity = max(0.0, min(1.0, float(solar_activity)))
    d = C.DIFFICULTY[state.difficulty]
    weights = {}
    for eid in eligible_events(state):
        ev = C.EVENTS[eid]
        w = ev["weight"] * C.SITES[state.site]["event_weight"].get(eid, 1.0)
        w *= d["hazard_mult"] if ev["kind"] == "hazard" else d["opportunity_mult"]
        if eid == "solar_storm":
            w *= 1.0 + activity * C.SOLAR_ACTIVITY_WEIGHT_GAIN
        weights[eid] = w
    return weights


def roll_event(state: OutpostState, rng: random.Random,
               solar_activity: float = C.SOLAR_ACTIVITY_DEFAULT) -> Optional[str]:
    """Pick this sol's event (or None).  Always consumes exactly two numbers from ``rng`` so a seed lines up sol by
    sol however the player plays; which event comes depends on the state through the fairness rules."""
    u_happen, u_pick = rng.random(), rng.random()
    if u_happen >= event_chance(state):
        return None
    weights = event_weights(state, solar_activity)
    total = sum(weights.values())
    if total <= 0:
        return None
    target, acc = u_pick * total, 0.0
    for eid, w in weights.items():
        acc += w
        if target < acc:
            return eid
    return eid                                              # float rounding: fall back to the last candidate


# ---------------------------------------------------------------------------------------------- the turn
def validate_allocation(state: OutpostState, allocation: Dict[str, int]) -> Dict[str, int]:
    """Return a complete allocation dict or raise ValueError."""
    unknown = set(allocation) - set(C.ALLOCATIONS)
    if unknown:
        raise ValueError(f"Unknown allocation categories: {sorted(unknown)}")
    out = {}
    for k in C.ALLOCATIONS:
        v = allocation.get(k, 0)
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"Allocation '{k}' must be a non-negative integer")
        if v > C.ALLOC_LIMIT[k]:
            raise ValueError(f"Allocation '{k}' is limited to {C.ALLOC_LIMIT[k]}")
        out[k] = v
    if sum(out.values()) > available_power(state):
        raise ValueError(f"Allocated {sum(out.values())} but only {available_power(state)} power is available")
    return out


def _clamp(v: float, hi: float) -> float:
    return max(0.0, min(hi, v))


def step_sol(state: OutpostState, allocation: Dict[str, int], event: Optional[str] = None,
             ls_focus: float = C.LS_FOCUS_DEFAULT) -> OutpostState:
    """Play one sol and return the new state.  ``ls_focus`` (0..1) sends Life Support power to oxygen (1) or food (0)."""
    if state.status != RUNNING:
        raise RuntimeError("The outpost mission is over")
    if event is not None and (not isinstance(event, str) or event not in C.EVENTS):
        raise ValueError(f"Unknown event: {event!r}")
    alloc = validate_allocation(state, allocation)                                    # 1. validate
    focus = _clamp(float(ls_focus), 1.0)
    msgs = []
    blackout = is_blackout(state)

    # 2. power consumption: the base load first, then the allocations; leftovers charge the battery
    pool = 0.0 if blackout else state.power + generation(state) - C.BASE_LOAD
    power = pool - sum(alloc.values())
    if blackout:
        msgs.append(("op_msg_blackout", {}))

    # 3. oxygen and food consumption
    oxygen = state.oxygen - C.CONSUME["oxygen"]
    food = state.food - C.CONSUME["food"]

    # 4. allocation benefits
    oxygen += alloc["life_support"] * focus * C.LIFE_SUPPORT_RATE["oxygen"]
    food += alloc["life_support"] * (1.0 - focus) * C.LIFE_SUPPORT_RATE["food"]
    shielding = state.shielding + alloc["shielding"] * C.SHIELD_RATE
    science = alloc["science"]
    link_down = state.comms_down_left > 0
    comms = 0 if link_down else alloc["comms"]            # during a blackout the comms power is simply wasted

    # 5. shielding effects: wear every sol
    shielding -= C.SHIELD_WEAR

    # 6. event effects
    health_hit = 0.0
    bonus_score = 0.0
    dust_left = max(0, state.dust_left - 1)
    dust_factor = state.dust_factor if dust_left > 0 else 1.0
    down_left = max(0, state.comms_down_left - 1)
    blackout_started = False
    if event:
        ev = C.EVENTS[event]
        sev = C.DIFFICULTY[state.difficulty]["severity_mult"]
        msgs.append(("op_event_" + event, {}))
        if "radiation" in ev:
            leak = max(0.0, ev["radiation"] * sev - _clamp(shielding, C.CAP["shielding"]) * C.RADIATION_ABSORB)
            if leak > 0:
                h = C.RADIATION_HARM
                oxygen -= leak * h["life_support"]
                food -= leak * h["life_support"]
                power -= leak * h["power"]
                shielding -= leak * h["shielding"]
                health_hit += leak * C.HEALTH["radiation_penalty"]
            msgs.append(("op_msg_radiation_blocked" if leak == 0 else "op_msg_radiation_leaked",
                         {"leak": round(leak)}))
        if "dust_sols" in ev:                              # stacks: longest duration, weakest factor
            dust_left = max(dust_left, ev["dust_sols"])
            dust_factor = min(dust_factor, ev["dust_factor"])
        if "shield_damage" in ev:
            shielding -= ev["shield_damage"] * sev
        if "battery_loss" in ev:
            power -= ev["battery_loss"] * sev
        if "oxygen_leak" in ev:
            oxygen -= ev["oxygen_leak"] * sev
        if "food_loss" in ev:
            food -= ev["food_loss"] * sev
        if "comms_down_sols" in ev:
            down_left, blackout_started = max(down_left, ev["comms_down_sols"]), True
        if "bonus" in ev:
            power += ev["bonus"]["power"]
            shielding += ev["bonus"]["shielding"]
        if "discovery" in ev:
            d = ev["discovery"]
            got = d["score"] if science >= d["min_science"] else d["missed"]
            bonus_score += got
            msgs.append(("op_msg_discovery" if science >= d["min_science"] else "op_msg_discovery_small",
                         {"points": got}))
        if "resupply" in ev:
            if comms >= C.COMMS_WINDOW_MIN:
                oxygen += ev["resupply"]["oxygen"]
                food += ev["resupply"]["food"]
                msgs.append(("op_msg_resupply_received", {}))
            else:
                msgs.append(("op_msg_resupply_missed", {}))

    power, shielding = _clamp(power, C.CAP["power"]), _clamp(shielding, C.CAP["shielding"])
    oxygen, food = _clamp(oxygen, C.CAP["oxygen"]), _clamp(food, C.CAP["food"])

    # 7. crew health
    if oxygen < C.LOW_LEVEL:
        health_hit += C.HEALTH["low_supply_penalty"]
        msgs.append(("op_msg_low_oxygen", {}))
    if food < C.LOW_LEVEL:
        health_hit += C.HEALTH["low_supply_penalty"]
        msgs.append(("op_msg_low_food", {}))
    if blackout:
        health_hit += C.HEALTH["blackout_penalty"]
    health = state.crew_health - health_hit
    if health_hit == 0 and min(oxygen, food) >= C.HEALTH["recovery_min_supply"]:
        health += C.HEALTH["recovery"]
    health = _clamp(health, C.CAP["crew_health"])
    if health_hit > 0:
        msgs.append(("op_msg_health_down", {}))

    # 10. mission status (evaluated before scoring so a lost sol earns nothing)
    status, reason = RUNNING, None
    for name, value in (("oxygen", oxygen), ("food", food), ("crew_health", health)):
        if value <= C.LOSE_AT[name]:
            status, reason = LOST, name
            break

    # 8. score, 9. advance the sol
    score = state.score
    sol = state.sol + 1
    if status == RUNNING:
        score += C.SCORE["per_sol"] + science * C.SCORE["science"] + health * C.SCORE["health"] + bonus_score
        if sol > state.total_sols:
            status = WON
            score += C.SCORE["win_bonus"]
            msgs.append(("op_msg_won", {}))
    else:
        msgs.append(("op_msg_lost", {}))

    return replace(state, sol=sol, power=power, oxygen=oxygen, food=food, shielding=shielding, crew_health=health,
                   score=round(score, C.SCORE["decimals"]), dust_left=dust_left, dust_factor=dust_factor if dust_left > 0 else 1.0,
                   comms_level=0 if (blackout_started or down_left > 0 or link_down) else comms,
                   comms_down_left=down_left,
                   recent_events=_last(state.recent_events + (event or "",), C.FAIRNESS["history"]),
                   status=status, fail_reason=reason, log=tuple(msgs))
