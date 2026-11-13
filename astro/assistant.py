# -*- coding: utf-8 -*-
"""AI Space Assistant: retrieval-augmented answers with graceful fallbacks.

Retrieval order : ChromaDB (if installed and working)  ->  built-in keyword retrieval (English + Arabic).
Answer order    : Gemini (if GEMINI_API_KEY is set)    ->  answer composed from retrieved passages.
Answers adapt to the player's age group (young 6-9, mid 10-13, teen 14+) and language (en / ar).
The assistant never reveals mission answers directly; it nudges.
"""
import logging
import re
import unicodedata
from typing import Dict, Iterator, List, Optional

from . import config
from .knowledge import SEED_DOCS

log = logging.getLogger("astro.assistant")

_WORD = re.compile(r"[a-z0-9]+|[\u0621-\u063a\u0641-\u064a\u0671-\u06d3]+")
_TASHKEEL = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u0640]")
_STOP = {"the", "a", "an", "is", "are", "of", "to", "and", "in", "it", "why", "what", "how", "do", "does", "on",
         "for", "i", "my", "me", "can", "this", "that", "there", "was", "were", "be", "we", "you",
         "في", "من", "على", "الى", "عن", "هل", "ما", "ماذا", "لماذا", "كيف", "هو", "هي", "هذا", "هذه", "ذلك", "تلك",
         "ان", "او", "ثم", "كان", "كانت", "انا", "نحن", "هناك", "مع", "الذي", "التي", "ايضا"}
MISSION_TOPIC = {"orbital": "orbit"}               # mission id -> knowledge topic tag
_EMOJI = re.compile("[\U00010000-\U0010FFFF\u2600-\u27BF\uFE0F\u200d\u2B50\u2B06]")


