"""Glue between mission results, progression and the database (engine-independent)."""
from typing import Any, Dict, List

from . import progression as prog
from .db import Database
from .missions import MISSIONS, MissionState, Mission, is_unlocked


def current_tier(db: Database, profile_id: int) -> str:
    return prog.tier_from_skill(db.get_profile(profile_id)["skill"])


def mission_list(db: Database, profile_id: int, missions=None) -> List[Dict[str, Any]]:
    completed = db.completed_missions(profile_id)
    progress = db.get_progress(profile_id)
    return [{
        "mission": m,
        "unlocked": is_unlocked(m, completed),
        "completed": m.id in completed,
        "stars": progress.get(m.id, {}).get("best_stars", 0),
    } for m in (missions or MISSIONS)]


def start_mission(db: Database, profile_id: int, mission: Mission, lang: str = "en", age: str = "mid") -> MissionState:
    completed = db.completed_missions(profile_id)
    if not is_unlocked(mission, completed):
        raise PermissionError(f"Mission '{mission.id}' is locked")
    db.record_attempt(profile_id, mission.id)
    return MissionState(mission, current_tier(db, profile_id), lang, age)


def finish_mission(db: Database, profile_id: int, state: MissionState, seconds: float) -> Dict[str, Any]:
    """Award XP, update adaptive skill, unlocks and achievements. Returns a summary dict."""
    if not state.complete:
        raise ValueError("Mission is not complete")
    profile = db.get_profile(profile_id)
    old_level = prog.level_from_xp(profile["xp"])
    star_count = prog.stars(state.mistakes, state.hints)
    xp = prog.mission_xp(state.base_xp, state.mission.bonus_xp, state.hints, state.tier)

    new_xp = db.add_xp(profile_id, xp)
    new_skill = prog.update_skill(profile["skill"], state.mistakes, state.hints)
    db.set_skill(profile_id, new_skill)
    db.record_completion(profile_id, state.mission.id, star_count)
    db.record_performance(profile_id, state.mission.id, state.mistakes, state.hints,
                          seconds, state.tier, new_skill)
    samples = int(db.get_setting(profile_id, "samples_analyzed", "0")) + 1
    db.set_setting(profile_id, "samples_analyzed", samples)

    completed = db.completed_missions(profile_id)
    new_level = prog.level_from_xp(new_xp)
    earned = prog.check_achievements(
        completed_count=len(completed), total_missions=len(MISSIONS), stars_earned=star_count,
        samples_total=samples, level=new_level)
    new_achievements = [a for a in earned if db.grant_achievement(profile_id, a)]

    unlocked = [m.id for m in MISSIONS if m.requires == state.mission.id]
    return {"xp": xp, "total_xp": new_xp, "stars": star_count, "level": new_level,
            "leveled_up": new_level > old_level, "new_skill": new_skill,
            "next_tier": prog.tier_from_skill(new_skill), "unlocked": unlocked,
            "achievements": new_achievements}
