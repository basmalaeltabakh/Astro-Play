"""Languages (English / Arabic), Arabic text shaping and right-to-left helpers.

Panda3D draws text left-to-right with no shaping, so Arabic must be *reshaped* (letters joined) and
*reordered* (bidi) before it is drawn.  Every string shown on screen goes through :func:`shape` exactly once
(the UI helpers in ``astro/game/ui.py`` do this); never shape text twice.

Logic modules (missions, assistant) only deal with *logical* text and accept an explicit ``lang``.
"""
import re
import textwrap
from typing import Dict

LANGS = ("en", "ar")
LANG_NAMES = {"en": "English", "ar": "\u0627\u0644\u0639\u0631\u0628\u064a\u0629"}

_current = "en"

try:  # optional at import time so logic and tests still work without the Arabic packages
    import arabic_reshaper
    from bidi.algorithm import get_display
    _reshaper = arabic_reshaper.ArabicReshaper(configuration={"use_unshaped_instead_of_isolated": True,
                                                              "delete_harakat": True})
except Exception:  # pragma: no cover
    _reshaper = None
    get_display = None

_ARABIC = re.compile("[\u0600-\u06FF\u0750-\u077F]")


def set_lang(code: str):
    global _current
    _current = code if code in LANGS else "en"


def get_lang() -> str:
    return _current


def is_rtl(lang: str = None) -> bool:
    return (lang or _current) == "ar"


def has_arabic(text: str) -> bool:
    return bool(_ARABIC.search(text or ""))


def shape(text: str, force: bool = None) -> str:
    """Return text ready to draw.  Arabic is reshaped + bidi-reordered; everything else is untouched.
    ``force`` overrides auto-detection (default: shape if the text contains Arabic letters)."""
    if text is None:
        return ""
    text = str(text)
    do = has_arabic(text) if force is None else force
    if not do or _reshaper is None or get_display is None:
        return text
    lines = []
    for line in text.split("\n"):
        lines.append(get_display(_reshaper.reshape(line), base_dir="R") if has_arabic(line) else line)
    return "\n".join(lines)


def wrap(text: str, width: int = 60) -> str:
    """Word-wrap *logical* text (call before shape)."""
    return "\n".join(textwrap.fill(p, width) if p.strip() else "" for p in str(text).split("\n"))


def font(kind: str = "body", lang: str = None, text: str = None) -> str:
    """Font file name (looked up in assets/fonts).  kind: 'display' (titles) or 'body'.
    If ``text`` contains Arabic letters the Arabic-capable font is used whatever the UI language is."""
    if (lang or _current) == "ar" or (text is not None and has_arabic(text)):
        return "Cairo-Black.ttf" if kind == "display" else "Cairo-Bold.ttf"
    return "Orbitron-Bold.ttf" if kind == "display" else "Rajdhani-Bold.ttf"


def t(key: str, lang: str = None, **kw) -> str:
    code = lang or _current
    table = STRINGS.get(code, STRINGS["en"])
    s = table.get(key)
    if s is None:
        s = STRINGS["en"].get(key, key)
    try:
        return s.format(**kw) if kw else s
    except (KeyError, IndexError):
        return s


def has_key(key: str, lang: str) -> bool:
    return key in STRINGS[lang]


STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        # ---- common
        "tagline": "EXPLORE  \u2022  DISCOVER  \u2022  LEARN",
        "loading": "Loading mission control...",
        "press_start": "Press any key",
        "new_game": "New Game", "continue": "Continue", "quit": "Quit", "back": "Back", "next": "Next",
        "music": "Music", "sound": "Sound", "language": "Language", "on": "ON", "off": "OFF",
        "music_hint": "Music (M)", "sfx_hint": "Sound effects", "lang_hint": "Language",
        "assistant_backend": "AI assistant retrieval: {backend}",
        "assistant_llm": "AI: {llm}",
        # ---- profile
        "create_profile": "Create your profile", "astro_name": "Astronaut name",
        "age_hint": "Age group  (changes how science is explained)",
        "age_young": "Ages 6-9", "age_mid": "Ages 10-13", "age_teen": "Ages 14+",
        "default_name": "Astro", "type_name": "Type your name",
        "suit_up": "Suit up, {name}!", "visor_color": "Visor color", "suit_color": "Suit color",
        "launch_map": "Launch to Galaxy Map", "choose_astronaut": "Choose your astronaut",
        # ---- map
        "galaxy_map": "G A L A X Y   M A P", "level": "LEVEL {n}", "xp_line": "{xp} / {hi} XP",
        "easy": "EASY", "normal": "NORMAL", "hard": "HARD",
        "achievements_count": "Achievements  {a}/{b}", "main_menu": "Main Menu", "locked": "LOCKED",
        "aborted": "Mission aborted. Progress in that attempt wasn't saved.",
        # ---- briefing
        "science_focus": "Science focus:  {x}", "objectives": "OBJECTIVES", "controls": "CONTROLS",
        "key_move": "Move", "key_look": "Look", "key_tools": "Tools", "key_use": "Use", "key_hint": "Hint",
        "key_ask": "Ask AI", "key_log": "Log", "key_leave": "Leave", "key_mouse": "Mouse",
        "difficulty": "Difficulty: {t}", "adapts": "adapts to how you play", "launch": "LAUNCH!",
        # ---- HUD / tools
        "tool_scanner": "Scanner", "tool_sampler": "Sample Collector", "tool_analyzer": "Spectrometer",
        "tool_wrench": "Repair Kit",
        "glyph_scanner": "SCAN", "glyph_sampler": "COLLECT", "glyph_analyzer": "ANALYZE", "glyph_wrench": "REPAIR",
        "start_tip": "Select the Scanner (1) and press E on equipment.  H = hint.",
        "hud_info": "Difficulty: {t}\nMistakes {m}   Hints {h}",
        "hud_keys": "H Hint   Q Ask AI   Tab Log   M Music   Esc Leave",
        # ---- panels
        "repair_title": "REPAIR  \u2022  {name}", "diagnosis": "Diagnosis: {d}",
        "fix_question": "Which fix will work in this environment?",
        "fix_question_young": "Which fix is the best one here?",
        "esc_cancel": "Esc to cancel", "esc_close": "Esc to close",
        "log_title": "EVIDENCE LOG", "log_empty": "Nothing yet. Scan objects to gather evidence.",
        "ask_title": "AI SPACE ASSISTANT",
        "ask_hint": "Ask a science question about this mission, then press Enter.",
        "ask_placeholder": "Type your question here...", "try_asking": "Or tap a question:",
        "thinking": "Thinking...", "comms_down": "My comms are down. Try again!",
        "ask_empty": "Ask me anything about the mission or the science!", "ask_btn": "Ask",
        "no_data": "I don't have data on that yet. Try scanning nearby objects, or ask about the environment you're exploring.",
        "from_notes": "From my notes:",
        # ---- completion & quiz
        "complete": "MISSION COMPLETE", "xp_total": "+{xp} XP      total {total}      Level {lvl}",
        "level_up": "LEVEL UP!",
        "stats": "Mistakes {m}    Hints {h}    Time {s}s    Next difficulty: {t}",
        "unlocked": "UNLOCKED: {names}", "achievement": "Achievement: {text}",
        "learned": "WHAT YOU LEARNED", "deep_dive": "DEEP DIVE",
        "back_to_map": "Back to Galaxy Map", "take_quiz": "Take the Quiz  (+XP)",
        "quiz_title": "MISSION QUIZ", "quiz_q": "Question {i} of {n}",
        "quiz_correct": "Correct!  +{xp} XP", "quiz_wrong": "Not quite.", "quiz_next": "Next question",
        "quiz_finish": "Finish", "quiz_result": "You got {c} of {n} right!  +{xp} XP",
        "quiz_great": "Amazing work, astronaut!", "quiz_ok": "Good try. Every explorer learns by trying!",
        # ---- achievements
        "ach_first_mission": "First Landing: complete your first mission",
        "ach_flawless": "Flawless: finish a mission with no mistakes or hints",
        "ach_scientist": "Field Scientist: analyze 5 samples in total",
        "ach_problem_solver": "Problem Solver: complete 3 missions",
        "ach_explorer": "Galaxy Explorer: complete every mission",
        "ach_level_5": "Veteran Astronaut: reach level 5",
        # ---- mission engine messages
        "aim_at": "Aim at an object to use the tool.", "unknown_tool": "Unknown tool.", "nothing_happened": "Nothing happened.",
        "nothing_collect": "Nothing to collect from the {name}.", "sample_done": "Sample already collected.",
        "sample_ok": "Sample collected from {name}. Analyze it with the Spectrometer.",
        "nothing_analyze": "The {name} has nothing to analyze.", "collect_first": "Collect a sample first.",
        "already_analyzed": "Already analyzed.", "analysis_msg": "Analysis: {text}",
        "no_repair": "The {name} doesn't need repairs.", "already_repaired": "Already repaired.",
        "diagnose_first": "Diagnose first! Scan it to find out what's wrong.",
        "scanned_msg": "Scanned {name}. {fact}", "already_scanned": "{name}: already scanned.",
        "repair_impossible": "Repair not possible right now.", "repaired": "Repaired! {expl}",
        "wont_work": "That won't work. {expl}", "wont_work_young": "Oops, not that one! {expl}",
        "ev_fact": "{name}: {fact}", "ev_diag": "{name} diagnosis: {fault}",
        "ev_analysis": "{name} analysis: {text}", "ev_fix": "{name} fix: {expl}",
        "hint_prefix": "Hint: ", "hint_done": "Everything is done. Return to the shuttle!",
        "hint_easy": "Go to the {obj} and use the {tool} (look for the glowing marker).",
        "hint_easy_young": "Walk to the {obj} and press E with the {tool}. Look for the shiny diamond!",
        "hint_normal": "Try your {tool}. Which object hasn't been investigated yet?",
        "hint_normal_young": "Try your {tool}! Is there something you haven't looked at yet?",
        "hint_hard": "Check your evidence log. What is still unexplained?",
        "hint_hard_young": "Peek at your evidence log. What do you still wonder about?",
        "obj_scan": "Scan the {name}", "obj_collect": "Collect a sample from the {name}",
        "obj_analyze": "Analyze the {name} sample", "obj_diagnose": "Diagnose the {name} with the Scanner",
        "obj_repair": "Repair the {name}",
    },
    "ar": {
        # ---- common
        "tagline": "\u0627\u0633\u062a\u0643\u0634\u0641  \u2022  \u0627\u0643\u062a\u0634\u0641  \u2022  \u062a\u0639\u0644\u0651\u0645",
        "loading": "\u062c\u0627\u0631\u064d \u062a\u062c\u0647\u064a\u0632 \u0645\u0631\u0643\u0632 \u0627\u0644\u062a\u062d\u0643\u0645...",
        "press_start": "\u0627\u0636\u063a\u0637 \u0623\u064a \u0632\u0631 \u0644\u0644\u0628\u062f\u0621",
        "new_game": "\u0644\u0639\u0628\u0629 \u062c\u062f\u064a\u062f\u0629", "continue": "\u0645\u062a\u0627\u0628\u0639\u0629",
        "quit": "\u062e\u0631\u0648\u062c", "back": "\u0631\u062c\u0648\u0639", "next": "\u0627\u0644\u062a\u0627\u0644\u064a",
        "music": "\u0627\u0644\u0645\u0648\u0633\u064a\u0642\u0649", "sound": "\u0627\u0644\u0635\u0648\u062a",
        "language": "\u0627\u0644\u0644\u063a\u0629", "on": "\u062a\u0634\u063a\u064a\u0644", "off": "\u0625\u064a\u0642\u0627\u0641",
        "music_hint": "\u0627\u0644\u0645\u0648\u0633\u064a\u0642\u0649 (M)", "sfx_hint": "\u0627\u0644\u0645\u0624\u062b\u0631\u0627\u062a \u0627\u0644\u0635\u0648\u062a\u064a\u0629",
        "lang_hint": "\u0627\u0644\u0644\u063a\u0629",
        "assistant_backend": "\u0627\u0644\u0628\u062d\u062b \u0641\u064a \u0627\u0644\u0645\u0639\u0644\u0648\u0645\u0627\u062a: {backend}",
        "assistant_llm": "\u0627\u0644\u0630\u0643\u0627\u0621 \u0627\u0644\u0627\u0635\u0637\u0646\u0627\u0639\u064a: {llm}",
        # ---- profile
        "create_profile": "\u0623\u0646\u0634\u0626 \u0645\u0644\u0641\u0643 \u0627\u0644\u0634\u062e\u0635\u064a",
        "astro_name": "\u0627\u0633\u0645 \u0631\u0627\u0626\u062f \u0627\u0644\u0641\u0636\u0627\u0621",
        "age_hint": "\u0627\u0644\u0641\u0626\u0629 \u0627\u0644\u0639\u0645\u0631\u064a\u0629  (\u062a\u063a\u064a\u0651\u0631 \u0637\u0631\u064a\u0642\u0629 \u0634\u0631\u062d \u0627\u0644\u0639\u0644\u0648\u0645)",
        "age_young": "\u0645\u0646 6 \u0625\u0644\u0649 9 \u0633\u0646\u0648\u0627\u062a", "age_mid": "\u0645\u0646 10 \u0625\u0644\u0649 13 \u0633\u0646\u0629",
        "age_teen": "14 \u0633\u0646\u0629 \u0641\u0623\u0643\u062b\u0631",
        "default_name": "\u0631\u0627\u0626\u062f", "type_name": "\u0627\u0643\u062a\u0628 \u0627\u0633\u0645\u0643",
        "suit_up": "\u062c\u0647\u0651\u0632 \u0628\u062f\u0644\u062a\u0643 \u064a\u0627 {name}!",
        "visor_color": "\u0644\u0648\u0646 \u0627\u0644\u062e\u0648\u0630\u0629", "suit_color": "\u0644\u0648\u0646 \u0627\u0644\u0628\u062f\u0644\u0629",
        "launch_map": "\u0627\u0646\u0637\u0644\u0642 \u0625\u0644\u0649 \u062e\u0631\u064a\u0637\u0629 \u0627\u0644\u0645\u062c\u0631\u0629",
        "choose_astronaut": "\u0627\u062e\u062a\u0631 \u0631\u0627\u0626\u062f \u0627\u0644\u0641\u0636\u0627\u0621",
        # ---- map
        "galaxy_map": "\u062e\u0631\u064a\u0637\u0629 \u0627\u0644\u0645\u062c\u0631\u0629", "level": "\u0627\u0644\u0645\u0633\u062a\u0648\u0649 {n}",
        "xp_line": "{xp} / {hi} XP",
        "easy": "\u0633\u0647\u0644", "normal": "\u0639\u0627\u062f\u064a", "hard": "\u0635\u0639\u0628",
        "achievements_count": "\u0627\u0644\u0625\u0646\u062c\u0627\u0632\u0627\u062a  {a}/{b}",
        "main_menu": "\u0627\u0644\u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u0631\u0626\u064a\u0633\u064a\u0629", "locked": "\u0645\u0642\u0641\u0644\u0629",
        "aborted": "\u062a\u0645 \u0625\u0646\u0647\u0627\u0621 \u0627\u0644\u0645\u0647\u0645\u0629. \u0644\u0645 \u064a\u064f\u062d\u0641\u0638 \u062a\u0642\u062f\u0651\u0645 \u0647\u0630\u0647 \u0627\u0644\u0645\u062d\u0627\u0648\u0644\u0629.",
        # ---- briefing
        "science_focus": "\u0627\u0644\u062a\u0631\u0643\u064a\u0632 \u0627\u0644\u0639\u0644\u0645\u064a:  {x}",
        "objectives": "\u0627\u0644\u0623\u0647\u062f\u0627\u0641", "controls": "\u0627\u0644\u062a\u062d\u0643\u0651\u0645",
        "key_move": "\u062d\u0631\u0643\u0629", "key_look": "\u0646\u0638\u0631", "key_tools": "\u0623\u062f\u0648\u0627\u062a",
        "key_use": "\u0627\u0633\u062a\u062e\u062f\u0627\u0645", "key_hint": "\u062a\u0644\u0645\u064a\u062d",
        "key_ask": "\u0627\u0633\u0623\u0644 AI", "key_log": "\u0627\u0644\u0633\u062c\u0644", "key_leave": "\u062e\u0631\u0648\u062c",
        "key_mouse": "\u0627\u0644\u0645\u0627\u0648\u0633",
        "difficulty": "\u0627\u0644\u0635\u0639\u0648\u0628\u0629: {t}",
        "adapts": "\u062a\u062a\u0643\u064a\u0651\u0641 \u0645\u0639 \u0623\u0633\u0644\u0648\u0628 \u0644\u0639\u0628\u0643",
        "launch": "\u0627\u0646\u0637\u0644\u0642!",
        # ---- HUD / tools
        "tool_scanner": "\u0627\u0644\u0645\u0627\u0633\u062d", "tool_sampler": "\u062c\u0627\u0645\u0639 \u0627\u0644\u0639\u064a\u0651\u0646\u0627\u062a",
        "tool_analyzer": "\u0627\u0644\u0645\u0637\u064a\u0627\u0641", "tool_wrench": "\u0639\u062f\u0651\u0629 \u0627\u0644\u0625\u0635\u0644\u0627\u062d",
        "glyph_scanner": "\u0641\u062d\u0635", "glyph_sampler": "\u062c\u0645\u0639", "glyph_analyzer": "\u062a\u062d\u0644\u064a\u0644",
        "glyph_wrench": "\u0625\u0635\u0644\u0627\u062d",
        "start_tip": "\u0627\u062e\u062a\u0631 \u0627\u0644\u0645\u0627\u0633\u062d (1) \u0648\u0627\u0636\u063a\u0637 E \u0639\u0644\u0649 \u0627\u0644\u0645\u0639\u062f\u0627\u062a.  H = \u062a\u0644\u0645\u064a\u062d.",
        "hud_info": "\u0627\u0644\u0635\u0639\u0648\u0628\u0629: {t}\n\u0623\u062e\u0637\u0627\u0621 {m}   \u062a\u0644\u0645\u064a\u062d\u0627\u062a {h}",
        "hud_keys": "H \u062a\u0644\u0645\u064a\u062d   Q \u0627\u0633\u0623\u0644 AI   Tab \u0627\u0644\u0633\u062c\u0644   M \u0645\u0648\u0633\u064a\u0642\u0649   Esc \u062e\u0631\u0648\u062c",
        # ---- panels
        "repair_title": "\u0625\u0635\u0644\u0627\u062d  \u2022  {name}", "diagnosis": "\u0627\u0644\u062a\u0634\u062e\u064a\u0635: {d}",
        "fix_question": "\u0623\u064a \u062d\u0644\u0651 \u0633\u064a\u0646\u062c\u062d \u0641\u064a \u0647\u0630\u0647 \u0627\u0644\u0628\u064a\u0626\u0629\u061f",
        "fix_question_young": "\u0623\u064a \u062d\u0644\u0651 \u0647\u0648 \u0627\u0644\u0623\u0646\u0633\u0628 \u0647\u0646\u0627\u061f",
        "esc_cancel": "Esc \u0644\u0644\u0625\u0644\u063a\u0627\u0621", "esc_close": "Esc \u0644\u0644\u0625\u063a\u0644\u0627\u0642",
        "log_title": "\u0633\u062c\u0644 \u0627\u0644\u0623\u062f\u0644\u0629",
        "log_empty": "\u0644\u0627 \u0634\u064a\u0621 \u0628\u0639\u062f. \u0627\u0641\u062d\u0635 \u0627\u0644\u0623\u0634\u064a\u0627\u0621 \u0644\u062a\u062c\u0645\u0639 \u0627\u0644\u0623\u062f\u0644\u0629.",
        "ask_title": "\u0645\u0633\u0627\u0639\u062f \u0627\u0644\u0641\u0636\u0627\u0621 \u0627\u0644\u0630\u0643\u064a",
        "ask_hint": "\u0627\u0633\u0623\u0644 \u0633\u0624\u0627\u0644\u064b\u0627 \u0639\u0644\u0645\u064a\u064b\u0627 \u0639\u0646 \u0647\u0630\u0647 \u0627\u0644\u0645\u0647\u0645\u0629 \u062b\u0645 \u0627\u0636\u063a\u0637 Enter.",
        "ask_placeholder": "\u0627\u0643\u062a\u0628 \u0633\u0624\u0627\u0644\u0643 \u0647\u0646\u0627...",
        "try_asking": "\u0623\u0648 \u0627\u0636\u063a\u0637 \u0639\u0644\u0649 \u0633\u0624\u0627\u0644:",
        "thinking": "\u0623\u0641\u0643\u0651\u0631...", "comms_down": "\u0627\u0646\u0642\u0637\u0639 \u0627\u0644\u0627\u062a\u0635\u0627\u0644. \u062d\u0627\u0648\u0644 \u0645\u0631\u0629 \u0623\u062e\u0631\u0649!",
        "ask_btn": "\u0627\u0633\u0623\u0644", "ask_empty": "\u0627\u0633\u0623\u0644\u0646\u064a \u0623\u064a \u0634\u064a\u0621 \u0639\u0646 \u0627\u0644\u0645\u0647\u0645\u0629 \u0623\u0648 \u0627\u0644\u0639\u0644\u0645!",
        "no_data": "\u0644\u064a\u0633 \u0639\u0646\u062f\u064a \u0645\u0639\u0644\u0648\u0645\u0627\u062a \u0639\u0646 \u0647\u0630\u0627 \u0628\u0639\u062f. \u062c\u0631\u0651\u0628 \u0641\u062d\u0635 \u0627\u0644\u0623\u0634\u064a\u0627\u0621 \u0627\u0644\u0642\u0631\u064a\u0628\u0629\u060c \u0623\u0648 \u0627\u0633\u0623\u0644 \u0639\u0646 \u0627\u0644\u0628\u064a\u0626\u0629 \u0627\u0644\u062a\u064a \u062a\u0633\u062a\u0643\u0634\u0641\u0647\u0627.",
        "from_notes": "\u0645\u0646 \u0645\u0644\u0627\u062d\u0638\u0627\u062a\u064a:",
        # ---- completion & quiz
        "complete": "\u0627\u0643\u062a\u0645\u0644\u062a \u0627\u0644\u0645\u0647\u0645\u0629!",
        "xp_total": "+{xp} XP      \u0627\u0644\u0645\u062c\u0645\u0648\u0639 {total}      \u0627\u0644\u0645\u0633\u062a\u0648\u0649 {lvl}",
        "level_up": "\u062a\u0631\u0642\u064a\u0629 \u0645\u0633\u062a\u0648\u0649!",
        "stats": "\u0623\u062e\u0637\u0627\u0621 {m}    \u062a\u0644\u0645\u064a\u062d\u0627\u062a {h}    \u0627\u0644\u0648\u0642\u062a {s} \u062b    \u0627\u0644\u0635\u0639\u0648\u0628\u0629 \u0627\u0644\u0642\u0627\u062f\u0645\u0629: {t}",
        "unlocked": "\u0641\u064f\u062a\u062d\u062a: {names}", "achievement": "\u0625\u0646\u062c\u0627\u0632: {text}",
        "learned": "\u0645\u0627\u0630\u0627 \u062a\u0639\u0644\u0651\u0645\u062a", "deep_dive": "\u0644\u0644\u0645\u062a\u0639\u0645\u0651\u0642\u064a\u0646",
        "back_to_map": "\u0627\u0644\u0639\u0648\u062f\u0629 \u0644\u062e\u0631\u064a\u0637\u0629 \u0627\u0644\u0645\u062c\u0631\u0629",
        "take_quiz": "\u0627\u0628\u062f\u0623 \u0627\u0644\u0627\u062e\u062a\u0628\u0627\u0631  (+XP)",
        "quiz_title": "\u0627\u062e\u062a\u0628\u0627\u0631 \u0627\u0644\u0645\u0647\u0645\u0629", "quiz_q": "\u0627\u0644\u0633\u0624\u0627\u0644 {i} \u0645\u0646 {n}",
        "quiz_correct": "\u0625\u062c\u0627\u0628\u0629 \u0635\u062d\u064a\u062d\u0629!  +{xp} XP",
        "quiz_wrong": "\u0644\u064a\u0633\u062a \u0635\u062d\u064a\u062d\u0629 \u062a\u0645\u0627\u0645\u064b\u0627.",
        "quiz_next": "\u0627\u0644\u0633\u0624\u0627\u0644 \u0627\u0644\u062a\u0627\u0644\u064a", "quiz_finish": "\u0625\u0646\u0647\u0627\u0621",
        "quiz_result": "\u0623\u062c\u0628\u062a \u0635\u062d \u0639\u0644\u0649 {c} \u0645\u0646 {n}!  +{xp} XP",
        "quiz_great": "\u0639\u0645\u0644 \u0631\u0627\u0626\u0639 \u064a\u0627 \u0631\u0627\u0626\u062f \u0627\u0644\u0641\u0636\u0627\u0621!",
        "quiz_ok": "\u0645\u062d\u0627\u0648\u0644\u0629 \u062c\u0645\u064a\u0644\u0629. \u0643\u0644 \u0645\u0633\u062a\u0643\u0634\u0641 \u064a\u062a\u0639\u0644\u0651\u0645 \u0645\u0646 \u0627\u0644\u062a\u062c\u0631\u0628\u0629!",
        # ---- achievements
        "ach_first_mission": "\u0623\u0648\u0644 \u0647\u0628\u0648\u0637: \u0623\u0643\u0645\u0644 \u0645\u0647\u0645\u062a\u0643 \u0627\u0644\u0623\u0648\u0644\u0649",
        "ach_flawless": "\u0628\u0644\u0627 \u0623\u062e\u0637\u0627\u0621: \u0623\u0646\u0647\u0650 \u0645\u0647\u0645\u0629 \u0628\u062f\u0648\u0646 \u0623\u062e\u0637\u0627\u0621 \u0623\u0648 \u062a\u0644\u0645\u064a\u062d\u0627\u062a",
        "ach_scientist": "\u0639\u0627\u0644\u0645 \u0645\u064a\u062f\u0627\u0646\u064a: \u062d\u0644\u0651\u0644 5 \u0639\u064a\u0651\u0646\u0627\u062a",
        "ach_problem_solver": "\u062d\u0627\u0644\u0651 \u0627\u0644\u0645\u0634\u0643\u0644\u0627\u062a: \u0623\u0643\u0645\u0644 3 \u0645\u0647\u0645\u0627\u062a",
        "ach_explorer": "\u0645\u0633\u062a\u0643\u0634\u0641 \u0627\u0644\u0645\u062c\u0631\u0629: \u0623\u0643\u0645\u0644 \u0643\u0644 \u0627\u0644\u0645\u0647\u0645\u0627\u062a",
        "ach_level_5": "\u0631\u0627\u0626\u062f \u0645\u062d\u0646\u0651\u0643: \u0627\u0628\u0644\u063a \u0627\u0644\u0645\u0633\u062a\u0648\u0649 5",
        # ---- mission engine messages
        "aim_at": "\u0648\u062c\u0651\u0647 \u0627\u0644\u0645\u0624\u0634\u0651\u0631 \u0646\u062d\u0648 \u0634\u064a\u0621 \u0644\u062a\u0633\u062a\u062e\u062f\u0645 \u0627\u0644\u0623\u062f\u0627\u0629.",
        "unknown_tool": "\u0623\u062f\u0627\u0629 \u063a\u064a\u0631 \u0645\u0639\u0631\u0648\u0641\u0629.", "nothing_happened": "\u0644\u0645 \u064a\u062d\u062f\u062b \u0634\u064a\u0621.",
        "nothing_collect": "\u0644\u0627 \u0634\u064a\u0621 \u0644\u062c\u0645\u0639\u0647 \u0645\u0646 {name}.",
        "sample_done": "\u062a\u0645 \u062c\u0645\u0639 \u0627\u0644\u0639\u064a\u0651\u0646\u0629 \u0645\u0646 \u0642\u0628\u0644.",
        "sample_ok": "\u062c\u0645\u0639\u062a \u0639\u064a\u0651\u0646\u0629 \u0645\u0646 {name}. \u062d\u0644\u0651\u0644\u0647\u0627 \u0628\u0627\u0644\u0645\u0637\u064a\u0627\u0641.",
        "nothing_analyze": "{name} \u0644\u064a\u0633 \u0641\u064a\u0647 \u0645\u0627 \u064a\u064f\u062d\u0644\u0651\u0644.",
        "collect_first": "\u0627\u062c\u0645\u0639 \u0639\u064a\u0651\u0646\u0629 \u0623\u0648\u0644\u064b\u0627.",
        "already_analyzed": "\u062a\u0645 \u0627\u0644\u062a\u062d\u0644\u064a\u0644 \u0645\u0646 \u0642\u0628\u0644.", "analysis_msg": "\u0627\u0644\u062a\u062d\u0644\u064a\u0644: {text}",
        "no_repair": "{name} \u0644\u0627 \u064a\u062d\u062a\u0627\u062c \u0625\u0635\u0644\u0627\u062d\u064b\u0627.",
        "already_repaired": "\u062a\u0645 \u0627\u0644\u0625\u0635\u0644\u0627\u062d \u0645\u0646 \u0642\u0628\u0644.",
        "diagnose_first": "\u0634\u062e\u0651\u0635 \u0623\u0648\u0644\u064b\u0627! \u0627\u0641\u062d\u0635\u0647 \u0644\u062a\u0639\u0631\u0641 \u0645\u0627 \u0627\u0644\u0645\u0634\u0643\u0644\u0629.",
        "scanned_msg": "\u0641\u062d\u0635\u062a {name}. {fact}", "already_scanned": "{name}: \u062a\u0645 \u0641\u062d\u0635\u0647 \u0645\u0646 \u0642\u0628\u0644.",
        "repair_impossible": "\u0627\u0644\u0625\u0635\u0644\u0627\u062d \u063a\u064a\u0631 \u0645\u0645\u0643\u0646 \u0627\u0644\u0622\u0646.",
        "repaired": "\u062a\u0645 \u0627\u0644\u0625\u0635\u0644\u0627\u062d! {expl}",
        "wont_work": "\u0647\u0630\u0627 \u0644\u0646 \u064a\u0646\u062c\u062d. {expl}", "wont_work_young": "\u0623\u0648\u0647! \u0644\u064a\u0633 \u0647\u0630\u0627. {expl}",
        "ev_fact": "{name}: {fact}", "ev_diag": "\u062a\u0634\u062e\u064a\u0635 {name}: {fault}",
        "ev_analysis": "\u062a\u062d\u0644\u064a\u0644 {name}: {text}", "ev_fix": "\u0625\u0635\u0644\u0627\u062d {name}: {expl}",
        "hint_prefix": "\u062a\u0644\u0645\u064a\u062d: ", "hint_done": "\u0643\u0644 \u0634\u064a\u0621 \u062a\u0645. \u0639\u064f\u062f \u0625\u0644\u0649 \u0627\u0644\u0645\u0631\u0643\u0628\u0629!",
        "hint_easy": "\u0627\u0630\u0647\u0628 \u0625\u0644\u0649 {obj} \u0648\u0627\u0633\u062a\u062e\u062f\u0645 {tool} (\u0627\u0628\u062d\u062b \u0639\u0646 \u0627\u0644\u0639\u0644\u0627\u0645\u0629 \u0627\u0644\u0645\u062a\u0648\u0647\u062c\u0629).",
        "hint_easy_young": "\u0627\u0645\u0634\u0650 \u0625\u0644\u0649 {obj} \u0648\u0627\u0636\u063a\u0637 E \u0645\u0639 {tool}. \u0627\u0628\u062d\u062b \u0639\u0646 \u0627\u0644\u0645\u0627\u0633\u0629 \u0627\u0644\u0644\u0627\u0645\u0639\u0629!",
        "hint_normal": "\u062c\u0631\u0651\u0628 {tool}. \u0623\u064a \u0634\u064a\u0621 \u0644\u0645 \u062a\u062f\u0631\u0633\u0647 \u0628\u0639\u062f\u061f",
        "hint_normal_young": "\u062c\u0631\u0651\u0628 {tool}! \u0647\u0644 \u0647\u0646\u0627\u0643 \u0634\u064a\u0621 \u0644\u0645 \u062a\u0646\u0638\u0631 \u0625\u0644\u064a\u0647 \u0628\u0639\u062f\u061f",
        "hint_hard": "\u0631\u0627\u062c\u0639 \u0633\u062c\u0644 \u0627\u0644\u0623\u062f\u0644\u0629. \u0645\u0627 \u0627\u0644\u0630\u064a \u0644\u0627 \u064a\u0632\u0627\u0644 \u063a\u064a\u0631 \u0645\u0641\u0647\u0648\u0645\u061f",
        "hint_hard_young": "\u0623\u0644\u0642\u0650 \u0646\u0638\u0631\u0629 \u0639\u0644\u0649 \u0633\u062c\u0644 \u0627\u0644\u0623\u062f\u0644\u0629. \u0645\u0627\u0630\u0627 \u0644\u0627 \u062a\u0632\u0627\u0644 \u062a\u062a\u0633\u0627\u0621\u0644 \u0639\u0646\u0647\u061f",
        "obj_scan": "\u0627\u0641\u062d\u0635 {name}", "obj_collect": "\u0627\u062c\u0645\u0639 \u0639\u064a\u0651\u0646\u0629 \u0645\u0646 {name}",
        "obj_analyze": "\u062d\u0644\u0651\u0644 \u0639\u064a\u0651\u0646\u0629 {name}",
        "obj_diagnose": "\u0634\u062e\u0651\u0635 \u0639\u0637\u0644 {name} \u0628\u0627\u0644\u0645\u0627\u0633\u062d",
        "obj_repair": "\u0623\u0635\u0644\u062d {name}",
    },
}