def _norm_ar(w: str) -> str:
    w = _TASHKEEL.sub("", w)
    w = re.sub("[\u0623\u0625\u0622]", "\u0627", w)
    w = w.replace("\u0649", "\u064a").replace("\u0629", "\u0647")
    for pre in ("\u0648\u0627\u0644", "\u0644\u0644", "\u0627\u0644", "\u0648"):   # wal- / lil- / al- / wa-
        if w.startswith(pre) and len(w) - len(pre) >= 3:
            w = w[len(pre):]
            break
    for suf in ("\u0627\u062a", "\u0648\u0646", "\u064a\u0646", "\u0647\u0627"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    return w


def _tokens(text: str) -> List[str]:
    out = []
    for w in _WORD.findall(_TASHKEEL.sub("", unicodedata.normalize("NFKC", (text or "").lower()))):
        if "\u0600" <= w[0] <= "\u06ff":
            w = _norm_ar(w)
        if w and w not in _STOP:
            out.append(w)
    return out


def sanitize(text: str) -> str:
    """Make LLM output safe for our fonts: strip markdown, emoji and extra whitespace."""
    text = _EMOJI.sub("", text or "")
    text = re.sub(r"[*#`_>]+", "", text)
    text = re.sub(r"^\s*[-\u2022]\s+", "", text, flags=re.M)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _level_pref(doc_level: str, age: str) -> float:
    if doc_level == age:
        return 1.0
    if age == "young" and doc_level != "young":
        return -0.5
    if age == "teen" and doc_level == "mid":
        return 0.4
    if age == "mid" and doc_level == "teen":
        return 0.3
    return 0.0


class KeywordIndex:
    def __init__(self, docs: List[Dict]):
        self.docs = docs
        self._cache = {}

    def _words(self, d):
        key = d["id"]
        if key not in self._cache:
            self._cache[key] = set(_tokens(d["text"])) | set(w for t in d["topics"] for w in _tokens(t))
        return self._cache[key]

    def query(self, question: str, mission_id: Optional[str], age_group: str, k: int = 3,
              lang: str = "en") -> List[Dict]:
        q = set(_tokens(question))
        topic = MISSION_TOPIC.get(mission_id, mission_id)
        best: Dict[str, tuple] = {}
        for d in self.docs:
            if d.get("lang", "en") != lang:
                continue
            overlap = len(q & self._words(d))
            if overlap == 0:
                continue  # bonuses alone must never make an unrelated passage relevant
            score = overlap + (1.5 if topic and topic in d["topics"] else 0.0) + _level_pref(d["level"], age_group)
            base = d.get("base", d["id"])
            if base not in best or score > best[base][0]:        # one level variant per topic
                best[base] = (score, d)
        ranked = sorted(best.values(), key=lambda p: -p[0])
        return [d for s, d in ranked if s > 0][:k]


class ChromaIndex:
    """Vector retrieval. Uses Chroma's default local embedding model (all-MiniLM-L6-v2 via ONNX)."""

    def __init__(self, docs: List[Dict], path, embedding_function=None):
        import chromadb  # optional dependency
        self.client = chromadb.PersistentClient(path=str(path))
        kwargs = {"embedding_function": embedding_function} if embedding_function else {}
        self.col = self.client.get_or_create_collection("astro_science_v2", **kwargs)
        self.col.upsert(
            ids=[d["id"] for d in docs], documents=[d["text"] for d in docs],
            metadatas=[{"topics": ",".join(d["topics"]), "level": d["level"], "lang": d.get("lang", "en"),
                        "base": d.get("base", d["id"]), "source": d["source"]} for d in docs])

    def query(self, question: str, mission_id: Optional[str], age_group: str, k: int = 3,
              lang: str = "en") -> List[Dict]:
        q = f"{question} ({mission_id})" if mission_id else question
        res = self.col.query(query_texts=[q], n_results=k * 6, where={"lang": lang})
        out, seen = [], set()
        for i, doc in enumerate(res["documents"][0]):
            meta = res["metadatas"][0][i]
            out.append({"id": res["ids"][0][i], "text": doc, "topics": meta["topics"].split(","), "lang": lang,
                        "level": meta["level"], "base": meta.get("base", res["ids"][0][i]), "source": meta["source"]})
        out.sort(key=lambda d: -_level_pref(d["level"], age_group))   # stable: prefer age-appropriate
        picked = []
        for d in out:                                                  # one level variant per topic
            if d["base"] not in seen:
                seen.add(d["base"])
                picked.append(d)
        return picked[:k]


# ---------------------------------------------------------------------------------- prompts
_AGE_STYLE = {
    "young": ("a curious child aged 6 to 9",
              "Use only words a 6-year-old knows. Sentences under 12 words. At most 3 short sentences (about 40 words). "
              "Compare the idea to everyday things like toys, food, pets or a playground. Sound warm, excited and playful. "
              "End with ONE tiny fun question that makes them think."),
    "mid": ("a student aged 10 to 13",
            "Use clear, friendly words. 3 to 5 sentences (up to 70 words). Use one fun comparison. "
            "If you use a science word, explain it in simple words right away. Be encouraging."),
    "teen": ("a teenager aged 14 or older",
             "Be precise but still friendly. Up to 110 words. Name the mechanism and include one number or real example when useful. "
             "Treat them as capable. End with one thought-provoking 'what if' or 'why do you think' question."),
}


def build_system_prompt(age_group: str, lang: str) -> str:
    who, style = _AGE_STYLE.get(age_group, _AGE_STYLE["mid"])
    language = ("Arabic. Use clear, simple Modern Standard Arabic in a warm, playful tone, with easy everyday words that a child in Egypt would understand. "
                "Do not use diacritics. Write science words in Arabic."
                if lang == "ar" else "English.")
    return (
        "You are Astro, the friendly AI Space Assistant inside an educational astronaut game. "
        f"You are talking to {who}. Reply ONLY in {language}\n"
        f"Style: {style}\n"
        "Make learning feel like a fun adventure, and keep every answer easy to understand. "
        "Rules: plain text only, no markdown, no lists, no asterisks, no emojis. "
        "Use ONLY the reference notes plus well-established science; if you are not sure, say so honestly. "
        "Never just hand over the solution to a repair puzzle: give hints, point to evidence the player can scan, and let them reason it out. "
        "If the question is not about space, science or the game, kindly steer back to the mission."
    )


_OFFLINE_LEAD = {
    ("young", "en"): "Great question! ", ("young", "ar"): "سؤال رائع! ",
    ("mid", "en"): "", ("mid", "ar"): "", ("teen", "en"): "", ("teen", "ar"): "",
}


class SpaceAssistant:
    def __init__(self, use_chroma: bool = True, docs: Optional[List[Dict]] = None, embedding_function=None):
        self.docs = list(docs if docs is not None else SEED_DOCS)
        self.backend = "keyword"
        self.index = KeywordIndex(self.docs)
        self._client = None
        self._model_used = None
        if use_chroma:
            try:
                self.index = ChromaIndex(self.docs, config.CHROMA_DIR, embedding_function)
                self.backend = "chroma"
            except Exception as e:  # missing package, offline model download, etc.
                log.warning("ChromaDB unavailable (%s); using keyword retrieval.", e)

    # ---- status
    @property
    def llm_enabled(self) -> bool:
        return config.LLM_PROVIDER == "gemini" and bool(config.LLM_API_KEY)

    @property
    def llm_label(self) -> str:
        return f"Gemini ({self._model_used or config.LLM_MODEL})" if self.llm_enabled else "offline"

    # ---- retrieval
    def retrieve(self, question, mission_id=None, age_group="mid", k=3, lang="en"):
        try:
            return self.index.query(question, mission_id, age_group, k, lang)
        except Exception as e:
            log.warning("Retrieval failed (%s); falling back to keyword.", e)
            return KeywordIndex(self.docs).query(question, mission_id, age_group, k, lang)

    # ---- answering
    def ask(self, question: str, mission_id: Optional[str] = None, age_group: str = "mid",
            evidence: Optional[List[str]] = None, lang: str = "en") -> str:
        text = ""
        for text in self.ask_stream(question, mission_id, age_group, evidence, lang):
            pass
        return text

    def ask_stream(self, question: str, mission_id: Optional[str] = None, age_group: str = "mid",
                   evidence: Optional[List[str]] = None, lang: str = "en") -> Iterator[str]:
        """Yield the answer as it grows (cumulative text). Falls back to offline notes on any LLM failure."""
        from . import i18n
        question = (question or "").strip()
        if not question:
            yield i18n.t("ask_empty", lang)
            return
        passages = self.retrieve(question, mission_id, age_group, lang=lang)
        got = False
        try:
            for partial in self._llm_stream(question, passages, age_group, evidence or [], lang):
                got = True
                yield partial
        except Exception as e:
            log.warning("LLM call failed (%s); using retrieved notes instead.", e)
        if got:
            return
        yield self._offline_answer(passages, age_group, lang)

    def _offline_answer(self, passages, age_group, lang) -> str:
        from . import i18n
        if not passages:
            return i18n.t("no_data", lang)
        n = 1 if age_group == "young" else 2
        lead = _OFFLINE_LEAD.get((age_group, lang), "")
        body = " ".join(p["text"] for p in passages[:n])
        return lead + (body if age_group == "young" else f"{i18n.t('from_notes', lang)} {body}")

    # ---- Gemini
    def _get_client(self):
        if self._client is None:
            from google import genai
            from google.genai import types
            self._client = genai.Client(
                api_key=config.LLM_API_KEY,
                http_options=types.HttpOptions(timeout=int(config.LLM_TIMEOUT_S * 1000)))
        return self._client

    def _candidate_models(self):
        seen, out = set(), []
        for m in ((self._model_used,) if self._model_used else ()) + (config.LLM_MODEL,) + config.LLM_FALLBACK_MODELS:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out

    def _llm_stream(self, question, passages, age_group, evidence, lang) -> Iterator[str]:
        if not self.llm_enabled:
            return
        from google.genai import types
        context = "\n".join(f"- {p['text']}" for p in passages) or "(no notes found)"
        ev = "\n".join(f"- {e}" for e in evidence[-6:]) or "(none yet)"
        prompt = f"Reference notes:\n{context}\n\nPlayer's evidence log:\n{ev}\n\nPlayer's question: {question}"
        client = self._get_client()
        last_err = None
        for model in self._candidate_models():
            for use_thinking_cfg in (True, False):
                acc, any_text = "", False
                try:
                    kwargs = dict(system_instruction=build_system_prompt(age_group, lang), temperature=0.8,
                                  max_output_tokens=700)
                    if use_thinking_cfg:
                        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
                    cfg = types.GenerateContentConfig(**kwargs)
                    for chunk in client.models.generate_content_stream(model=model, contents=prompt, config=cfg):
                        piece = getattr(chunk, "text", None) or ""
                        if piece:
                            acc += piece
                            any_text = True
                            yield sanitize(acc)
                    if any_text:
                        self._model_used = model
                        return
                    last_err = RuntimeError("empty response")
                except Exception as e:  # try without thinking config, then next model
                    last_err = e
                    if any_text:                      # already streaming text to the player: keep it
                        raise
        if last_err:
            raise last_err

