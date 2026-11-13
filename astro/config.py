"""Central configuration and paths."""
import os
from pathlib import Path

try:  # optional dependency
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.getenv("ASTRO_DB_PATH", DATA_DIR / "astro_play.db"))
CHROMA_DIR = Path(os.getenv("ASTRO_CHROMA_DIR", DATA_DIR / "chroma"))
SETTINGS_PATH = Path(os.getenv("ASTRO_SETTINGS_PATH", DATA_DIR / "settings.json"))
KNOWLEDGE_DIR = DATA_DIR / "knowledge"

# ---- LLM (Gemini). Set GEMINI_API_KEY in .env.  Provider "none" = fully offline answers.
LLM_PROVIDER = os.getenv("ASTRO_LLM_PROVIDER", "gemini").lower()          # gemini | none
LLM_MODEL = os.getenv("ASTRO_LLM_MODEL", "gemini-flash-latest")
# tried in order if the model above is unavailable for your key/region
LLM_FALLBACK_MODELS = tuple(m.strip() for m in os.getenv("ASTRO_LLM_FALLBACKS", "gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m.strip())
LLM_API_KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
if LLM_API_KEY.lower() in ("your-key-here", "your-gemini-key", "changeme"):   # untouched template value
    LLM_API_KEY = ""
LLM_TIMEOUT_S = float(os.getenv("ASTRO_LLM_TIMEOUT", "25"))

# Experimental real-time sun shadows (ASTRO_SHADOWS=1). Off by default: it crashed under software OpenGL, so the
# worlds use soft contact-shadow decals instead, which work everywhere.
SHADOWS = os.getenv("ASTRO_SHADOWS", "0") == "1"

# ---- NASA DONKI space weather. Official API (CCMC, version 2.0): https://ccmc.gsfc.nasa.gov/DONKI/api/ . It needs NO API key,
# so none is read or sent. (The older https://api.nasa.gov/DONKI gateway is no longer used.)
DONKI_BASE_URL = os.getenv("ASTRO_DONKI_URL", "https://ccmc.gsfc.nasa.gov/DONKI-API/get").rstrip("/")
DONKI_CACHE_PATH = Path(os.getenv("ASTRO_DONKI_CACHE", DATA_DIR / "donki_cache.json"))
DONKI_ARCHIVE_PATH = Path(os.getenv("ASTRO_DONKI_ARCHIVE", DATA_DIR / "donki_archive.json"))

# ---- NASA OSDR (Open Science Data Repository). Official OSDR Biological Data API v2: https://visualization.osdr.nasa.gov/biodata/api/
# It needs no API key. Cached metadata is git-ignored; the curated offline dataset ships with the game.
OSDR_BASE_URL = os.getenv("ASTRO_OSDR_URL", "https://visualization.osdr.nasa.gov/biodata/api").rstrip("/")
OSDR_CACHE_PATH = Path(os.getenv("ASTRO_OSDR_CACHE", DATA_DIR / "osdr_cache.json"))
OSDR_STUDIES_PATH = Path(os.getenv("ASTRO_OSDR_STUDIES", DATA_DIR / "osdr_studies.json"))

LOGO_NAMES = ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp")


def find_logo():
    """Return the path of the official logo if supplied, else None."""
    for name in LOGO_NAMES:
        p = ASSETS_DIR / name
        if p.exists():
            return p
    return None