# ---- habitat, oxygen and tool-battery strings
STRINGS["en"].update({
    "hab_door": "Habitat Airlock", "hab_analyzer": "Science Analyzer", "hab_bed": "Astronaut Bunk",
    "hab_locker": "Tool Locker", "hab_o2": "Oxygen Station",
    "prompt_e": "E  -  {action}",
    "act_open": "Open airlock", "act_close": "Close airlock", "act_lab": "Analyze my samples",
    "act_rest": "Rest and save checkpoint", "act_locker": "Recharge my tools", "act_o2": "Refill oxygen",
    "door_opened": "Airlock open.", "door_closed": "Airlock closed.",
    "bed_rest": "You rest in the bunk. Checkpoint saved: if your oxygen runs out you will wake up here.",
    "bed_todo": "Still to do: {todo}", "bed_all_done": "Everything is done. Time to head back to the shuttle!",
    "o2_filling": "Refilling oxygen...", "o2_full": "Oxygen tank full.", "o2_already_full": "Your oxygen tank is already full.",
    "locker_charged": "All tool batteries recharged.", "locker_full": "Your tools are already fully charged.",
    "tool_low": "The {tool} battery is too low. Recharge it at the tool locker inside the habitat.",
    "lab_no_sample": "Collect a sample first, then bring it to the analyzer.",
    "lab_report": "Lab analysis: {text}", "lab_bonus": "Detailed lab report: {text}  (+{xp} XP)",
    "lab_done": "The analyzer has no new samples to study.", "ev_lab": "{name} lab report: {text}",
    "o2_low": "Oxygen low: {p}%. Return to the habitat oxygen station.",
    "o2_critical": "OXYGEN CRITICAL: {p}%! Get to the habitat now!",
    "o2_empty": "Out of oxygen! Emergency return to the habitat. (+1 mistake)",
    "watch_o2": "O2", "battery": "Battery",
})
STRINGS["ar"].update({
    "hab_door": "بوابة المسكن", "hab_analyzer": "المحلّل العلمي", "hab_bed": "سرير رائد الفضاء",
    "hab_locker": "خزانة الأدوات", "hab_o2": "محطة الأكسجين",
    "prompt_e": "E  -  {action}",
    "act_open": "افتح البوابة", "act_close": "أغلق البوابة", "act_lab": "حلّل عيّناتي",
    "act_rest": "استرح واحفظ نقطة العودة", "act_locker": "اشحن أدواتي", "act_o2": "املأ الأكسجين",
    "door_opened": "البوابة مفتوحة.", "door_closed": "البوابة مغلقة.",
    "bed_rest": "ارتحت على السرير. حُفظت نقطة العودة: إن نفد أكسجينك ستستيقظ هنا.",
    "bed_todo": "ما زال عليك: {todo}", "bed_all_done": "كل شيء تمّ. حان وقت العودة إلى المركبة!",
    "o2_filling": "جارٍ ملء الأكسجين...", "o2_full": "خزّان الأكسجين ممتلئ.", "o2_already_full": "خزّان الأكسجين ممتلئ بالفعل.",
    "locker_charged": "تم شحن بطاريات كل الأدوات.", "locker_full": "أدواتك مشحونة بالكامل بالفعل.",
    "tool_low": "بطارية {tool} ضعيفة جدًّا. اشحنها من خزانة الأدوات داخل المسكن.",
    "lab_no_sample": "اجمع عيّنة أولًا ثم أحضرها إلى المحلّل.",
    "lab_report": "تحليل المعمل: {text}", "lab_bonus": "تقرير المعمل المفصّل: {text}  (+{xp} XP)",
    "lab_done": "ليس عند المحلّل عيّنات جديدة ليدرسها.", "ev_lab": "تقرير معمل {name}: {text}",
    "o2_low": "الأكسجين منخفض: {p}%. عُد إلى محطة الأكسجين في المسكن.",
    "o2_critical": "الأكسجين في خطر: {p}%! اذهب إلى المسكن الآن!",
    "o2_empty": "نفد الأكسجين! عودة طارئة إلى المسكن. (+1 خطأ)",
    "watch_o2": "O2", "battery": "البطارية",
})

