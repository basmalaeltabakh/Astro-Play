# 🚀 Astro Play

### Run a Moon or Mars outpost. Every choice costs something.

**NASA Space Apps Challenge 2026 · Challenge: Build a Junior Astronaut Mission Trainer**

Astro Play is an interactive 3D space game in **Arabic and English** for kids aged 7–12 (and anyone curious). Players
become astronauts, explore the Moon, Mars, an orbital lab and Europa, and make the kind of trade-offs real mission
planners face: *power or shielding? oxygen or one more experiment?*

> **NASA data → Mission → Player explores and analyzes → AI explains → Player decides → Sees the consequence**

---

## 💡 Why Astro Play

Space content for kids is often too abstract (posters and general facts) or too technical to hold a young learner's
attention. Either way, children see a mission's outcomes but never the **decisions** behind them. Astro Play puts those
decisions in the player's hands:

- There is **no cost-free choice**. Every option gives something up.
- Learning comes from **doing**: scan, sample, analyze, diagnose, repair, decide.
- Failing is part of learning, with a debrief that explains *why*, not a punishment.
- Everything is available **in Arabic and English**, with correct right-to-left layout.

## ✅ What works today
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

> **Status: in development for the hackathon (13–14 Nov 2026).** The items below are our plan, not shipped features.

A new mode where the player **runs a lunar or Martian outpost** over a series of sols:

- **Three core resources:** power, life support (oxygen and food) and radiation shielding, plus communication delay as
  an event. Few systems, so young players can follow them, but with real consequences.
- **Real trade-offs:** reinforce shielding before a solar event and lose tonight's power. Spend oxygen reserves on an
  extra research opportunity and live with the margin.
- **Real NASA data behind the risk:** radiation-event likelihood follows recent solar activity from **DONKI**, so a
  shielding decision connects to real space weather.
- **Real research as fact cards:** short findings from **OSDR** on astronaut health and biology.
- **Honest data:** every source is labeled in-game. Archived data is marked as archived and never presented as live.
- **Replayable:** events vary between playthroughs, so kids can try new strategies and learn from failure.
- **Same AI assistant:** explains terms like *radiation dose* and *sol* in plain language, in Arabic or English.

## 📡 NASA data and sources
| Source | Use in Astro Play |
|---|---|
| [DONKI](https://api.nasa.gov/) (Space Weather Database) | Solar activity that drives radiation risk in Outpost Command *(planned)* |
| [OSDR](https://osdr.nasa.gov/) (Open Science Data Repository) | Astronaut health and biology findings as fact cards *(planned)* |
| NASA Moon, Mars, Europa and ISS pages | Knowledge base for the AI assistant (listed in `data/knowledge_sources.txt`, loaded with `scripts/ingest_nasa.py`) |

The built-in offline notes are short educational summaries written in our own words about topics covered by NASA
resources. Always verify facts against the original NASA pages.

## 🛠️ Technologies
| Area | Technology |
|---|---|
| Language | Python 3.10+ |
| Game engine / 3D | [Ursina Engine](https://www.ursinaengine.org/) (built on Panda3D) |
| AI assistant | Google Gemini (`google-genai`) with retrieval-augmented generation |
| Knowledge base | NASA content indexed in ChromaDB (vector search), with built-in keyword search as fallback |
| Database | SQLite: profiles, progress, XP, stars, achievements |
| Arabic support | `arabic-reshaper` + `python-bidi`, bundled Cairo font |
| Art and audio | Procedurally generated with NumPy, SciPy and Pillow |
| Configuration | `python-dotenv` |
| Testing | pytest, plus an automated smoke test that plays the game in both languages |



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



## 👩‍🚀 Team
**Merhan Medhat** · **Basmala Saeed** · **Tahany Emad** · **Aml Ashraf** · **Rawan Hany** · **Alaa Elsayed**

## 📜 Notes
Astro Play is an independent project made for the NASA Space Apps Challenge. It uses publicly available NASA data and
educational content and is not endorsed by NASA. The Astro Play base prototype (3D worlds, UI, bilingual system and AI
assistant) was created before the event. Outpost Command and the DONKI/OSDR integration are being built during the
hackathon.
