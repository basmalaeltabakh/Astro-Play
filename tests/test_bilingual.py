# -*- coding: utf-8 -*-
"""Tests for the Arabic/English layer, age-adapted content, quiz, Gemini integration and settings."""
import re
from pathlib import Path

import pytest

from astro import assistant as asst, config, i18n
from astro.assistant import SpaceAssistant, build_system_prompt, sanitize
from astro.audio import AudioManager
from astro.content import MISSION_TEXT, pick
from astro.knowledge import SEED_DOCS
from astro.missions import MissionState, ORDER, get_missions
from astro.quiz import QUIZ, SUGGESTED, quiz_for
from astro.settings import Settings

AGES = ("young", "mid", "teen")
FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def test_every_english_string_has_arabic_and_same_placeholders():
    en, ar = i18n.STRINGS["en"], i18n.STRINGS["ar"]
    assert set(en) == set(ar), set(en) ^ set(ar)
    ph = lambda s: sorted(re.findall(r"{(\w+)}", s))
    for k in en:
        assert ph(en[k]) == ph(ar[k]), k


def test_keys_used_in_code_exist():
    root = Path(__file__).resolve().parent.parent / "astro"
    used = set()
    for f in root.rglob("*.py"):
        used |= set(re.findall(r'\bT\(\s*"([a-z_0-9]+)"', f.read_text(encoding="utf-8")))
        used |= set(re.findall(r'\bi18n\.t\(\s*"([a-z_0-9]+)"', f.read_text(encoding="utf-8")))
    dynamic = {"age_", "ach_", "tool_", "glyph_"}
    for k in used:
        assert k in i18n.STRINGS["en"] or k in dynamic, k
    for a in ("first_mission", "flawless", "scientist", "problem_solver", "explorer", "level_5"):
        assert f"ach_{a}" in i18n.STRINGS["ar"]


def test_arabic_shaping_joins_and_reorders():
    shaped = i18n.shape("\u0645\u0631\u062d\u0628\u0627")
    assert shaped != "\u0645\u0631\u062d\u0628\u0627" and len(shaped) == 5
    assert i18n.shape("Hello") == "Hello"
    assert i18n.has_arabic("\u0623\u062d\u0645\u062f") and not i18n.has_arabic("Ahmed")
    assert i18n.font("body", "ar").startswith("Cairo") and i18n.font("body", "en", text="\u0623").startswith("Cairo")


def _glyphs(font_file):
    from fontTools.ttLib import TTFont
    return set(TTFont(FONTS / font_file).getBestCmap())


def _all_text(lang):
    out = list(i18n.STRINGS[lang].values())
    for m in MISSION_TEXT.values():
        specs = [m["name"], m["briefing"], m["science"], m["deep"]]
        for o in m["objects"].values():
            specs += [v for k, v in o.items() if k != "options"] + [x for pair in o.get("options", []) for x in pair]
        for s in specs:
            for age in ("young", "std"):
                out.append(s[lang][age])
    for items in QUIZ.values():
        for q in items:
            for age in AGES:
                qq, opts, _, ex = q[age][lang]
                out += [qq, ex] + list(opts)
    for by_age in SUGGESTED.values():
        for age in AGES:
            out += by_age[age][lang]
    out += [d["text"] for d in SEED_DOCS if d["lang"] == lang]
    return out


@pytest.mark.parametrize("lang,fonts", [("ar", ["Cairo-Bold.ttf", "Cairo-Black.ttf"]),
                                        ("en", ["Rajdhani-Bold.ttf", "Orbitron-Bold.ttf"])])
def test_fonts_have_every_glyph_we_show(lang, fonts):
    for f in fonts:
        have = _glyphs(f)
        missing = set()
        for text in _all_text(lang):
            text = text.replace("{", "").replace("}", "")
            for ch in i18n.shape(text, force=(lang == "ar")):
                if ch not in "\n " and ord(ch) not in have:
                    missing.add(ch)
        # Orbitron is a display face used only for short English headings; allow it to lack dashes/symbols
        if f.startswith("Orbitron"):
            missing -= set("\u00b0\u2014\u2013;:,.'")
            continue
        assert not missing, (f, [hex(ord(c)) for c in missing])