STRINGS["en"]["door_blocked"] = "Step away from the doorway first."
STRINGS["ar"]["door_blocked"] = "ابتعد عن مدخل البوابة أولًا."

# ---- Outpost Command (all on-screen text for the outpost simulation; keys are prefixed "op_")
STRINGS["en"].update({
    "op_power": "Power", "op_life_support": "Life Support", "op_shielding": "Radiation Shielding",
    "op_oxygen": "Oxygen", "op_food": "Food", "op_crew_health": "Crew Health", "op_score": "Score",
    "op_sol": "Sol {n}", "op_comms": "Communications", "op_science": "Science",
    "op_event_solar_storm": "Solar storm! Charged particles are heading for the outpost.",
    "op_event_dust_storm": "Dust storm! The solar panels get less light for a few sols.",
    "op_event_micrometeorite": "A tiny space rock hit the outpost and damaged the shield.",
    "op_event_equipment_fault": "Equipment fault! Some power and oxygen were lost.",
    "op_event_comms_window": "Supply window! Earth can send a package if you have the radio on.",
    "op_msg_blackout": "Blackout! There was not enough power even for the basics.",
    "op_msg_radiation_blocked": "Your shielding blocked the radiation.",
    "op_msg_radiation_leaked": "Radiation got through the shield ({leak} points) and hurt the crew and the machines.",
    "op_msg_resupply_received": "Communications were on, so the supplies arrived!",
    "op_msg_resupply_missed": "Communications were off, so the supply window was missed.",
    "op_msg_low_oxygen": "Oxygen is running low!", "op_msg_low_food": "Food is running low!",
    "op_msg_health_down": "The crew's health dropped.",
    "op_msg_won": "Mission complete! Your crew survived every sol.",
    "op_msg_lost": "Mission failed.",
    "op_fail_oxygen": "The crew ran out of oxygen. Machines that make and clean air need power, so when power "
                      "goes to other jobs the air runs low. Real outposts always protect life support first.",
    "op_fail_food": "The crew ran out of food. Growing and storing food takes power and planning. "
                    "Real crews must plan their food for the whole mission.",
    "op_fail_crew_health": "The crew became too sick to continue. Radiation that gets past thin shielding, "
                           "too little air or food, and blackouts all hurt health. Strengthen the shield before "
                           "a solar storm and keep oxygen and food high.",
})
STRINGS["ar"].update({
    "op_power": "الطاقة", "op_life_support": "دعم الحياة", "op_shielding": "الحماية من الإشعاع",
    "op_oxygen": "الأكسجين", "op_food": "الغذاء", "op_crew_health": "صحة الطاقم", "op_score": "النقاط",
    "op_sol": "سول {n}", "op_comms": "الاتصالات", "op_science": "العلوم",
    "op_event_solar_storm": "عاصفة شمسية! جسيمات مشحونة متجهة نحو القاعدة.",
    "op_event_dust_storm": "عاصفة غبار! الألواح الشمسية تأخذ ضوءًا أقل لعدة أيام.",
    "op_event_micrometeorite": "صخرة صغيرة من الفضاء ضربت القاعدة وأضرّت بالدرع.",
    "op_event_equipment_fault": "عطل في المعدات! فُقدت بعض الطاقة وبعض الأكسجين.",
    "op_event_comms_window": "فرصة إمداد! تستطيع الأرض إرسال طرد إذا كان جهاز الاتصال يعمل.",
    "op_msg_blackout": "انقطاع الكهرباء! لم تكف الطاقة حتى للأساسيات.",
    "op_msg_radiation_blocked": "درعك حجب الإشعاع.",
    "op_msg_radiation_leaked": "تسرّب الإشعاع عبر الدرع ({leak} نقطة) وأضرّ بالطاقم والآلات.",
    "op_msg_resupply_received": "كانت الاتصالات تعمل فوصلت الإمدادات!",
    "op_msg_resupply_missed": "كانت الاتصالات متوقفة فضاعت فرصة الإمداد.",
    "op_msg_low_oxygen": "الأكسجين يوشك على النفاد!", "op_msg_low_food": "الغذاء يوشك على النفاد!",
    "op_msg_health_down": "انخفضت صحة الطاقم.",
    "op_msg_won": "اكتملت المهمة! نجا طاقمك في كل الأيام.",
    "op_msg_lost": "فشلت المهمة.",
    "op_fail_oxygen": "نفد الأكسجين من الطاقم. الآلات التي تصنع الهواء وتنظّفه تحتاج إلى طاقة. وحين تذهب الطاقة "
                      "إلى أعمال أخرى يقلّ الهواء. القواعد الحقيقية تحمي دعم الحياة أولًا دائمًا.",
    "op_fail_food": "نفد الغذاء من الطاقم. زراعة الغذاء وتخزينه يحتاجان إلى طاقة وتخطيط. "
                    "على الطواقم الحقيقية أن تخطّط لغذائها طوال المهمة.",
    "op_fail_crew_health": "مرض الطاقم ولم يعد قادرًا على المتابعة. الإشعاع الذي يعبر درعًا ضعيفًا ونقص الهواء "
                           "أو الغذاء وانقطاع الكهرباء كلها تضرّ بالصحة. قوِّ الدرع قبل العاصفة الشمسية "
                           "وأبقِ الأكسجين والغذاء مرتفعين.",
})

