"""Mission data and the pure-Python mission state machine (no engine imports)."""
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from . import i18n
from .content import MISSION_TEXT, pick

# tool id -> (display name, action it performs, hotkey)
TOOLS = {
    "scanner": ("Scanner", "scan", "1"),
    "sampler": ("Sample Collector", "collect", "2"),
    "analyzer": ("Spectrometer", "analyze", "3"),
    "wrench": ("Repair Kit", "repair", "4"),
}
TOOL_ORDER = ["scanner", "sampler", "analyzer", "wrench"]
OPTIONS_BY_TIER = {"easy": 2, "normal": 3, "hard": 4}


@dataclass(frozen=True)
class RepairOption:
    text: str
    correct: bool
    explanation: str


@dataclass(frozen=True)
class WorldObject:
    id: str
    name: str
    shape: str                      # 'cube' | 'sphere'
    pos: Tuple[float, float]        # x, z
    size: Tuple[float, float, float]
    color: Tuple[float, float, float]
    fact: str = ""                  # revealed by scanner
    analysis: str = ""              # revealed by spectrometer after collection
    fault: str = ""                 # diagnosis shown for repairable objects
    options: Tuple[RepairOption, ...] = ()


@dataclass(frozen=True)
class Objective:
    id: str
    action: str                     # scan | collect | analyze | repair
    target: str
    text: str
    xp: int = 20


@dataclass(frozen=True)
class Mission:
    id: str
    name: str
    planet_color: Tuple[float, float, float]
    map_pos: Tuple[float, float]
    requires: Optional[str]
    ground_color: Tuple[float, float, float]
    sky_color: Tuple[float, float, float]
    briefing: str
    science_focus: str
    objects: Tuple[WorldObject, ...]
    objectives: Tuple[Objective, ...]
    bonus_xp: int = 50

    def get_object(self, obj_id: str) -> WorldObject:
        for o in self.objects:
            if o.id == obj_id:
                return o
        raise KeyError(obj_id)


def _std(scan_id, sample_id, fix_id, objs, lang):
    n = {o.id: o.name for o in objs}
    T = lambda k, **kw: i18n.t(k, lang, **kw)
    return (
        Objective("scan_site", "scan", scan_id, T("obj_scan", name=n[scan_id])),
        Objective("collect", "collect", sample_id, T("obj_collect", name=n[sample_id])),
        Objective("analyze", "analyze", sample_id, T("obj_analyze", name=n[sample_id])),
        Objective("diagnose", "scan", fix_id, T("obj_diagnose", name=n[fix_id])),
        Objective("repair", "repair", fix_id, T("obj_repair", name=n[fix_id]), xp=30),
    )


# Layout / geometry (language independent): id -> (shape, pos, size, colour, has_fault)
_GEOM = {
    "moon": {"solar_array": ("cube", (10, 8), (5, 2.2, 0.6), (0.2, 0.3, 0.7)),
             "regolith": ("sphere", (-9, 6), (2.5, 1.2, 2.5), (0.55, 0.55, 0.55)),
             "power_relay": ("cube", (2, -12), (2, 2.5, 2), (0.8, 0.45, 0.1))},
    "mars": {"riverbed": ("cube", (12, 6), (6, 1.2, 3), (0.6, 0.35, 0.25)),
             "clay_rock": ("sphere", (-8, 9), (2.2, 1.5, 2.2), (0.7, 0.45, 0.35)),
             "rover": ("cube", (0, -11), (3, 1.5, 2), (0.85, 0.85, 0.85))},
    "orbital": {"earth_window": ("cube", (11, 5), (0.5, 4, 5), (0.3, 0.6, 0.9)),
                "plant_rack": ("cube", (-9, 7), (2, 3, 1.5), (0.2, 0.7, 0.3)),
                "scrubber": ("cube", (1, -12), (2, 3, 2), (0.7, 0.7, 0.75))},
    "europa": {"ice_ridge": ("cube", (11, 7), (7, 2.0, 2), (0.75, 0.88, 0.95)),
               "salt_ice": ("sphere", (-8, 8), (2.4, 1.6, 2.4), (0.8, 0.8, 0.7)),
               "drill": ("cube", (0, -12), (1.5, 4, 1.5), (0.9, 0.5, 0.1))},
}
# id -> (planet colour, map position, requires, ground colour, sky colour, (scan, sample, fix))
_LAYOUT = {
    "moon": ((0.75, 0.75, 0.78), (-0.55, -0.1), None, (0.45, 0.45, 0.47), (0.0, 0.0, 0.03), ("solar_array", "regolith", "power_relay")),
    "mars": ((0.8, 0.35, 0.2), (-0.2, 0.2), "moon", (0.62, 0.32, 0.2), (0.45, 0.28, 0.2), ("riverbed", "clay_rock", "rover")),
    "orbital": ((0.25, 0.5, 0.9), (0.2, -0.1), "mars", (0.7, 0.72, 0.78), (0.02, 0.02, 0.08), ("earth_window", "plant_rack", "scrubber")),
    "europa": ((0.7, 0.85, 0.95), (0.55, 0.15), "orbital", (0.8, 0.85, 0.9), (0.03, 0.03, 0.06), ("ice_ridge", "salt_ice", "drill")),
}
ORDER = ("moon", "mars", "orbital", "europa")


