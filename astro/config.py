"""Central configuration and paths."""
import os
import shutil
import sys
from pathlib import Path

# Packaged build (PyInstaller): read-only game files live in the bundle, while saves, settings and caches go to a
# per-user folder, because the folder the game was unzipped into may not be writable.
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    APP_DIR = Path(sys.executable).resolve().parent
    if os.name == "nt":
        USER_DIR = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "AstroPlay"
    else:
        USER_DIR = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "astro-play"
else:
    ROOT = Path(__file__).resolve().parent.parent
    APP_DIR = ROOT
    USER_DIR = ROOT / "data"

try:  # optional dependency
    from dotenv import load_dotenv
    if FROZEN:  # a .env next to the game (or in the user folder) can add a Gemini key
        for _env in (APP_DIR / ".env", USER_DIR / ".env"):
            if _env.is_file():
                load_dotenv(_env)
    else:
        load_dotenv()
except Exception:  # pragma: no cover
    pass

ASSETS_DIR = ROOT / "assets"
DATA_DIR = ROOT / "data"
if FROZEN:
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        if not (USER_DIR / "settings.json").exists() and (DATA_DIR / "settings.json").exists():
            shutil.copyfile(DATA_DIR / "settings.json", USER_DIR / "settings.json")   # first run: default settings
    except OSError:  # pragma: no cover - the game still runs, it just cannot save
        pass
DB_PATH = Path(os.getenv("ASTRO_DB_PATH", USER_DIR / "astro_play.db"))
CHROMA_DIR = Path(os.getenv("ASTRO_CHROMA_DIR", USER_DIR / "chroma"))
SETTINGS_PATH = Path(os.getenv("ASTRO_SETTINGS_PATH", USER_DIR / "settings.json"))
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
DONKI_CACHE_PATH = Path(os.getenv("ASTRO_DONKI_CACHE", USER_DIR / "donki_cache.json"))
DONKI_ARCHIVE_PATH = Path(os.getenv("ASTRO_DONKI_ARCHIVE", DATA_DIR / "donki_archive.json"))

# ---- NASA OSDR (Open Science Data Repository). Official OSDR Biological Data API v2: https://visualization.osdr.nasa.gov/biodata/api/
# It needs no API key. Cached metadata is git-ignored; the curated offline dataset ships with the game.
OSDR_BASE_URL = os.getenv("ASTRO_OSDR_URL", "https://visualization.osdr.nasa.gov/biodata/api").rstrip("/")
OSDR_CACHE_PATH = Path(os.getenv("ASTRO_OSDR_CACHE", USER_DIR / "osdr_cache.json"))
OSDR_STUDIES_PATH = Path(os.getenv("ASTRO_OSDR_STUDIES", DATA_DIR / "osdr_studies.json"))

LOGO_NAMES = ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp")


def find_logo():
    """Return the path of the official logo if supplied, else None."""
    for name in LOGO_NAMES:
        p = ASSETS_DIR / name
        if p.exists():
            return p
    return None
