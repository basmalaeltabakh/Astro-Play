"""Outpost Command game flow: everything the UI needs, with NO Ursina and no drawing.

  * ``BackgroundLoader``  runs slow work (NASA lookups) on worker threads and hands finished results back through a
                          queue. Workers never touch the UI: the game loop calls ``poll()`` and applies results itself.
  * ``NasaData``          the DONKI solar-activity snapshot and the OSDR research cards, with their loading state.
                          It starts from LOCAL data (cache / archive / offline dataset) so the game works offline,
                          and upgrades it when a background refresh succeeds.
  * ``OutpostSession``    one Outpost run: the simulation state, the player's allocation draft, forecast and effect
                          views, the consequence preview, and saving to / resuming from the ``outpost_runs`` table.

The simulation (``outpost.py``) stays pure: this module only calls it. Presentation strings live in ``i18n``; this
module returns keys, numbers and plain data. The pending event is private to the session: the UI can only see what the
forecast rules allow (``forecast_view``) or what already happened (``last_sol_view``).
"""
import dataclasses
import json
import queue
import random
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import fileio, nasa_data, osdr_data
from . import outpost as O
from . import outpost_config as C

NASA_JOBS = ("donki", "osdr")
STATES = ("idle", "loading", "ok", "error")


# ---------------------------------------------------------------------------------------------- saving a run
def state_to_json(state: O.OutpostState) -> str:
    return json.dumps(dataclasses.asdict(state), ensure_ascii=False)


def state_from_json(text: str) -> Optional[O.OutpostState]:
    """Rebuild a saved state, or None if it is damaged or inconsistent (never raises)."""
    try:
        d = json.loads(text)
        if not isinstance(d, dict):
            return None
        nums = ("power", "oxygen", "food", "shielding", "crew_health", "score", "dust_factor")
        ints = ("sol", "dust_left", "comms_level", "comms_down_left")
        if any(isinstance(d.get(k), bool) or not isinstance(d.get(k), (int, float)) for k in nums + ints):
            return None
        if d.get("site") not in C.SITES or d.get("difficulty") not in C.DIFFICULTY:
            return None
        if d.get("status") not in (O.RUNNING, O.WON, O.LOST) or int(d["sol"]) < 1:
            return None
        log = tuple((str(k), dict(p)) for k, p in d.get("log", ()))
        recent = tuple(str(x) for x in d.get("recent_events", ()))
        reason = d.get("fail_reason")
        if reason is not None and not isinstance(reason, str):
            return None
        return O.OutpostState(
            sol=int(d["sol"]), power=float(d["power"]), oxygen=float(d["oxygen"]), food=float(d["food"]),
            shielding=float(d["shielding"]), crew_health=float(d["crew_health"]), score=float(d["score"]),
            site=d["site"], difficulty=d["difficulty"], dust_left=int(d["dust_left"]),
            dust_factor=float(d["dust_factor"]), comms_level=int(d["comms_level"]),
            comms_down_left=int(d["comms_down_left"]), recent_events=recent, status=d["status"],
            fail_reason=reason, log=log)
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


# ---------------------------------------------------------------------------------------------- background work
class BackgroundLoader:
    """Runs named jobs on daemon threads. A job that is already running is never started twice. Results (or the
    name of the error) wait in a queue until the main thread calls ``poll``; nothing here touches the UI."""

    def __init__(self, inline: bool = False):
        self.inline = inline                       # run jobs immediately on the caller's thread (tests / no threads)
        self._lock = threading.Lock()
        self._running = set()
        self._done: "queue.Queue[Tuple[str, bool, Any]]" = queue.Queue()

    def start(self, name: str, fn: Callable[[], Any]) -> bool:
        with self._lock:
            if name in self._running:
                return False
            self._running.add(name)
        if self.inline:
            self._run(name, fn)
        else:
            threading.Thread(target=self._run, args=(name, fn), daemon=True, name=f"outpost-{name}").start()
        return True

    def _run(self, name: str, fn: Callable[[], Any]) -> None:
        try:
            item = (name, True, fn())
        except Exception as e:                      # a worker error must never crash the game
            item = (name, False, type(e).__name__)
        self._done.put(item)
        with self._lock:
            self._running.discard(name)

    def is_loading(self, name: Optional[str] = None) -> bool:
        with self._lock:
            return bool(self._running) if name is None else name in self._running

    def poll(self) -> List[Tuple[str, bool, Any]]:
        """Finished jobs since the last call: (name, ok, result or error name). Never blocks."""
        out = []
        while True:
            try:
                out.append(self._done.get_nowait())
            except queue.Empty:
                return out