# ---- Outpost Command: event variety and forecasts (Phase 3)
STRINGS["en"].update({
    "op_event_dust_accumulation": "Dust is piling up on the solar panels. They make less power for a few sols.",
    "op_event_comms_blackout": "Communications blackout! The radio is down, so radio power is wasted and no forecast is possible.",
    "op_event_crop_blight": "Blight in the greenhouse! Some of the food plants died.",
    "op_event_supply_cache": "Lucky find! The crew found a cache of spare parts and batteries.",
    "op_event_science_discovery": "A science discovery! The crew spotted something interesting near the outpost.",
    "op_msg_discovery": "Your science team was ready and studied it well: {points} bonus points!",
    "op_msg_discovery_small": "Not enough science power to study it properly: only {points} bonus points.",
    "op_forecast_off": "No forecast. Put more power into Communications to see what is coming.",
    "op_forecast_radiation": "Mission control warns: radiation activity is expected soon.",
    "op_forecast_weather": "Mission control warns: bad weather is expected soon.",
    "op_forecast_damage": "Mission control warns: something may break or get damaged soon.",
    "op_forecast_comms": "Mission control warns: the radio link may have trouble soon.",
    "op_forecast_opportunity": "Mission control says: a lucky chance may be coming soon.",
    "op_forecast_exact": "Mission control forecast: {event}",
})
STRINGS["ar"].update({
    "op_event_dust_accumulation": "الغبار يتراكم على الألواح الشمسية. ستنتج طاقة أقل لعدة أيام.",
    "op_event_comms_blackout": "انقطاع الاتصالات! جهاز الراديو متوقف فتضيع طاقته ولا يمكن معرفة التوقعات.",
    "op_event_crop_blight": "مرض أصاب الدفيئة! ماتت بعض نباتات الغذاء.",
    "op_event_supply_cache": "اكتشاف محظوظ! وجد الطاقم مخزنًا من قطع الغيار والبطاريات.",
    "op_event_science_discovery": "اكتشاف علمي! لاحظ الطاقم شيئًا مثيرًا قرب القاعدة.",
    "op_msg_discovery": "كان فريق العلوم مستعدًا ودرسه جيدًا: {points} نقطة إضافية!",
    "op_msg_discovery_small": "لا توجد طاقة علمية كافية لدراسته جيدًا: {points} نقاط إضافية فقط.",
    "op_forecast_off": "لا توجد توقعات. ضع طاقة أكثر في الاتصالات لترى ما هو قادم.",
    "op_forecast_radiation": "مركز التحكم يحذّر: نشاط إشعاعي متوقع قريبًا.",
    "op_forecast_weather": "مركز التحكم يحذّر: طقس سيئ متوقع قريبًا.",
    "op_forecast_damage": "مركز التحكم يحذّر: قد ينكسر شيء أو يتضرر قريبًا.",
    "op_forecast_comms": "مركز التحكم يحذّر: قد تواجه وصلة الراديو مشكلة قريبًا.",
    "op_forecast_opportunity": "مركز التحكم يقول: قد تأتي فرصة محظوظة قريبًا.",
    "op_forecast_exact": "توقعات مركز التحكم: {event}",
})

