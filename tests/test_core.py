import pytest

from astro import progression as prog
from astro import session
from astro.assistant import SpaceAssistant
from astro.db import Database
from astro.missions import MISSIONS, MISSIONS_BY_ID, MissionState, is_unlocked


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


@pytest.fixture
def pid(db):
    return db.create_profile("Nova", "mid", "orange", "blue")


# ---------- database ----------
def test_profile_crud_and_validation(db):
    assert db.list_profiles() == []
    with pytest.raises(ValueError):
        db.create_profile("   ")
    with pytest.raises(ValueError):
        db.create_profile("X", age_group="baby")
    pid = db.create_profile("Nova'; DROP TABLE profiles;--", "teen")
    assert db.get_profile(pid)["name"].startswith("Nova")      # injection stays inert
    assert len(db.list_profiles()) == 1
    db.delete_profile(pid)
    assert db.list_profiles() == []


def test_xp_never_negative_and_settings_upsert(db, pid):
    assert db.add_xp(pid, 30) == 30
    assert db.add_xp(pid, -100) == 0
    db.set_setting(pid, "volume", 3)
    db.set_setting(pid, "volume", 7)
    assert db.get_setting(pid, "volume") == "7"
    assert db.get_setting(pid, "missing", "d") == "d"


def test_achievement_granted_once(db, pid):
    assert db.grant_achievement(pid, "first_mission") is True
    assert db.grant_achievement(pid, "first_mission") is False
    assert db.list_achievements(pid) == ["first_mission"]


def test_data_persists_across_connections(tmp_path):
    path = tmp_path / "p.db"
    a = Database(path)
    pid = a.create_profile("Sol")
    a.record_completion(pid, "moon", 3)
    b = Database(path)
    assert b.completed_missions(pid) == {"moon"}


# ---------- progression ----------
def test_levels_and_tiers():
    assert prog.level_from_xp(0) == 1 and prog.level_from_xp(50) == 2
    assert prog.level_from_xp(prog.xp_for_level(5)) == 5
    assert prog.tier_from_skill(0.1) == "easy"
    assert prog.tier_from_skill(0.5) == "normal"
    assert prog.tier_from_skill(0.9) == "hard"


def test_skill_adapts_both_ways():
    assert prog.update_skill(0.5, 0, 0) > 0.5
    assert prog.update_skill(0.5, 4, 3) < 0.5
    s = 0.5
    for _ in range(6):
        s = prog.update_skill(s, 0, 0)
    assert prog.tier_from_skill(s) == "hard"
    for _ in range(10):
        s = prog.update_skill(s, 5, 5)
    assert prog.tier_from_skill(s) == "easy"


def test_stars_and_xp():
    assert prog.stars(0, 0) == 3 and prog.stars(1, 1) == 2 and prog.stars(3, 0) == 1
    assert prog.mission_xp(100, 50, 0, "hard") > prog.mission_xp(100, 50, 0, "easy")
    assert prog.mission_xp(1, 0, 50, "hard") == 10   # floor


# ---------- missions ----------
def play_perfectly(state):
    m = state.mission
    for o in m.objectives:
        tool = {"scan": "scanner", "collect": "sampler", "analyze": "analyzer", "repair": "wrench"}[o.action]
        res = state.use_tool(tool, o.target)
        assert res.ok, res.message
        if o.action == "repair":
            assert res.needs_choice
            correct = next(i for i, opt in state.repair_options(o.target) if opt.correct)
            assert state.repair(o.target, correct).ok


@pytest.mark.parametrize("mission", MISSIONS, ids=lambda m: m.id)
@pytest.mark.parametrize("tier", ["easy", "normal", "hard"])
def test_every_mission_completable(mission, tier):
    s = MissionState(mission, tier)
    play_perfectly(s)
    assert s.complete and s.mistakes == 0 and len(s.evidence) >= 4


def test_dependencies_enforced():
    s = MissionState(MISSIONS_BY_ID["moon"])
    assert not s.use_tool("analyzer", "regolith").ok                # needs sample
    r = s.use_tool("wrench", "power_relay")                         # needs diagnosis
    assert not r.ok and s.mistakes == 1
    assert not s.use_tool("sampler", "solar_array").ok              # nothing to collect
    assert not s.use_tool("scanner", None).ok


def test_wrong_repair_costs_mistake_and_can_retry():
    s = MissionState(MISSIONS_BY_ID["moon"], "hard")
    s.use_tool("scanner", "power_relay")
    wrong = next(i for i, o in s.repair_options("power_relay") if not o.correct)
    r = s.repair("power_relay", wrong)
    assert not r.ok and s.mistakes == 1 and not s.complete
    good = next(i for i, o in s.repair_options("power_relay") if o.correct)
    assert s.repair("power_relay", good).ok


