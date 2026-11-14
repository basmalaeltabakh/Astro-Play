# 🚀 Astro Play

### Run a Moon or Mars outpost. Every choice costs something.

**NASA Space Apps Challenge 2026 · Challenge: Build a Junior Astronaut Mission Trainer**

Astro Play is an interactive 3D space game in **Arabic and English** for kids aged 7–12 (and anyone curious). Players
become astronauts, explore the Moon, Mars, an orbital lab and Europa, and make the kind of trade-offs real mission
planners face: *power or shielding? oxygen or one more experiment?*

> **NASA data → Mission → Player explores and analyzes → AI explains → Player decides → Sees the consequence**
>
> 1. Project Repository (GitHub)
https://github.com/basmalaeltabakh/Astro-Play
2. Download Astro Play – Windows
https://github.com/basmalaeltabakh/Astro-Play/releases/download/v1.0.1/AstroPlay-Windows.zip
3. Download Astro Play – Linux
https://github.com/basmalaeltabakh/Astro-Play/releases/download/v1.0.1/AstroPlay-Linux.tar.gz
4. Gameplay Demo Video
https://youtu.be/nbIOqtVWuHo?si=5rqzpFbI7Uvsee0o

---

## 💡 Why Astro Play

Space content for kids is often too abstract (posters and general facts) or too technical to hold a young learner's
attention. Either way, children see a mission's outcomes but never the **decisions** behind them. Astro Play puts those
decisions in the player's hands:

- There is **no cost-free choice**. Every option gives something up.
- Learning comes from **doing**: scan, sample, analyze, diagnose, repair, decide.
- Failing is part of learning, with a debrief that explains *why*, not a punishment.
- Everything is available **in Arabic and English**, with correct right-to-left layout.

## ✅ Core features
| Feature | Details |
|---|---|
| **4 explorable 3D worlds** | Moon → Mars → Orbital Lab → Europa, each with its own terrain, sky, sounds and challenges |
| **Mission loop** | Scan the site → collect a sample → analyze it → diagnose the broken system → choose the repair that works in that environment |
| **Survival constraints** | Oxygen drains outside the habitat (alarms at 30% and 15%); tool batteries drain with use and recharge at the locker |
| **Habitat on every map** | Airlock, science analyzer, bunk (rest + checkpoint), tool locker, oxygen station |
| **AI Space Assistant (RAG)** | Answers from NASA-based sources (ChromaDB + Google Gemini), stays within its knowledge, says so when it can't answer, and nudges instead of giving the solution |
| **Adaptive to the player** | Wording, questions, hints and difficulty adjust to age group and performance |
| **Debrief and quiz** | After each mission: what you learned, plus a quiz for bonus XP, stars and achievements |
| **Fully bilingual** | Arabic and English with proper letter joining, RTL layout and Arabic typing |
| **Works offline** | Without internet or an API key, the assistant answers from built-in notes |

## 🛰️ Built for this challenge: Outpost Command

A mode where the player **runs a lunar or Martian outpost** over a series of sols (Martian days). Open it from the main
menu: **Outpost Command**.

- **Three core resources:** **Power**, **Life Support** (with oxygen and food shown separately) and **Radiation
  Shielding**. Each sol the player splits the available power between Life Support, Shielding, **Communications** and
  **Science**. Communications and Science are things you spend power *on*, not extra resources. Crew health and score are
  shown as status indicators, not resources.
- **Real trade-offs:** reinforce shielding before a solar storm and have less power for science. Keep the radio on to get
  a forecast (and to use supply windows) and give up score for it. Put science first and risk the crew on Hard.
- **Forecasts:** with enough power on Communications you see the *category* of the next event (3 units) or the exact
  event (5 units). With no forecast the player has to plan for the unknown.
- **Events:** ten varied events (solar storm, micrometeorite, dust storm, dust build-up, equipment fault, crop blight,
  radio blackout, plus helpful ones: comms window, supply cache, science discovery). Events are fair by design: quiet
  opening sols, no long hazard streaks, and a gap between severe storms.