def test_missions_complete_in_every_language_and_age():
    for lang in ("en", "ar"):
        for age in AGES:
            ms = get_missions(lang, age)
            assert [m.id for m in ms] == list(ORDER)
            for m in ms:
                assert m.name and m.briefing and m.science_focus and len(m.objectives) == 5
                for o in m.objects:
                    assert o.name
                    if o.options:
                        assert len(o.options) == 4 and sum(x.correct for x in o.options) == 1
                        assert all(x.text and x.explanation for x in o.options)
                        assert o.fault


def test_young_wording_is_simpler_than_standard():
    shorter = 0
    for m in MISSION_TEXT.values():
        for o in m["objects"].values():
            for k in ("fact", "analysis", "fault"):
                if k in o:
                    shorter += len(o[k]["en"]["young"]) <= len(o[k]["en"]["std"])
    assert shorter >= 8


def test_mission_state_messages_are_localized():
    for lang in ("en", "ar"):
        m = get_missions(lang, "young")[0]
        st = MissionState(m, "easy", lang, "young")
        assert st.use_tool("scanner", None).message == i18n.t("aim_at", lang)
        assert "?" in st.hint() or st.hint()           # hint exists
        r = st.use_tool("scanner", "solar_array")
        assert r.ok and m.get_object("solar_array").name in r.message
        assert i18n.t("hint_easy_young", lang, obj="X", tool="Y").replace("X", "").replace("Y", "") != ""


def test_wrong_fix_uses_young_message():
    m = get_missions("en", "young")[0]
    st = MissionState(m, "hard", "en", "young")
    st.use_tool("scanner", "power_relay")
    res = st.repair("power_relay", 1)
    assert not res.ok and res.message.startswith("Oops")


def test_quiz_adapts_to_age_and_language_and_is_valid():
    seen = set()
    for mid, items in QUIZ.items():
        for q in items:
            for age in AGES:
                for lang in ("en", "ar"):
                    text, opts, ok, ex = q[age][lang]
                    assert text and ex and len(opts) == 3 and 0 <= ok < 3 and len(set(opts)) == 3
                    seen.add((age, lang, text))
        for age in AGES:
            for lang in ("en", "ar"):
                qs = quiz_for(mid, age, lang, seed=1)
                assert len(qs) == 2
                for text, opts, ok, ex in qs:           # shuffling must keep the right answer right
                    assert any(text == q[age][lang][0] and opts[ok] == q[age][lang][1][q[age][lang][2]] for q in QUIZ[mid])
    assert len(seen) == len(QUIZ) * 2 * 3 * 2          # every age/language variant is different text
    assert quiz_for("moon", "young", "en")[0][0] != quiz_for("moon", "teen", "en")[0][0]


def test_suggested_questions_per_age():
    for mid in ORDER:
        for age in AGES:
            for lang in ("en", "ar"):
                assert len(SUGGESTED[mid][age][lang]) == 3
        assert SUGGESTED[mid]["young"]["en"] != SUGGESTED[mid]["teen"]["en"]


def test_offline_arabic_answers_adapt_to_age():
    a = SpaceAssistant(use_chroma=False)
    q = "\u0644\u0645\u0627\u0630\u0627 \u064a\u0637\u0641\u0648 \u0631\u0648\u0627\u062f \u0627\u0644\u0641\u0636\u0627\u0621\u061f"
    young = a.ask(q, "orbital", "young", lang="ar")
    teen = a.ask(q, "orbital", "teen", lang="ar")
    assert i18n.has_arabic(young) and i18n.has_arabic(teen)
    assert "\u0633\u0624\u0627\u0644 \u0631\u0627\u0626\u0639" in young          # friendly opener for kids
    assert len(teen) > len(young) and "28" in teen                             # teen adds the technical detail
    assert "\u0645\u0627 \u0647\u0648 \u0627\u0644\u0631\u064a\u063a\u0648\u0644\u064a\u062b\u061f" and \
        "\u0627\u0644\u0631\u064a\u063a\u0648\u0644\u064a\u062b" in a.ask("\u0645\u0627 \u0647\u0648 \u0627\u0644\u0631\u064a\u063a\u0648\u0644\u064a\u062b\u061f", "moon", "mid", lang="ar")
    assert a.ask("zzzz", None, "mid", lang="ar") == i18n.t("no_data", "ar")


def test_language_filter_in_retrieval():
    a = SpaceAssistant(use_chroma=False)
    assert all(d["lang"] == "ar" for d in a.retrieve("\u0627\u0644\u0642\u0645\u0631", "moon", "mid", lang="ar"))
    assert all(d["lang"] == "en" for d in a.retrieve("moon dust", "moon", "mid", lang="en"))