def test_difficulty_changes_option_count_and_hints():
    counts = {t: len(MissionState(MISSIONS_BY_ID["mars"], t).repair_options("rover"))
              for t in ("easy", "normal", "hard")}
    assert counts == {"easy": 2, "normal": 3, "hard": 4}
    easy = MissionState(MISSIONS_BY_ID["mars"], "easy").hint()
    hard = MissionState(MISSIONS_BY_ID["mars"], "hard").hint()
    assert "Mars" not in hard and len(easy) != len(hard)
    assert "Dry Riverbed" in easy


def test_hints_are_counted():
    s = MissionState(MISSIONS_BY_ID["moon"])
    s.hint(); s.hint()
    assert s.hints == 2


# ---------- session / progression integration ----------
def test_unlock_chain_and_persistence(db, pid):
    moon, mars = MISSIONS_BY_ID["moon"], MISSIONS_BY_ID["mars"]
    assert is_unlocked(moon, set()) and not is_unlocked(mars, set())
    with pytest.raises(PermissionError):
        session.start_mission(db, pid, mars)
    s = session.start_mission(db, pid, moon)
    with pytest.raises(ValueError):
        session.finish_mission(db, pid, s, 10)       # incomplete
    play_perfectly(s)
    out = session.finish_mission(db, pid, s, 42.0)
    assert out["stars"] == 3 and "mars" in out["unlocked"]
    assert {"first_mission", "flawless"} <= set(out["achievements"])
    assert db.get_profile(pid)["xp"] == out["total_xp"] > 0
    assert db.get_profile(pid)["skill"] > 0.5
    assert len(db.performance_history(pid)) == 1
    listing = {r["mission"].id: r for r in session.mission_list(db, pid)}
    assert listing["mars"]["unlocked"] and listing["moon"]["completed"] and not listing["orbital"]["unlocked"]
    session.start_mission(db, pid, mars)             # now allowed


def test_full_campaign_unlocks_everything(db, pid):
    last = None
    for m in MISSIONS:
        s = session.start_mission(db, pid, m)
        play_perfectly(s)
        last = session.finish_mission(db, pid, s, 1)
    assert "explorer" in db.list_achievements(pid)
    assert "scientist" not in db.list_achievements(pid)    # only 4 samples so far
    s = session.start_mission(db, pid, MISSIONS[0])        # replay
    play_perfectly(s)
    session.finish_mission(db, pid, s, 1)
    assert "scientist" in db.list_achievements(pid)


def test_poor_play_lowers_tier(db, pid):
    for _ in range(4):
        s = session.start_mission(db, pid, MISSIONS[0])
        s.mistakes, s.hints = 4, 4
        play_perfectly(s)
        s.mistakes, s.hints = 4, 4
        session.finish_mission(db, pid, s, 1)
    assert session.current_tier(db, pid) == "easy"


# ---------- assistant ----------
def test_assistant_retrieval_offline():
    a = SpaceAssistant(use_chroma=False)
    assert a.backend == "keyword"
    ans = a.ask("Why do astronauts float?", "orbital", "mid")
    assert "free fall" in ans
    assert "falling" in a.ask("Why do astronauts float?", "orbital", "young")
    assert "dust" in a.ask("what is regolith", "moon").lower()
    assert "Ask me" in a.ask("   ")
    assert "don't have data" in a.ask("xyzzy plugh", None)


# ---------- ChromaDB code path (uses a tiny local embedder so no model download is needed) ----------
def test_chroma_retrieval_path(tmp_path, monkeypatch):
    chromadb = pytest.importorskip("chromadb")
    import hashlib
    from astro import config
    from astro.assistant import _tokens

    class HashEmbed(chromadb.EmbeddingFunction):
        def __init__(self): pass
        @staticmethod
        def name(): return "hash-embed"
        def get_config(self): return {}
        @staticmethod
        def build_from_config(cfg): return HashEmbed()
        def __call__(self, input):
            out = []
            for text in input:
                v = [0.0] * 256
                for t in _tokens(text):
                    v[int(hashlib.md5(t.encode()).hexdigest(), 16) % 256] += 1.0
                out.append(v)
            return out

    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    a = SpaceAssistant(use_chroma=True, embedding_function=HashEmbed())
    assert a.backend == "chroma"
    docs = a.retrieve("why do astronauts float in orbit", "orbital", "young")
    assert docs and docs[0]["id"] == "iss-freefall-en-young"       # age-appropriate doc ranked first
    assert "falling" in a.ask("why do astronauts float in orbit", "orbital", "young")
