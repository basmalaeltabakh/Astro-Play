"""Outpost Command: EVERY gameplay balance number lives in this one file.

GAME-BALANCE DECISIONS, NOT NASA MEASUREMENTS.  All values are provisional, abstract "game units" picked for
playability and should be tuned by playtesting.  They must never be shown to players as real-world figures.
Real data (e.g. solar activity from DONKI) may only enter the simulation through the ``solar_activity``
argument (0..1) of ``outpost.roll_event``.

The game has exactly THREE core resources:
  * power          (battery)
  * life_support   (sub-values: oxygen and food)
  * shielding      (radiation shielding integrity)
``crew_health`` is a status vital sign, not a resource: it cannot be allocated, produced or stored.
Communications and Science are *power allocation categories* only, never resources.
"""

RESOURCES = ("power", "life_support", "shielding")                 # the only three core resource categories
LIFE_SUPPORT_PARTS = ("oxygen", "food")                            # sub-values of life_support
ALLOCATIONS = ("life_support", "shielding", "comms", "science")    # where power can be spent each sol

# ------------------------------------------------------------------------------------------ mission & difficulty
# sols = mission duration; event_chance = base chance that some event happens in a sol; severity_mult scales hazard
# damage; hazard_mult / opportunity_mult scale the weights of harmful / helpful events; grace_sols = opening sols with
# no hazards; max_consecutive_hazards = most hazards allowed in a row (fairness rule, see FAIRNESS).
DIFFICULTY = {
    "easy":   {"sols": 8,  "event_chance": 0.55, "severity_mult": 1.0, "start_power": 30,
               "hazard_mult": 0.9, "opportunity_mult": 1.3, "grace_sols": 2, "max_consecutive_hazards": 1},
    "normal": {"sols": 10, "event_chance": 0.75, "severity_mult": 1.4, "start_power": 20,
               "hazard_mult": 1.2, "opportunity_mult": 1.0, "grace_sols": 1, "max_consecutive_hazards": 2},
    "hard":   {"sols": 12, "event_chance": 0.85, "severity_mult": 1.6, "start_power": 10,
               "hazard_mult": 1.3, "opportunity_mult": 0.8, "grace_sols": 1, "max_consecutive_hazards": 2},
}

# ------------------------------------------------------------------------------------------ sites
# gen = power generated per sol; event_weight multiplies an event's weight at that site (missing = 1.0).
SITES = {
    "moon": {"gen": 34, "event_weight": {"dust_storm": 0.2, "dust_accumulation": 1.3, "micrometeorite": 1.3}},
    "mars": {"gen": 28, "event_weight": {"dust_storm": 1.8, "dust_accumulation": 0.8, "micrometeorite": 0.5,
                                         "comms_window": 0.8}},
}

# ------------------------------------------------------------------------------------------ starting values
START = {"oxygen": 80.0, "food": 80.0, "shielding": 60.0, "crew_health": 100.0,
         "comms_level": 3}                        # sol 1 starts with a basic (category) forecast
CAP = {"power": 60.0, "oxygen": 100.0, "food": 100.0, "shielding": 100.0, "crew_health": 100.0}

# ------------------------------------------------------------------------------------------ daily rules
BASE_LOAD = 8                                    # power the habitat needs to stay alive; paid before allocations
CONSUME = {"oxygen": 6.0, "food": 4.0}           # used per sol by the whole crew
SHIELD_WEAR = 5.0                                # shielding integrity lost every sol

# Power allocation limits: the most power one category can usefully take in a sol (no all-in on one thing).
ALLOC_LIMIT = {"life_support": 20, "shielding": 16, "comms": 8, "science": 14}

# Gains per power unit spent
LIFE_SUPPORT_RATE = {"oxygen": 1.0, "food": 0.7}  # split by the player's oxygen/food focus
LS_FOCUS_DEFAULT = 0.5                           # 1.0 = all Life Support power to oxygen, 0.0 = all to food
LS_FOCUS_CHOICES = (1.0, LS_FOCUS_DEFAULT, 0.0)       # what the player can pick: oxygen focus, balanced, food focus
SHIELD_RATE = 1.5
SCIENCE_RATE = 1.0
COMMS_FORECAST_MIN = 3                           # comms units this sol: NEXT sol's event CATEGORY is forecast
COMMS_FORECAST_FULL = 5                          # comms units this sol: NEXT sol's exact EVENT is forecast
COMMS_WINDOW_MIN = 4                             # comms units needed to use a 'comms_window' resupply

