"""Astronaut suit systems: oxygen and tool batteries.  Pure logic (no Ursina), fully testable.

* Oxygen drains while the astronaut is outside (faster when walking), never inside the pressurised habitat,
  and is refilled at the habitat's oxygen station.  Crossing 30% / 15% / 0% raises events the game turns into
  warnings, alarm sounds and (at 0%) an emergency return to the habitat.
* Every tool has a battery.  A successful use costs charge; batteries trickle back slowly and are fully
  recharged at the habitat's tool locker.
"""
from typing import Dict, List

DRAIN_REST = 0.06          # percent of a full tank per second (standing still, normal difficulty)
DRAIN_WALK = 0.15          # percent per second while walking  (~11 minutes of continuous walking)
TIER_DRAIN = {"easy": 0.6, "normal": 1.0, "hard": 1.3}
LOW, CRITICAL = 30.0, 15.0
REFILL_RATE = 20.0         # percent per second at the oxygen station
EMERGENCY_O2 = 40.0        # oxygen left after the emergency return
TOOL_COST = {"scanner": 10.0, "sampler": 20.0, "analyzer": 20.0, "wrench": 25.0}
TRICKLE = 0.25             # tool battery percent per second regained outside the locker


class Suit:
    def __init__(self, tier: str = "normal"):
        self.tier = tier
        self.oxygen = 100.0
        self.charges: Dict[str, float] = {t: 100.0 for t in TOOL_COST}
        self.emergencies = 0
        self.seconds_outside = 0.0
        self._fired = set()

    # ---- oxygen
    @property
    def status(self) -> str:
        if self.oxygen <= 0:
            return "empty"
        if self.oxygen <= CRITICAL:
            return "critical"
        if self.oxygen <= LOW:
            return "low"
        return "ok"

    def tick(self, dt: float, moving: bool, inside: bool) -> List[str]:
        """Advance the suit by dt seconds. Returns newly raised events: 'low', 'critical', 'empty'."""
        events = []
        if not inside:
            self.seconds_outside += dt
            rate = (DRAIN_WALK if moving else DRAIN_REST) * TIER_DRAIN.get(self.tier, 1.0)
            self.oxygen = max(0.0, self.oxygen - rate * dt)
            for name, limit in (("low", LOW), ("critical", CRITICAL), ("empty", 0.0)):
                if self.oxygen <= limit and name not in self._fired:
                    self._fired.add(name)
                    events.append(name)
            for t in self.charges:
                self.charges[t] = min(100.0, self.charges[t] + TRICKLE * dt)
        return events

    def refill(self, dt: float) -> bool:
        """Refill from the station for dt seconds. True once the tank is full."""
        self.oxygen = min(100.0, self.oxygen + REFILL_RATE * dt)
        if self.oxygen > LOW:
            self._fired.discard("low")
        if self.oxygen > CRITICAL:
            self._fired.discard("critical")
        if self.oxygen > 0:
            self._fired.discard("empty")
        return self.oxygen >= 100.0

    def emergency_reset(self):
        self.emergencies += 1
        self.oxygen = EMERGENCY_O2
        self._fired.clear()

    # ---- tools
    def can_use(self, tool: str) -> bool:
        return self.charges.get(tool, 100.0) >= TOOL_COST.get(tool, 0.0)

    def consume(self, tool: str):
        self.charges[tool] = max(0.0, self.charges[tool] - TOOL_COST.get(tool, 0.0))

    def recharge_all(self) -> bool:
        """Top up every battery. Returns True if anything actually needed charging."""
        needed = any(v < 99.9 for v in self.charges.values())
        for t in self.charges:
            self.charges[t] = 100.0
        return needed