- **Real NASA data behind the risk:** how likely solar storms are follows recent space weather from **DONKI**, so a
  shielding decision connects to real events. The number is a *game mapping* of recent event counts, **not** a NASA
  measurement or forecast.
- **Real research as fact cards:** 13 **OSDR** study cards (plants, radiation, microgravity, health, microbes) with NASA's
  own title and description, kept apart from a short, clearly labeled gameplay note written by our team.
- **Honest data:** every NASA source is labeled in-game as *Live*, *Cached*, *Archived* (with its date) or built-in
  default. Saved data is never presented as live.
- **Replayable and saved:** a run is saved after every sol, so you can leave and **resume** exactly where you stopped.
  Events differ between runs (each run has a seed, shown on the result screen). Finish with a result screen (stars, score,
  and a plain explanation of why a mission failed), then **Play again**.
- **Bilingual:** the whole mode works in English and Arabic (mirrored layout).

### Locations and difficulties
| | Sols | Events | Notes |
|---|---|---|---|
| **Easy** | 8 | fewer and gentler, quiet opening sols | forgiving first mission |
| **Normal** | 10 | more frequent, harder-hitting | the default for most players |
| **Hard** | 12 | most frequent, starts with little power | the radio and careful planning matter |

The starting difficulty follows the player's skill level (Easy, Normal or Hard) and can be changed on the setup screen.
**Moon**: more solar power and few dust storms, but more micrometeorites. **Mars**: less power and more dust storms, so it
is the harder place to run an outpost. All balance numbers live in `astro/outpost_config.py` and are game-design choices,
not NASA figures.

### Outpost Command controls
Mostly mouse: click the buttons on screen (**+ / −** to move power, **Advance to next sol**, **Reset**, **Research cards**).

| Key | Action |
|---|---|
| Enter / Space | Advance to the next sol |
| R | Reset this sol's power plan |
| Shift + click on + / − | Change power by 5 instead of 1 |
| ← / → (or A / D) | Previous / next research card |
| Esc | Back (to setup, or out of Outpost Command; a run in progress stays saved) |

The AI Space Assistant (Q) belongs to the 3D missions. It is not part of Outpost Command.