def _build_object(mid, oid, lang, age):
    shape, pos, size, col = _GEOM[mid][oid]
    spec = MISSION_TEXT[mid]["objects"][oid]
    opts = tuple(RepairOption(pick(t, lang, age), i == 0, pick(e, lang, age))
                 for i, (t, e) in enumerate(spec.get("options", [])))
    g = lambda k: pick(spec[k], lang, age) if k in spec else ""
    return WorldObject(oid, pick(spec["name"], lang, age), shape, pos, size, col,
                       fact=g("fact"), analysis=g("analysis"), fault=g("fault"), options=opts)


def _build_missions(lang="en", age="mid") -> Tuple[Mission, ...]:
    out = []
    for mid in ORDER:
        planet, mpos, req, ground, sky, (a, b, c) = _LAYOUT[mid]
        txt = MISSION_TEXT[mid]
        objs = tuple(_build_object(mid, oid, lang, age) for oid in _GEOM[mid])
        out.append(Mission(mid, pick(txt["name"], lang, age), planet, mpos, req, ground, sky,
                           pick(txt["briefing"], lang, age), pick(txt["science"], lang, age),
                           objs, _std(a, b, c, objs, lang)))
    return tuple(out)


@lru_cache(maxsize=16)
def get_missions(lang="en", age="mid") -> Tuple[Mission, ...]:
    """Missions with all text localized (cached)."""
    return _build_missions(lang, age)


def deep_dive(mission_id: str, lang="en") -> str:
    return pick(MISSION_TEXT[mission_id]["deep"], lang, "teen")


MISSIONS: Tuple[Mission, ...] = get_missions("en", "mid")
MISSIONS_BY_ID: Dict[str, Mission] = {m.id: m for m in MISSIONS}


def is_unlocked(mission: Mission, completed: set) -> bool:
    return mission.requires is None or mission.requires in completed


@dataclass
class ActionResult:
    ok: bool
    message: str
    xp: int = 0
    needs_choice: bool = False
    target: Optional[str] = None
    completed_objective: Optional[str] = None