# ---- Outpost Command: honest data-source labels for NASA DONKI space weather (Phase 4)
STRINGS["en"].update({
    "op_src_live": "Live NASA DONKI space-weather data.",
    "op_src_cached": "Saved NASA DONKI data, retrieved {date}. Not live.",
    "op_src_archived": "Archived NASA DONKI data, retrieved {date}. Not live.",
    "op_src_default": "No NASA data is available right now, so the game uses a standard solar-activity level.",
    "op_solar_low": "Solar activity: calm",
    "op_solar_medium": "Solar activity: active",
    "op_solar_high": "Solar activity: stormy",
})
STRINGS["ar"].update({
    "op_src_live": "بيانات الطقس الفضائي المباشرة من ناسا (DONKI).",
    "op_src_cached": "بيانات ناسا (DONKI) المحفوظة، جُلبت في {date}. ليست مباشرة.",
    "op_src_archived": "بيانات ناسا (DONKI) المؤرشفة، جُلبت في {date}. ليست مباشرة.",
    "op_src_default": "لا تتوفر بيانات من ناسا الآن لذلك تستخدم اللعبة مستوى عاديًّا للنشاط الشمسي.",
    "op_solar_low": "النشاط الشمسي: هادئ",
    "op_solar_medium": "النشاط الشمسي: نشط",
    "op_solar_high": "النشاط الشمسي: عاصف",
})

# ---- Outpost Command: NASA OSDR research cards (Phase 5). NASA's own titles/descriptions stay in English; the text
# below is ours. Gameplay notes are educational and illustrative: they never state findings or numeric thresholds.
STRINGS["en"].update({
    "op_osdr_topic_plants": "Plants and food", "op_osdr_topic_radiation": "Radiation",
    "op_osdr_topic_microgravity": "Microgravity and the body", "op_osdr_topic_health": "Human health",
    "op_osdr_topic_microbes": "Microbes and habitats",
    "op_osdr_setting_spaceflight": "Spaceflight study",
    "op_osdr_setting_ground": "Ground-based study (done on Earth)",
    "op_osdr_setting_unknown": "Not stated whether it flew in space",
    "op_osdr_summary_spaceflight": "A NASA OSDR dataset about {organism} from a spaceflight study.",
    "op_osdr_summary_ground": "A NASA OSDR dataset about {organism} from a study done on Earth, not in space.",
    "op_osdr_summary_unknown": "A NASA OSDR dataset about {organism}. Its record does not say whether the study flew in space.",
    "op_osdr_unknown_organism": "a biological subject",
    "op_osdr_card_title": "Space research card", "op_osdr_accession": "Study ID", "op_osdr_organism": "Organism",
    "op_osdr_material": "Sample type", "op_osdr_mission": "Mission", "op_osdr_platform": "Hardware or platform",
    "op_osdr_title": "Official study title (NASA, in English)",
    "op_osdr_description": "Official description (NASA, in English)",
    "op_osdr_source": "Source: NASA Open Science Data Repository (OSDR)", "op_osdr_view": "View the study on NASA OSDR",
    "op_osdr_game_label": "How the game uses this idea (educational)",
    "op_osdr_game_plants": "Educational idea: an outpost must make food, and that is part of Life Support in the game. This card does not tell how much food a crew could grow, and the game's numbers are not taken from it.",
    "op_osdr_game_radiation": "Educational idea: radiation is why Shielding matters in the game. The game's numbers are made up for play and are not taken from this study.",
    "op_osdr_game_microgravity": "Educational idea: living in space can change the body, so the game tracks Crew Health. The game's numbers are not taken from this study.",
    "op_osdr_game_health": "Educational idea: keeping a crew healthy on long missions is shown as Crew Health in the game. This card gives no medical advice, and the game's numbers are not taken from it.",
    "op_osdr_game_microbes": "Educational idea: keeping air, water and food clean is part of Life Support in the game. The game does not model germs or use numbers from this study.",
    "op_osdr_disclaimer": "The title and description are NASA's own words. The sentence about the game is our educational simplification, not a finding of this study.",
    "op_osdr_loading": "Loading NASA research cards...",
    "op_osdr_error": "Could not reach NASA OSDR right now. Showing saved research cards instead.",
    "op_osdr_empty": "No research cards found.",
    "op_osdr_src_live": "Live NASA OSDR data.",
    "op_osdr_src_cached": "Saved NASA OSDR data, retrieved {date}. Not live.",
    "op_osdr_src_offline": "Offline NASA OSDR records, retrieved {date}. Not live.",
    "op_osdr_src_none": "No research cards are available right now.",
    "op_osdr_card_live": "Live data", "op_osdr_card_cached": "Saved data (not live)",
    "op_osdr_card_offline": "Offline data (not live)",
})
STRINGS["ar"].update({
    "op_osdr_topic_plants": "النباتات والغذاء", "op_osdr_topic_radiation": "الإشعاع",
    "op_osdr_topic_microgravity": "انعدام الجاذبية والجسم", "op_osdr_topic_health": "صحة الإنسان",
    "op_osdr_topic_microbes": "الميكروبات والمساكن الفضائية",
    "op_osdr_setting_spaceflight": "دراسة أُجريت في الفضاء",
    "op_osdr_setting_ground": "دراسة على الأرض (ليست في الفضاء)",
    "op_osdr_setting_unknown": "لم يُذكر إن كانت قد أُجريت في الفضاء",
    "op_osdr_summary_spaceflight": "مجموعة بيانات من ناسا (OSDR) عن {organism} من دراسة أُجريت في الفضاء.",
    "op_osdr_summary_ground": "مجموعة بيانات من ناسا (OSDR) عن {organism} من دراسة أُجريت على الأرض وليس في الفضاء.",
    "op_osdr_summary_unknown": "مجموعة بيانات من ناسا (OSDR) عن {organism}. ولا يذكر سجلّها إن كانت الدراسة قد أُجريت في الفضاء.",
    "op_osdr_unknown_organism": "كائن حي",
    "op_osdr_card_title": "بطاقة بحث فضائي", "op_osdr_accession": "رقم الدراسة", "op_osdr_organism": "الكائن الحي",
    "op_osdr_material": "نوع العيّنة", "op_osdr_mission": "المهمة", "op_osdr_platform": "الجهاز أو المنصّة",
    "op_osdr_title": "عنوان الدراسة الرسمي (من ناسا بالإنجليزية)",
    "op_osdr_description": "الوصف الرسمي (من ناسا بالإنجليزية)",
    "op_osdr_source": "المصدر: مستودع ناسا للبيانات العلمية المفتوحة (OSDR)", "op_osdr_view": "اعرض الدراسة على موقع ناسا",
    "op_osdr_game_label": "كيف تستخدم اللعبة هذه الفكرة (تعليمي)",
    "op_osdr_game_plants": "فكرة تعليمية: على القاعدة أن تنتج الغذاء وهذا جزء من دعم الحياة في اللعبة. لا تخبرنا هذه البطاقة كم من الغذاء يمكن لطاقم أن يزرع. وأرقام اللعبة ليست مأخوذة منها.",
    "op_osdr_game_radiation": "فكرة تعليمية: الإشعاع هو سبب أهمية الحماية في اللعبة. أرقام اللعبة مخترعة للعب وليست مأخوذة من هذه الدراسة.",
    "op_osdr_game_microgravity": "فكرة تعليمية: قد تغيّر الحياة في الفضاء جسم الإنسان لذلك تتابع اللعبة صحة الطاقم. أرقام اللعبة ليست مأخوذة من هذه الدراسة.",
    "op_osdr_game_health": "فكرة تعليمية: الحفاظ على صحة الطاقم في المهمات الطويلة يظهر في اللعبة كصحة الطاقم. لا تقدّم هذه البطاقة نصيحة طبية وأرقام اللعبة ليست مأخوذة منها.",
    "op_osdr_game_microbes": "فكرة تعليمية: إبقاء الهواء والماء والغذاء نظيفة جزء من دعم الحياة في اللعبة. لا تحاكي اللعبة الجراثيم ولا تستخدم أرقامًا من هذه الدراسة.",
    "op_osdr_disclaimer": "العنوان والوصف من كلمات ناسا نفسها. أما الجملة عن اللعبة فهي تبسيط تعليمي منا وليست نتيجة من هذه الدراسة.",
    "op_osdr_loading": "جارٍ تحميل بطاقات البحث من ناسا...",
    "op_osdr_error": "تعذّر الوصول إلى OSDR من ناسا الآن. نعرض البطاقات المحفوظة بدلًا من ذلك.",
    "op_osdr_empty": "لم يتم العثور على بطاقات بحث.",
    "op_osdr_src_live": "بيانات مباشرة من OSDR التابع لناسا.",
    "op_osdr_src_cached": "بيانات OSDR المحفوظة، جُلبت في {date}. ليست مباشرة.",
    "op_osdr_src_offline": "سجلّات OSDR دون اتصال، جُلبت في {date}. ليست مباشرة.",
    "op_osdr_src_none": "لا توجد بطاقات بحث متاحة الآن.",
    "op_osdr_card_live": "بيانات مباشرة", "op_osdr_card_cached": "بيانات محفوظة (ليست مباشرة)",
    "op_osdr_card_offline": "بيانات دون اتصال (ليست مباشرة)",
})