class NasaData:
    """DONKI solar activity + OSDR research cards for the screens, with honest loading state."""

    def __init__(self, loader: Optional[BackgroundLoader] = None):
        self.loader = loader or BackgroundLoader()
        # Local files only (cache, archive, curated offline dataset): instant, and works with no internet.
        self.solar: nasa_data.SolarActivity = nasa_data.get_solar_activity(allow_network=False)
        self.studies: osdr_data.StudySet = osdr_data.get_studies(allow_network=False)
        self.state: Dict[str, str] = {k: "idle" for k in NASA_JOBS}
        self.error: Dict[str, Optional[str]] = {k: None for k in NASA_JOBS}
        self.checked_at: Dict[str, Optional[str]] = {k: None for k in NASA_JOBS}   # last time NASA was asked (ISO + offset)

    def refresh(self, force: bool = False) -> bool:
        """Ask NASA for fresh data in the background. Returns False if a refresh is already running.

        Entering Outpost Command refreshes normally (a recent cache is reused). ``force=True`` is the player's own
        Refresh button: the cache shortcut is skipped and NASA is always asked."""
        started = False
        for name, fn in (("donki", lambda: nasa_data.get_solar_activity(force=force)),
                         ("osdr", lambda: osdr_data.get_studies(force=force))):
            if self.loader.start(name, fn):
                self.state[name], self.error[name] = "loading", None
                started = True
        return started

    @property
    def loading(self) -> bool:
        return any(s == "loading" for s in self.state.values())

    def pump(self, now=None) -> bool:
        """Apply finished background results (call from the main thread). True if anything changed."""
        changed = False
        for name, ok, result in self.loader.poll():
            changed = True
            self.checked_at[name] = (fileio.as_aware(now) if now else fileio.local_now()).isoformat(timespec="seconds")
            if ok and name == "donki" and isinstance(result, nasa_data.SolarActivity):
                self.solar = result
                self._settle(name, "ok")
            elif ok and name == "osdr" and isinstance(result, osdr_data.StudySet):
                if not result.empty:                         # never replace saved cards with nothing
                    self.studies = result
                self._settle(name, "ok")
            else:
                self.error[name] = result if isinstance(result, str) else "bad result"
                self._settle(name, "error")
        return changed

    def _settle(self, name: str, state: str) -> None:
        """Record a finished job's outcome. If a NEWER job of the same name is already running (a result left over from an
        earlier visit), the data is still applied (it is valid) but the status stays 'loading' until that job finishes."""
        self.state[name] = "loading" if self.loader.is_loading(name) else state

    @property
    def unreachable(self) -> bool:
        """True when a finished refresh could only produce saved/default data (so the UI can say so)."""
        return (self.state["donki"] == "ok" and self.solar.source in (nasa_data.ARCHIVED, nasa_data.DEFAULT)) or \
               (self.state["osdr"] == "ok" and bool(self.studies.errors)) or "error" in self.state.values()