class MissionState:
    """Tracks one playthrough of a mission. Pure logic, fully testable.
    ``lang``/``age`` only affect the wording of messages (the rules are identical)."""

    def __init__(self, mission: Mission, tier: str = "normal", lang: str = "en", age: str = "mid"):
        self.mission = mission
        self.tier = tier
        self.lang = lang
        self.age = age
        self.done = set()           # objective ids
        self.collected = set()      # object ids
        self.scanned = set()
        self.evidence: List[str] = []
        self.mistakes = 0
        self.hints = 0
        self.base_xp = 0
        self.lab_bonus_done = False

    def T(self, key, **kw):
        return i18n.t(key, self.lang, **kw)

    # -- queries --------------------------------------------------------
    def _objective_available(self, obj: Objective) -> bool:
        if obj.id in self.done:
            return False
        if obj.action == "analyze":
            return obj.target in self.collected
        if obj.action == "repair":
            return obj.target in self.scanned
        return True

    def available_objectives(self) -> List[Objective]:
        return [o for o in self.mission.objectives if self._objective_available(o)]

    @property
    def complete(self) -> bool:
        return len(self.done) == len(self.mission.objectives)

    def next_objective(self) -> Optional[Objective]:
        avail = self.available_objectives()
        return avail[0] if avail else None

    def _find(self, action: str, target: str) -> Optional[Objective]:
        for o in self.mission.objectives:
            if o.action == action and o.target == target:
                return o
        return None

    def _finish(self, obj: Objective, message: str) -> ActionResult:
        self.done.add(obj.id)
        self.base_xp += obj.xp
        return ActionResult(True, message, xp=obj.xp, target=obj.target, completed_objective=obj.id)

    def _log(self, text: str):
        if text and text not in self.evidence:
            self.evidence.append(text)

    # -- actions --------------------------------------------------------
    def use_tool(self, tool: str, obj_id: Optional[str]) -> ActionResult:
        T = self.T
        if tool not in TOOLS:
            return ActionResult(False, T("unknown_tool"))
        if not obj_id:
            return ActionResult(False, T("aim_at"))
        obj = self.mission.get_object(obj_id)
        action = TOOLS[tool][1]

        if action == "scan":
            first = obj_id not in self.scanned
            self.scanned.add(obj_id)
            self._log(T("ev_fact", name=obj.name, fact=obj.fact))
            if obj.fault:
                self._log(T("ev_diag", name=obj.name, fault=obj.fault))
            o = self._find("scan", obj_id)
            if o and o.id not in self.done:
                return self._finish(o, T("scanned_msg", name=obj.name, fact=obj.fact))
            return ActionResult(True, T("ev_fact", name=obj.name, fact=obj.fact) if first
                                else T("already_scanned", name=obj.name), target=obj_id)

        if action == "collect":
            o = self._find("collect", obj_id)
            if not o:
                return ActionResult(False, T("nothing_collect", name=obj.name), target=obj_id)
            if o.id in self.done:
                return ActionResult(False, T("sample_done"), target=obj_id)
            self.collected.add(obj_id)
            return self._finish(o, T("sample_ok", name=obj.name))

        if action == "analyze":
            o = self._find("analyze", obj_id)
            if not o:
                return ActionResult(False, T("nothing_analyze", name=obj.name), target=obj_id)
            if obj_id not in self.collected:
                return ActionResult(False, T("collect_first"), target=obj_id)
            if o.id in self.done:
                return ActionResult(False, T("already_analyzed"), target=obj_id)
            self._log(T("ev_analysis", name=obj.name, text=obj.analysis))
            return self._finish(o, T("analysis_msg", text=obj.analysis))

        if action == "repair":
            o = self._find("repair", obj_id)
            if not o:
                return ActionResult(False, T("no_repair", name=obj.name), target=obj_id)
            if o.id in self.done:
                return ActionResult(False, T("already_repaired"), target=obj_id)
            if obj_id not in self.scanned:
                self.mistakes += 1
                return ActionResult(False, T("diagnose_first"), target=obj_id)
            return ActionResult(True, obj.fault, needs_choice=True, target=obj_id)

        return ActionResult(False, T("nothing_happened"))

    def repair_options(self, obj_id: str) -> List[Tuple[int, RepairOption]]:
        """Options shown for this difficulty: the correct fix plus tier-limited distractors."""
        obj = self.mission.get_object(obj_id)
        limit = OPTIONS_BY_TIER[self.tier]
        indexed = list(enumerate(obj.options))
        correct = [p for p in indexed if p[1].correct]
        wrong = [p for p in indexed if not p[1].correct][: max(0, limit - len(correct))]
        return sorted(correct + wrong, key=lambda p: p[0])

    def repair(self, obj_id: str, option_index: int) -> ActionResult:
        obj = self.mission.get_object(obj_id)
        o = self._find("repair", obj_id)
        if not o or o.id in self.done or obj_id not in self.scanned:
            return ActionResult(False, self.T("repair_impossible"), target=obj_id)
        opt = obj.options[option_index]
        if opt.correct:
            self._log(self.T("ev_fix", name=obj.name, expl=opt.explanation))
            return self._finish(o, self.T("repaired", expl=opt.explanation))
        self.mistakes += 1
        key = "wont_work_young" if self.age == "young" else "wont_work"
        return ActionResult(False, self.T(key, expl=opt.explanation), target=obj_id)

    def hint(self) -> str:
        """Hint detail adapts to difficulty tier (and wording to age). Using a hint is tracked."""
        self.hints += 1
        o = self.next_objective()
        if o is None:
            return self.T("hint_done")
        obj = self.mission.get_object(o.target)
        tool = self.T("tool_" + {"scan": "scanner", "collect": "sampler",
                                 "analyze": "analyzer", "repair": "wrench"}[o.action])
        suffix = "_young" if self.age == "young" else ""
        if self.tier == "easy":
            return self.T("hint_easy" + suffix, obj=obj.name, tool=tool)
        if self.tier == "normal":
            return self.T("hint_normal" + suffix, tool=tool)
        return self.T("hint_hard" + suffix)

    # -- habitat laboratory ----------------------------------------------
    LAB_BONUS_XP = 10

    def lab_analyze(self) -> ActionResult:
        """Use the habitat's scientific analyzer on the samples collected so far.
        Analyses any pending sample (same result as the Spectrometer); once everything is analyzed it gives a
        one-time detailed-report bonus.  Never changes what the mission requires."""
        T = self.T
        if not self.collected:
            return ActionResult(False, T("lab_no_sample"))
        pending = [o for o in self.mission.objectives
                   if o.action == "analyze" and o.id not in self.done and o.target in self.collected]
        if pending:
            o = pending[0]
            obj = self.mission.get_object(o.target)
            self._log(T("ev_analysis", name=obj.name, text=obj.analysis))
            return self._finish(o, T("lab_report", text=obj.analysis))
        if not self.lab_bonus_done:
            self.lab_bonus_done = True
            self.base_xp += self.LAB_BONUS_XP
            obj = self.mission.get_object(sorted(self.collected)[0])
            self._log(T("ev_lab", name=obj.name, text=obj.analysis))
            return ActionResult(True, T("lab_bonus", text=obj.analysis, xp=self.LAB_BONUS_XP), xp=self.LAB_BONUS_XP,
                                target=obj.id)
        return ActionResult(False, T("lab_done"))