# ------------------------------------------------------------------------------------------ crew health
LOW_LEVEL = 30.0                                 # oxygen or food below this hurts the crew (also the UI warning level)
HEALTH = {
    "low_supply_penalty": 8.0,                   # per sol, for EACH of oxygen / food below LOW_LEVEL
    "blackout_penalty": 6.0,                     # per sol with no power for the base load
    "radiation_penalty": 0.35,                   # per unabsorbed radiation point
    "recovery": 4.0,                             # per sol when nothing hurt the crew and oxygen & food are healthy
    "recovery_min_supply": 50.0,                 # oxygen and food must both be at least this to recover
}
LOSE_AT = {"oxygen": 0.0, "food": 0.0, "crew_health": 0.0}   # mission is lost when a value is at or below this

# ------------------------------------------------------------------------------------------ events
# ALL numbers here are FICTIONAL GAMEPLAY PARAMETERS, not real scientific predictions, probabilities or measurements.
#
# Per event:  kind (hazard | opportunity), category (shown in forecasts), severity (low | medium | high; used by the
#             fairness rules), weight (relative likelihood), min_sol (earliest sol), cooldown (sols before the same
#             event may repeat; 0 = no limit), plus effects (game units):
#   radiation        severity; shielding absorbs RADIATION_ABSORB per point, the rest harms the outpost
#   dust_sols/dust_factor   power generation multiplier for the following N sols (stacks: weakest factor wins)
#   shield_damage    direct shielding loss      battery_loss  direct power loss
#   oxygen_leak      direct oxygen loss         food_loss     direct food loss
#   comms_down_sols  communications are down for N sols: comms power is wasted and no forecast is possible
#   resupply         {oxygen, food} gained, but ONLY if comms units >= COMMS_WINDOW_MIN this sol
#   bonus            {power, shielding} gained, no conditions
#   discovery        score gained: "score" if science power >= "min_science" this sol, otherwise "missed"
# Hazard damage (not bonuses) is multiplied by the difficulty's severity_mult.
EVENTS = {
    "solar_storm":       {"kind": "hazard", "category": "radiation", "severity": "high", "weight": 1.6,
                          "min_sol": 2, "cooldown": 3, "radiation": 70},
    "micrometeorite":    {"kind": "hazard", "category": "damage", "severity": "medium", "weight": 1.0,
                          "min_sol": 1, "cooldown": 2, "shield_damage": 18},
    "dust_storm":        {"kind": "hazard", "category": "weather", "severity": "medium", "weight": 0.8,
                          "min_sol": 1, "cooldown": 4, "dust_sols": 2, "dust_factor": 0.5},
    "dust_accumulation": {"kind": "hazard", "category": "weather", "severity": "low", "weight": 0.8,
                          "min_sol": 1, "cooldown": 3, "dust_sols": 3, "dust_factor": 0.75},
    "equipment_fault":   {"kind": "hazard", "category": "damage", "severity": "medium", "weight": 1.0,
                          "min_sol": 1, "cooldown": 2, "battery_loss": 15, "oxygen_leak": 8},
    "crop_blight":       {"kind": "hazard", "category": "damage", "severity": "medium", "weight": 0.7,
                          "min_sol": 2, "cooldown": 3, "food_loss": 14},
    "comms_blackout":    {"kind": "hazard", "category": "comms", "severity": "low", "weight": 0.7,
                          "min_sol": 2, "cooldown": 4, "comms_down_sols": 2},
    "comms_window":      {"kind": "opportunity", "category": "opportunity", "severity": "low", "weight": 0.8,
                          "min_sol": 1, "cooldown": 2, "resupply": {"oxygen": 15, "food": 15}},
    "supply_cache":      {"kind": "opportunity", "category": "opportunity", "severity": "low", "weight": 0.6,
                          "min_sol": 1, "cooldown": 3, "bonus": {"power": 10, "shielding": 10}},
    "science_discovery": {"kind": "opportunity", "category": "opportunity", "severity": "low", "weight": 0.6,
                          "min_sol": 2, "cooldown": 3, "discovery": {"score": 30, "missed": 8, "min_science": 4}},
}
FORECAST_CATEGORIES = ("radiation", "weather", "damage", "comms", "opportunity")   # what a basic forecast can name
SOLAR_ACTIVITY_DEFAULT = 0.3                     # neutral default until real / archived DONKI data is supplied
SOLAR_ACTIVITY_WEIGHT_GAIN = 3.0                 # solar_storm weight *= 1 + activity * gain
RADIATION_ABSORB = 0.8                           # radiation absorbed per shielding point
RADIATION_HARM = {"life_support": 0.45, "power": 0.4, "shielding": 0.25}   # per unabsorbed point

