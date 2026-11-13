"""XP, levels, achievements and adaptive difficulty. Pure logic."""
import math
from dataclasses import dataclass
from typing import Dict, List

TIERS = ("easy", "normal", "hard")


@dataclass(frozen=True)
class TierSettings:
    xp_mult: float
    hint_cost: int
    highlight_targets: bool


TIER_SETTINGS: Dict[str, TierSettings] = {
    "easy": TierSettings(0.8, 0, True),
    "normal": TierSettings(1.0, 5, False),
    "hard": TierSettings(1.25, 10, False),
}

ACHIEVEMENTS = {
    "first_mission": "First Landing: complete your first mission",
    "flawless": "Flawless: finish a mission with no mistakes or hints",
    "scientist": "Field Scientist: analyze 5 samples in total",
    "problem_solver": "Problem Solver: complete 3 missions",
    "explorer": "Galaxy Explorer: complete every mission",
    "level_5": "Veteran Astronaut: reach level 5",
}


def level_from_xp(xp: int) -> int:
    return 1 + int(math.sqrt(max(0, xp) / 50))


def xp_for_level(level: int) -> int:
    return 50 * (max(1, level) - 1) ** 2


def tier_from_skill(skill: float) -> str:
    if skill < 0.35:
        return "easy"
    if skill < 0.7:
        return "normal"
    return "hard"


def update_skill(skill: float, mistakes: int, hints: int) -> float:
    """Exponential moving average of a per-mission performance score."""
    score = max(0.0, 1.0 - 0.2 * mistakes - 0.1 * hints)
    return round(max(0.0, min(1.0, 0.6 * skill + 0.4 * score)), 3)


def stars(mistakes: int, hints: int) -> int:
    if mistakes == 0 and hints == 0:
        return 3
    if mistakes <= 1 and hints <= 1:
        return 2
    return 1


def mission_xp(base_xp: int, bonus_xp: int, hints: int, tier: str) -> int:
    s = TIER_SETTINGS[tier]
    return max(10, round((base_xp + bonus_xp) * s.xp_mult) - hints * s.hint_cost)


def check_achievements(*, completed_count: int, total_missions: int, stars_earned: int,
                       samples_total: int, level: int) -> List[str]:
    earned = []
    if completed_count >= 1:
        earned.append("first_mission")
    if stars_earned == 3:
        earned.append("flawless")
    if samples_total >= 5:
        earned.append("scientist")
    if completed_count >= 3:
        earned.append("problem_solver")
    if completed_count >= total_missions:
        earned.append("explorer")
    if level >= 5:
        earned.append("level_5")
    return earned