# ---- Outpost Command: screens, buttons and messages of the game interface (Phase 6). Resource, event, forecast, solar
# and research-card texts come from the earlier "op_*" blocks above and are reused, not repeated.
STRINGS["en"].update({
    "op_ui_menu": "Outpost Command", "op_ui_title": "OUTPOST COMMAND",
    "op_ui_setup_sub": "Run a lunar or Martian outpost. Share the power wisely and keep your crew alive, sol after sol.",
    "op_ui_location": "Location", "op_ui_site_moon": "Moon", "op_ui_site_mars": "Mars",
    "op_ui_difficulty": "Difficulty", "op_ui_start": "Start mission", "op_ui_resume": "Resume (sol {n})",
    "op_ui_research": "Research cards", "op_ui_refresh": "Refresh NASA data", "op_ui_best": "Best score: {n}",
    "op_ui_seed": "Seed: {n}",
    "op_ui_sol": "Sol {n} of {total}", "op_ui_resources": "Resources", "op_ui_allocation": "Power allocation",
    "op_ui_events": "Events and forecast", "op_ui_status": "Status",
    "op_ui_available": "Power available: {n}", "op_ui_allocated": "Allocated: {n}",
    "op_ui_unspent": "Left over (charges the battery): {n}", "op_ui_limit": "max {n}",
    "op_ui_focus": "Life Support focus", "op_ui_focus_oxygen": "Oxygen", "op_ui_focus_balanced": "Balanced",
    "op_ui_focus_food": "Food",
    "op_ui_hint_life_support": "Makes oxygen and food. The crew uses some every sol.",
    "op_ui_hint_shielding": "Rebuilds the radiation shield. It wears down every sol.",
    "op_ui_hint_comms": "Radio: lets you forecast the next event and receive supplies.",
    "op_ui_hint_science": "Earns score and may help with discoveries.",
    "op_ui_preview": "If nothing unexpected happens:",
    "op_ui_preview_note": "Events are not included here.",
    "op_ui_value_delta": "{name}: {value} ({delta})",
    "op_ui_warn_oxygen": "Oxygen would be dangerously low.", "op_ui_warn_food": "Food would be dangerously low.",
    "op_ui_warn_shielding": "The shield would be very weak.",
    "op_ui_warn_power": "Not enough power: blackout!",
    "op_ui_warn_lost_oxygen": "The crew would run out of oxygen!",
    "op_ui_warn_lost_food": "The crew would run out of food!",
    "op_ui_warn_lost_crew_health": "The crew would be too sick to continue!",
    "op_ui_forecast_title": "Mission control forecast", "op_ui_forecast_quiet": "No warning received.",
    "op_ui_comms_status": "Communications: {state}", "op_ui_comms_ok": "working", "op_ui_comms_weak": "too weak",
    "op_ui_comms_down": "radio down ({n} sols)",
    "op_ui_forecast_need": "Basic warnings need {a}+ Communications power. Exact forecasts need {b}+.",
    "op_ui_severity": "Severity: {level}", "op_ui_sev_low": "Low", "op_ui_sev_medium": "Medium",
    "op_ui_sev_high": "High",
    "op_ui_last_sol": "Last sol (sol {n})", "op_ui_no_event": "A quiet sol: nothing unexpected happened.",
    "op_ui_effects": "Active effects", "op_ui_no_effects": "No active effects.",
    "op_ui_effect_dust": "Dust on the panels: power output is at {percent}% for {sols} more sol(s).",
    "op_ui_effect_comms_down": "The radio is down for {sols} more sol(s).",
    "op_ui_nasa": "NASA data", "op_ui_donki_title": "Space weather (DONKI)", "op_ui_osdr_title": "Space biology (OSDR)",
    "op_ui_solar_note": "This level is a game mapping of recent NASA space-weather event counts. It is not a NASA radiation measurement or an official scientific index.",
    "op_ui_retrieved": "Retrieved: {date}", "op_ui_cards_count": "{n} research cards",
    "op_ui_checked": "Last checked: {when}",
    "op_ui_latest_event": "Newest NASA event: {date} (UTC)",
    "op_ui_latest_event_note": "NASA lists events as they happen, so the newest can be days old.",
    "op_ui_no_events": "NASA listed no solar events in this period.",
    "op_ui_solar_short": "A game mapping, not a NASA measurement.",
    "op_ui_nasa_loading": "Checking NASA data in the background...", "op_ui_nasa_done": "NASA data checked.",
    "op_ui_nasa_failed": "Could not update NASA data. Using saved data.",
    "op_ui_nasa_unreachable": "Could not reach NASA. Using saved data.",
    "op_ui_advance": "Advance to next sol", "op_ui_reset": "Reset",
    "op_ui_status_running": "In progress", "op_ui_status_won": "Mission complete", "op_ui_status_lost": "Mission failed",
    "op_ui_result_won": "MISSION COMPLETE", "op_ui_result_lost": "MISSION FAILED", "op_ui_stars": "Stars: {n}",
    "op_ui_final_score": "Final score: {n}", "op_ui_sols_survived": "Sols survived: {n} of {total}",
    "op_ui_why_failed": "What happened", "op_ui_play_again": "Play again",
    "op_ui_cards_title": "Space research cards", "op_ui_card_n": "Card {n} of {total}",
    "op_ui_prev": "Previous", "op_ui_filter_all": "All topics", "op_ui_open_nasa": "Open NASA study page",
    "op_ui_help": "Keys: Enter = next sol, R = reset, Esc = back. Hold Shift to change by 5.",
})
STRINGS["ar"].update({
    "op_ui_menu": "قيادة القاعدة", "op_ui_title": "قيادة القاعدة",
    "op_ui_setup_sub": "أدِر قاعدة على القمر أو المريخ. وزّع الطاقة بحكمة وحافظ على طاقمك حيًّا سولًا بعد سول.",
    "op_ui_location": "الموقع", "op_ui_site_moon": "القمر", "op_ui_site_mars": "المريخ",
    "op_ui_difficulty": "الصعوبة", "op_ui_start": "ابدأ المهمة", "op_ui_resume": "تابع (السول {n})",
    "op_ui_research": "بطاقات البحث", "op_ui_refresh": "حدّث بيانات ناسا", "op_ui_best": "أفضل نتيجة: {n}",
    "op_ui_seed": "البذرة: {n}",
    "op_ui_sol": "السول {n} من {total}", "op_ui_resources": "الموارد", "op_ui_allocation": "توزيع الطاقة",
    "op_ui_events": "الأحداث والتوقعات", "op_ui_status": "الحالة",
    "op_ui_available": "الطاقة المتاحة: {n}", "op_ui_allocated": "الموزَّع: {n}",
    "op_ui_unspent": "المتبقي (يشحن البطارية): {n}", "op_ui_limit": "الحد الأقصى {n}",
    "op_ui_focus": "تركيز دعم الحياة", "op_ui_focus_oxygen": "الأكسجين", "op_ui_focus_balanced": "متوازن",
    "op_ui_focus_food": "الغذاء",
    "op_ui_hint_life_support": "ينتج الأكسجين والغذاء. ويستهلك الطاقم بعضها كل سول.",
    "op_ui_hint_shielding": "يعيد بناء درع الإشعاع. وهو يتآكل كل سول.",
    "op_ui_hint_comms": "الراديو: يتيح لك توقّع الحدث القادم واستقبال الإمدادات.",
    "op_ui_hint_science": "يكسبك نقاطًا وقد يساعد في الاكتشافات.",
    "op_ui_preview": "إن لم يحدث شيء غير متوقع:",
    "op_ui_preview_note": "الأحداث غير محسوبة هنا.",
    "op_ui_value_delta": "{name}: {value} ({delta})",
    "op_ui_warn_oxygen": "سيصبح الأكسجين منخفضًا بشكل خطير.", "op_ui_warn_food": "سيصبح الغذاء منخفضًا بشكل خطير.",
    "op_ui_warn_shielding": "سيصبح الدرع ضعيفًا جدًّا.",
    "op_ui_warn_power": "الطاقة لا تكفي: سيحدث انقطاع!",
    "op_ui_warn_lost_oxygen": "سينفد الأكسجين من الطاقم!",
    "op_ui_warn_lost_food": "سينفد الغذاء من الطاقم!",
    "op_ui_warn_lost_crew_health": "سيمرض الطاقم ولن يستطيع المتابعة!",
    "op_ui_forecast_title": "توقعات مركز التحكم", "op_ui_forecast_quiet": "لم يصل أي تحذير.",
    "op_ui_comms_status": "الاتصالات: {state}", "op_ui_comms_ok": "تعمل", "op_ui_comms_weak": "ضعيفة جدًّا",
    "op_ui_comms_down": "الراديو متوقف ({n} سول)",
    "op_ui_forecast_need": "التحذيرات الأساسية تحتاج {a} أو أكثر من طاقة الاتصالات والتوقع الدقيق يحتاج {b} أو أكثر.",
    "op_ui_severity": "الخطورة: {level}", "op_ui_sev_low": "منخفضة", "op_ui_sev_medium": "متوسطة",
    "op_ui_sev_high": "عالية",
    "op_ui_last_sol": "السول الأخير (السول {n})", "op_ui_no_event": "سول هادئ: لم يحدث شيء غير متوقع.",
    "op_ui_effects": "التأثيرات الجارية", "op_ui_no_effects": "لا توجد تأثيرات جارية.",
    "op_ui_effect_dust": "الغبار على الألواح: إنتاج الطاقة {percent}% لمدة {sols} سول إضافي.",
    "op_ui_effect_comms_down": "الراديو متوقف لمدة {sols} سول إضافي.",
    "op_ui_nasa": "بيانات ناسا", "op_ui_donki_title": "الطقس الفضائي (DONKI)", "op_ui_osdr_title": "علم الأحياء الفضائي (OSDR)",
    "op_ui_solar_note": "هذا المستوى تحويل للعبة لأعداد أحداث الطقس الفضائي الأخيرة من ناسا. وهو ليس قياسًا إشعاعيًّا من ناسا ولا مؤشرًا علميًّا رسميًّا.",
    "op_ui_retrieved": "تاريخ الجلب: {date}", "op_ui_cards_count": "{n} بطاقة بحث",
    "op_ui_checked": "آخر فحص: {when}",
    "op_ui_latest_event": "أحدث حدث من ناسا: {date} (بتوقيت UTC)",
    "op_ui_latest_event_note": "تسجّل ناسا الأحداث عند وقوعها، فقد يكون أحدثها قديمًا.",
    "op_ui_no_events": "لم تسجّل ناسا أحداثًا شمسية في هذه الفترة.",
    "op_ui_solar_short": "تحويل للعبة وليس قياسًا من ناسا.",
    "op_ui_nasa_loading": "جارٍ فحص بيانات ناسا في الخلفية...", "op_ui_nasa_done": "تم فحص بيانات ناسا.",
    "op_ui_nasa_failed": "تعذّر تحديث بيانات ناسا. نستخدم البيانات المحفوظة.",
    "op_ui_nasa_unreachable": "تعذّر الوصول إلى ناسا. نستخدم البيانات المحفوظة.",
    "op_ui_advance": "انتقل إلى السول التالي", "op_ui_reset": "إعادة الضبط",
    "op_ui_status_running": "قيد التنفيذ", "op_ui_status_won": "اكتملت المهمة", "op_ui_status_lost": "فشلت المهمة",
    "op_ui_result_won": "اكتملت المهمة", "op_ui_result_lost": "فشلت المهمة", "op_ui_stars": "النجوم: {n}",
    "op_ui_final_score": "النتيجة النهائية: {n}", "op_ui_sols_survived": "السولات التي نجوتَ فيها: {n} من {total}",
    "op_ui_why_failed": "ماذا حدث", "op_ui_play_again": "العب مجددًا",
    "op_ui_cards_title": "بطاقات البحث الفضائي", "op_ui_card_n": "البطاقة {n} من {total}",
    "op_ui_prev": "السابق", "op_ui_filter_all": "كل المواضيع", "op_ui_open_nasa": "افتح صفحة الدراسة في ناسا",
    "op_ui_help": "المفاتيح: Enter للسول التالي و R لإعادة الضبط و Esc للرجوع. اضغط Shift لتغيير القيمة بمقدار 5.",
})