# Fairness and pacing: keep runs varied but never unwinnable by bad luck alone.
FAIRNESS = {
    "history": 4,                                # how many past sols the engine remembers
    "chance_ramp": 0.25,                         # event chance grows by up to this fraction by the last sol
    "max_chance": 0.9,                           # event chance never exceeds this
    "after_hazard_chance_mult": 0.8,             # event chance right after a hazard (breathing room)
    "high_hazard_gap": 2,                        # a high-severity hazard needs this many sols since the previous one
}

# ------------------------------------------------------------------------------------------ score
SCORE = {
    "per_sol": 10,                               # for surviving a sol
    "science": 2.0,                              # per science power unit spent
    "health": 0.1,                               # per crew-health point at the end of each sol
    "win_bonus": 50,
    "decimals": 2,                               # score is rounded to this many decimals
    "stars_per_sol": (28, 36),                   # average score per sol needed (when winning) for 2 and 3 stars
}

# ------------------------------------------------------------------------------------------ NASA DONKI mapping
# DONKI = NASA's Space Weather Database Of Notifications, Knowledge, Information.  The game turns RECENT event COUNTS
# into one 0..1 "solar activity" number that only makes solar storms likelier (SOLAR_ACTIVITY_WEIGHT_GAIN above).
# The points below are a GAMEPLAY MAPPING, NOT a scientific index and NOT a space-weather forecast.
DONKI = {
    "endpoints": ("FLR", "CME", "GST", "SEP"),   # flares, coronal mass ejections, geomagnetic storms, particle events
    "window_days": 30,                           # how far back to look
    "cache_ttl_hours": 1,                        # a saved result this young is reused when OUTPOST opens; the Refresh button always asks NASA
    "timeout_s": (5, 15),                        # (connect, read) seconds per request
    "budget_s": 25,                              # give up on live data after this many seconds in total
    "points": {"flare_x": 4.0, "flare_m": 2.0, "flare_c": 0.5, "cme": 0.25, "gst": 2.0, "gst_strong": 2.0, "sep": 3.0},
    "gst_strong_kp": 7,                          # a geomagnetic storm with Kp at least this counts as strong
    "full_points": 160.0,                        # this many points in the window = maximum game solar activity (1.0)
    # Calibration (approved): 24 real, non-overlapping 30-day DONKI windows (2024-11-20 .. 2026-11-09). With the CME weight
    # at 0.25 and full_points 160, 5 of 24 windows saturate, the median level is 0.67, quiet windows average 0.45 and busy
    # ones 0.82, and CME entries alone reach at most 0.29. Gameplay parameters only, not NASA indices.
    "levels": (0.25, 0.6),                       # below the first: calm; below the second: active; else stormy
}

# ------------------------------------------------------------------------------------------ NASA OSDR (research cards)
# OSDR = NASA's Open Science Data Repository. These are access settings only: they never change simulation balance, and
# OSDR findings are never turned into game numbers or safety thresholds.
OSDR = {
    "timeout_s": (5, 20),                        # (connect, read) seconds per request
    "budget_s": 40,                              # give up on live data after this many seconds in total
    "cache_ttl_days": 1,                         # saved metadata younger than this is reused when OUTPOST opens; Refresh always asks NASA
    "page_size": 10,                             # studies fetched per page (the API itself has no pagination)
    "max_studies": 60,                           # most studies one refresh will fetch
    "description_chars": 600,                    # study description is cut at a sentence end near this length
    "topics": ("plants", "radiation", "microgravity", "health", "microbes"),
    # canonical metadata field paths of the official query endpoint (https://visualization.osdr.nasa.gov/biodata/api)
    "filters": {"organism": "study.characteristics.organism", "spaceflight": "study.factor value.spaceflight",
                "radiation": "study.factor value.ionizing radiation"},
    "spaceflight_values": ("Space Flight", "in-flight", "pre-flight", "post-flight"),   # factor values meaning "flew"
}