## 📡 NASA data and sources
| Source | Use in Astro Play |
|---|---|
| [DONKI](https://ccmc.gsfc.nasa.gov/DONKI/) (Space Weather Database) | Counts of recent solar flares, CMEs, geomagnetic storms and particle events set how likely solar storms are in Outpost Command |
| [OSDR](https://osdr.nasa.gov/) (Open Science Data Repository) | Study titles and descriptions for the research cards in Outpost Command |
| NASA Moon, Mars, Europa and ISS pages | Knowledge base for the AI assistant (listed in `data/knowledge_sources.txt`, loaded with `scripts/ingest_nasa.py`) |

Both DONKI and OSDR are official NASA APIs that need **no API key**. The game works fully **offline**: it ships with a
saved DONKI snapshot and 13 curated OSDR studies, and says clearly when it is showing saved data. See
**[DATA_SOURCES.md](DATA_SOURCES.md)** for endpoints, attribution, limits and how the bundled data works.

The built-in offline notes are short educational summaries written in our own words about topics covered by NASA
resources. Always verify facts against the original NASA pages.

## 🛠️ Technologies
| Area | Technology |
|---|---|
| Language | Python 3.10+ |
| Game engine / 3D | [Ursina Engine](https://www.ursinaengine.org/) (built on Panda3D) |
| AI assistant | Google Gemini (`google-genai`) with retrieval-augmented generation |
| Knowledge base | NASA content indexed in ChromaDB (vector search), with built-in keyword search as fallback |
| NASA data | `requests` against the official DONKI and OSDR APIs, loaded in background threads, with local cache, bundled snapshot and offline fallback |
| Database | SQLite: profiles, progress, XP, stars, achievements, Outpost Command runs (saved/resumable) |
| Arabic support | `arabic-reshaper` + `python-bidi`, bundled Cairo font |
| Art and audio | Procedurally generated with NumPy, SciPy and Pillow |
| Configuration | `python-dotenv` |
| Testing | pytest (simulation, balance, NASA data with mocked network, real-window UI tests), plus smoke tests that play the game in both languages |

## ▶️ Run it
```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
python main.py
```
Add a free [Gemini API key](https://aistudio.google.com/apikey) as `GEMINI_API_KEY` in `.env` to turn on the live AI
assistant. Without it, the assistant answers from its built-in notes. Currently a desktop game; a browser version is a
possible next step.

**Requirements:** Python 3.10 or newer (developed and tested on Python 3.13 on Windows) and a computer with a display and
OpenGL graphics. The first start needs no internet. The NASA data for Outpost Command needs **no API key**; the
`NASA_API_KEY` line in `.env.example` is not used by the game.

### Offline mode
Everything works with no internet:
- **Outpost Command** starts from saved data right away (a bundled DONKI snapshot and 13 bundled OSDR studies). In the
  background it asks NASA for newer data; if that fails, the screen says so and the saved data is used and labeled
  *Archived / Offline*, never *Live*.
- **The AI assistant** answers from its built-in notes (set no `GEMINI_API_KEY`, or lose the connection).

Optional settings (environment variables, all have defaults): `ASTRO_DONKI_URL`, `ASTRO_OSDR_URL`, `ASTRO_DONKI_CACHE`,
`ASTRO_OSDR_CACHE`, `ASTRO_DB_PATH`.

### Run the tests
```bash
python -m pytest                       # everything (~35 minutes: the UI tests open a real game window)
python -m pytest tests/test_outpost.py tests/test_outpost_events.py tests/test_outpost_balance.py \
    tests/test_outpost_flow.py tests/test_outpost_safety.py tests/test_nasa_data.py tests/test_osdr_data.py \
    tests/test_netguard.py tests/test_core.py                    # fast, no window (under a minute)
python scripts/smoke_outpost.py        # plays Outpost Command in the real game, English and Arabic, offline
python scripts/smoke_outpost.py --live # same, using the real NASA services
```
The test suite never touches the real internet unless you opt in (`ASTRO_LIVE_TESTS=1` with the `live_network` marker).

### Controls
| Key | Action |
|---|---|
| WASD / mouse | Move / look |
| 1-4 or scroll | Select tool (Scanner, Sample Collector, Spectrometer, Repair Kit) |
| E or left click | Use the tool or the station you are looking at |
| H | Hint |
| Q | Ask the AI Space Assistant |
| Tab | Evidence log |
| M | Music on/off |
| Esc | Close panel / leave mission |

## 📁 Project structure
```
main.py            entry point
astro/             missions, assistant (RAG), knowledge, quiz, database, i18n, audio
astro/outpost.py         Outpost Command simulation (pure Python, no UI, no network)
astro/outpost_config.py  every Outpost balance number in one place
astro/outpost_flow.py    sessions, saving/resuming, background loading of NASA data
astro/nasa_data.py       DONKI client, cache and bundled snapshot
astro/osdr_data.py       OSDR client, cache, bundled studies and research cards
astro/game/        screens, HUD, UI widgets, 3D worlds, habitat
astro/game/outpost_ui.py Outpost Command screens (setup, play, result, research cards)
assets/            fonts, audio, sky and UI art
scripts/           asset generators, NASA ingestion (ingest_nasa.py), smoke tests,
                   fetch_donki_archive.py / build_osdr_dataset.py (refresh the bundled NASA data)
tests/             pytest suite (tests/netguard.py blocks real HTTP in tests)
data/              knowledge sources, settings, donki_archive.json, osdr_studies.json
DATA_SOURCES.md    NASA sources, endpoints, attribution and limits
docs/              demo script and submission summary
```

## 👩‍🚀 Team
**Merhan Medhat** · **Basmala Saeed** · **Tahany Emad** · **Aml Ashraf** · **Rawan Hany** · **Alaa Elsayed**

## 📜 Notes
Astro Play is an independent project made for the NASA Space Apps Challenge. It uses publicly available NASA data and
educational content and is not endorsed by NASA.