# ---- Outpost Command: what the player sees when a screen cannot be drawn (Phase 6 remediation)
STRINGS["en"].update({
    "op_ui_error_title": "Something went wrong",
    "op_ui_error_notice": "This screen could not be updated, so the last good screen is still showing. The details were saved in the log.",
    "op_ui_error_repeated": "This keeps happening, so automatic updates are paused. You can keep playing with the buttons. The details were saved in the log.",
    "op_ui_error_screen": "This screen could not be drawn. The details were saved in the log. You can try again or go back to the main menu.",
    "op_ui_error_retry": "Try again", "op_ui_dismiss": "OK",
})
STRINGS["ar"].update({
    "op_ui_error_title": "حدث خطأ ما",
    "op_ui_error_notice": "تعذّر تحديث هذه الشاشة لذلك ما زالت آخر شاشة سليمة ظاهرة. وقد حُفظت التفاصيل في السجل.",
    "op_ui_error_repeated": "تتكرر هذه المشكلة لذلك أُوقف التحديث التلقائي مؤقتًا. يمكنك متابعة اللعب بالأزرار. وقد حُفظت التفاصيل في السجل.",
    "op_ui_error_screen": "تعذّر رسم هذه الشاشة. وقد حُفظت التفاصيل في السجل. يمكنك المحاولة مرة أخرى أو العودة إلى القائمة الرئيسية.",
    "op_ui_error_retry": "حاول مرة أخرى", "op_ui_dismiss": "حسنًا",
})