# ---------------------------------------------------------------------------------------------- one run
class OutpostSession:
    def __init__(self, db, profile_id: Optional[int], state: O.OutpostState, seed: int, solar_level: float,
                 solar_source: str, solar_as_of: Optional[str], run_id: Optional[int] = None,
                 history: Optional[List[dict]] = None):
        self.db, self.profile_id, self.state, self.seed = db, profile_id, state, int(seed)
        self.solar_level, self.solar_source, self.solar_as_of = solar_level, solar_source, solar_as_of
        self.history: List[dict] = list(history or [])
        self.focus = C.LS_FOCUS_DEFAULT
        self.alloc: Dict[str, int] = {k: 0 for k in C.ALLOCATIONS}
        # Each roll_event call consumes exactly two random numbers, so skipping 2 per played sol puts the stream back
        # exactly where it was: a resumed run sees the same events as one that was never interrupted.
        self.rng = random.Random(self.seed)
        for _ in range(state.sol - 1):
            self.rng.random()
            self.rng.random()
        self._event: Optional[str] = (O.roll_event(state, self.rng, solar_level)
                                      if state.status == O.RUNNING else None)
        self.run_id = run_id if run_id is not None else self._create()

    # ---- creating / resuming
    @classmethod
    def new(cls, db, profile_id, site: str, difficulty: str, solar: nasa_data.SolarActivity,
            seed: Optional[int] = None) -> "OutpostSession":
        db.abandon_unfinished_outpost_runs(profile_id)               # only one unfinished run per player
        seed = random.randrange(2 ** 31) if seed is None else int(seed)
        return cls(db, profile_id, O.new_state(site, difficulty), seed, solar.level, solar.source, solar.as_of)

    @classmethod
    def resume(cls, db, profile_id) -> Optional["OutpostSession"]:
        row = db.latest_unfinished_outpost_run(profile_id)
        if not row:
            return None
        state = state_from_json(row["state_json"])
        try:
            history = json.loads(row["history_json"])
        except ValueError:
            history = None
        if state is None or state.status != O.RUNNING or not isinstance(history, list) or len(history) != state.sol - 1:
            db.update_outpost_run(row["id"], status="abandoned", sol=row["sol"], score=row["score"], stars=0,
                                  fail_reason=row["fail_reason"], state_json=row["state_json"],
                                  history_json="[]")                  # a damaged save is retired, not trusted
            return None
        return cls(db, profile_id, state, row["seed"], row["solar_level"], row["solar_source"], row["solar_as_of"],
                   run_id=row["id"], history=history)

    def _create(self) -> int:
        return self.db.create_outpost_run(self.profile_id, self.state.site, self.state.difficulty, self.seed,
                                          self.solar_level, self.solar_source, self.solar_as_of,
                                          state_to_json(self.state))

    def _save(self) -> None:
        s = self.state
        self.db.update_outpost_run(self.run_id, status=s.status, sol=min(s.sol, s.total_sols), score=s.score,
                                   stars=O.rating(s), fail_reason=s.fail_reason, state_json=state_to_json(s),
                                   history_json=json.dumps(self.history))

    # ---- the power budget
    @property
    def running(self) -> bool:
        return self.state.status == O.RUNNING

    def available(self) -> int:
        return O.available_power(self.state)

    def limit(self, cat: str) -> int:
        return C.ALLOC_LIMIT[cat]

    def allocated(self) -> int:
        return sum(self.alloc.values())

    def unspent(self) -> int:
        """Power not allocated: it charges the battery (up to its cap) instead of being lost."""
        return self.available() - self.allocated()

    def adjust(self, cat: str, delta: int) -> bool:
        """Change one category by ``delta`` within its limit and the remaining budget. True if it changed."""
        if cat not in self.alloc or not self.running:
            return False
        new = max(0, min(self.limit(cat), self.alloc[cat] + int(delta)))
        new = min(new, self.alloc[cat] + max(0, self.unspent())) if new > self.alloc[cat] else new
        changed = new != self.alloc[cat]
        self.alloc[cat] = new
        return changed

    def reset(self) -> None:
        self.alloc = {k: 0 for k in C.ALLOCATIONS}

    def set_focus(self, value: float) -> bool:
        if value not in C.LS_FOCUS_CHOICES:
            return False
        self.focus = value
        return True

    # ---- what the player is allowed to see
    def preview(self) -> Dict[str, Any]:
        """The consequence of the CURRENT allocation, assuming no event (events stay unknown). Pure: changes nothing."""
        if not self.running:
            return {"valid": False}
        try:
            nxt = O.step_sol(self.state, self.alloc, None, self.focus)
        except ValueError:
            return {"valid": False}
        s = self.state
        warnings = []
        if nxt.status == O.LOST:
            warnings.append(f"op_ui_warn_lost_{nxt.fail_reason}")
        else:
            if nxt.oxygen < C.LOW_LEVEL:
                warnings.append("op_ui_warn_oxygen")
            if nxt.food < C.LOW_LEVEL:
                warnings.append("op_ui_warn_food")
            if nxt.shielding < C.LOW_LEVEL:
                warnings.append("op_ui_warn_shielding")
            if O.is_blackout(nxt):
                warnings.append("op_ui_warn_power")
        return {"valid": True, "warnings": warnings,
                "delta": {"oxygen": nxt.oxygen - s.oxygen, "food": nxt.food - s.food, "power": nxt.power - s.power,
                          "shielding": nxt.shielding - s.shielding, "crew_health": nxt.crew_health - s.crew_health,
                          "score": nxt.score - s.score},
                "next": {"oxygen": nxt.oxygen, "food": nxt.food, "power": nxt.power, "shielding": nxt.shielding,
                         "crew_health": nxt.crew_health}}

    def forecast_view(self) -> Dict[str, Any]:
        """What mission control can say about THIS sol, exactly as the simulation's forecast rules allow."""
        s = self.state
        base = {"comms_level": s.comms_level, "comms_ok": s.comms_ok, "need_hint": C.COMMS_FORECAST_MIN,
                "need_full": C.COMMS_FORECAST_FULL, "blackout_sols": s.comms_down_left}
        if not self.running:
            return {**base, "kind": "none"}
        exact = O.forecast(s, self._event)
        if exact:
            return {**base, "kind": "exact", "event": exact, "severity": C.EVENTS[exact]["severity"],
                    "category": C.EVENTS[exact]["category"]}
        hint = O.forecast_hint(s, self._event)
        if hint:
            return {**base, "kind": "category", "category": hint}
        return {**base, "kind": "quiet" if s.comms_ok else "none"}

    def effects_view(self) -> List[Dict[str, Any]]:
        """Temporary effects that are already active (known to the player: they have happened)."""
        s, out = self.state, []
        if s.dust_left > 0:
            out.append({"key": "op_ui_effect_dust", "sols": s.dust_left, "percent": round(s.dust_factor * 100)})
        if s.comms_down_left > 0:
            out.append({"key": "op_ui_effect_comms_down", "sols": s.comms_down_left})
        return out

    def last_sol_view(self) -> Optional[Dict[str, Any]]:
        """The sol just played: the event that HAPPENED (if any), its severity and the messages."""
        if not self.history:
            return None
        ev = self.history[-1]["event"]
        return {"sol": self.history[-1]["sol"], "event": ev, "severity": C.EVENTS[ev]["severity"] if ev else None,
                "messages": [(k, p) for k, p in self.state.log if not k.startswith("op_event_")]}

    def solar(self) -> nasa_data.SolarActivity:
        return nasa_data.SolarActivity(self.solar_level, self.solar_source, self.solar_as_of)

    def result(self) -> Optional[Dict[str, Any]]:
        s = self.state
        if s.status == O.RUNNING:
            return None
        return {"status": s.status, "stars": O.rating(s), "score": s.score, "sols": min(s.sol - 1, s.total_sols),
                "total_sols": s.total_sols, "seed": self.seed, "failure_key": O.failure_key(s),
                "failure_text": O.failure_explanation(s)}

    # ---- playing
    def advance(self) -> bool:
        """Play the sol with the current allocation. False if the allocation is not allowed."""
        if not self.running:
            return False
        try:
            new_state = O.step_sol(self.state, self.alloc, self._event, self.focus)
        except ValueError:
            return False
        self.history.append({"sol": self.state.sol, "alloc": dict(self.alloc), "focus": self.focus,
                             "event": self._event})
        self.state = new_state
        self._event = O.roll_event(new_state, self.rng, self.solar_level) if self.running else None
        self._carry_allocation()
        self._save()
        return True

    def _carry_allocation(self) -> None:
        """Keep last sol's plan as the next draft, trimmed to the new budget and limits."""
        old, self.alloc = self.alloc, {k: 0 for k in C.ALLOCATIONS}
        for cat in C.ALLOCATIONS:
            self.adjust(cat, old[cat])

    def abandon(self) -> None:
        """Leave the run for good (it stays in the history as abandoned)."""
        if self.running:
            s = self.state
            self.db.update_outpost_run(self.run_id, status="abandoned", sol=s.sol, score=s.score, stars=0,
                                       fail_reason=None, state_json=state_to_json(s),
                                       history_json=json.dumps(self.history))