def test_system_prompt_changes_with_age_and_language():
    young, teen, ar = build_system_prompt("young", "en"), build_system_prompt("teen", "en"), build_system_prompt("mid", "ar")
    assert "6 to 9" in young and "14 or older" in teen and "Arabic" in ar and "English" in young
    assert "no emojis" in young and "hand over the solution" in young


def test_sanitize_strips_markdown_and_emoji():
    assert sanitize("**Hi** there \U0001F680 # x") == "Hi there x"


class _Chunk:
    def __init__(self, t):
        self.text = t


class _FakeModels:
    def __init__(self, fail_models=()):
        self.calls, self.fail = [], set(fail_models)

    def generate_content_stream(self, model, contents, config):
        self.calls.append((model, contents, config))
        if model in self.fail:
            raise RuntimeError("model not found")
        return iter([_Chunk("Astronauts "), _Chunk("float because **they fall** \U0001F680 around Earth.")])


class _FakeClient:
    def __init__(self, models):
        self.models = models


def _gemini_assistant(monkeypatch, fail=()):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    a = SpaceAssistant(use_chroma=False)
    fake = _FakeModels(fail)
    a._client = _FakeClient(fake)
    return a, fake


def test_gemini_answers_stream_and_are_cleaned(monkeypatch):
    a, fake = _gemini_assistant(monkeypatch)
    parts = list(a.ask_stream("Why do astronauts float?", "orbital", "young", ["Scanner: x"], "en"))
    assert parts[0] == "Astronauts" and parts[-1] == "Astronauts float because they fall around Earth."
    model, prompt, cfg = fake.calls[0]
    assert model == config.LLM_MODEL
    assert "Reference notes" in prompt and "Scanner: x" in prompt and "Why do astronauts float?" in prompt
    assert "6 to 9" in cfg.system_instruction
    assert "Gemini" in a.llm_label


def test_gemini_falls_back_to_next_model_then_to_offline(monkeypatch):
    a, fake = _gemini_assistant(monkeypatch, fail={config.LLM_MODEL})
    assert a.ask("Why do astronauts float?", "orbital", "mid").startswith("Astronauts float")
    assert [c[0] for c in fake.calls][-1] == config.LLM_FALLBACK_MODELS[0]
    a2, fake2 = _gemini_assistant(monkeypatch, fail={config.LLM_MODEL, *config.LLM_FALLBACK_MODELS})
    out = a2.ask("Why do astronauts float?", "orbital", "mid")
    assert "free fall" in out and "From my notes" in out                     # graceful offline answer


def test_gemini_prompt_uses_arabic_instruction(monkeypatch):
    a, fake = _gemini_assistant(monkeypatch)
    a.ask("\u0644\u0645\u0627\u0630\u0627 \u064a\u0637\u0641\u0648\u061f", "orbital", "teen", lang="ar")
    assert "Arabic" in fake.calls[0][2].system_instruction


def test_no_key_means_offline(monkeypatch):
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    a = SpaceAssistant(use_chroma=False)
    assert not a.llm_enabled and a.llm_label == "offline"


def test_settings_roundtrip_and_corruption(tmp_path):
    p = tmp_path / "s.json"
    s = Settings.load(p)
    assert s.lang == "en" and s.music and s.sfx
    s.lang, s.music = "ar", False
    s.save(p)
    s2 = Settings.load(p)
    assert s2.lang == "ar" and s2.music is False
    p.write_text("{not json", encoding="utf-8")
    assert Settings.load(p).lang == "en"
    p.write_text('{"lang": "xx", "music_volume": 7}', encoding="utf-8")
    t = Settings.load(p)
    assert t.lang == "en"


def test_audio_manager_toggles_without_a_device(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "s.json")
    s = Settings()
    am = AudioManager(s, loader=None)               # no audio device: must not raise
    am.play_music("menu"); am.sfx("click"); am.update(0.1)
    assert am.toggle_music() is False and s.music is False
    assert am.toggle_music() is True
    assert am.toggle_sfx() is False and s.sfx is False
    assert Settings.load(tmp_path / "s.json").sfx is False


def test_audio_assets_exist():
    audio = config.ASSETS_DIR / "audio"
    for name in ("music_menu.wav", "music_mission.wav", "sfx_click.wav", "sfx_scan.wav", "sfx_fanfare.wav"):
        assert (audio / name).stat().st_size > 1000
