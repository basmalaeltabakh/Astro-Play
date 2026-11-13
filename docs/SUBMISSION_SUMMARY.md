# Astro Play – Outpost Command: submission summary

**NASA Space Apps Challenge 2026 · Challenge: Build a Junior Astronaut Mission Trainer**
Team: Merhan Medhat · Basmala Saeed · Tahany Emad · Aml Ashraf · Rawan Hany · Alaa Elsayed

## The problem
Space content for children is either too abstract (posters, lists of facts) or too technical. Kids see what happened on a
mission but almost never the **decisions** behind it, so they learn *that* astronauts are careful, not *why*. Content is
also rarely available in Arabic with a properly mirrored layout, and rarely connected to real, current NASA data.

## The solution
**Astro Play** is a 3D space game in **Arabic and English** for ages 7–12. Its new mode, **Outpost Command**, puts the
player in charge of a lunar or Martian outpost for 8–12 sols (Martian days). Each sol the player splits limited power
between **Life Support, Radiation Shielding, Communications and Science**, and then lives with what happens.

- **Three resources** the child can follow: Power, Life Support (oxygen and food), Radiation Shielding.
- **No free choices:** shielding costs science, the radio costs score, oxygen focus costs food.
- **Forecasts you pay for:** the radio shows the *type* of the next event, or the exact event with enough power.
- **Ten events** (storms, equipment faults, dust, blight, radio blackout, and helpful windows, caches and discoveries),
  paced fairly: quiet first sols, no long hazard streaks, gaps between severe storms.
- **Failure that teaches:** every lost mission ends with a plain explanation of what happened.
- **Saved and replayable:** saved after every sol, resumable, different events each run, three difficulties and two sites.

## How NASA data is used
| NASA source | What the game does with it |
|---|---|
| **DONKI** (space weather) | Counts recent solar flares, CMEs, geomagnetic storms and particle events and maps them to one 0–1 *solar activity* level (calm/active/stormy). This only changes how likely **solar storms** are. |
| **OSDR** (space biology) | Shows 13 real study titles and descriptions as **research cards** (plants, radiation, microgravity, health, microbes), each linking to the NASA study page. |

Rules we hold ourselves to:
- **Honest labels:** every source is shown as *Live*, *Cached*, *Archived* (with its date) or built-in default. Saved data
  is never shown as live, and defaults are never called NASA data.
- **Facts apart from game:** NASA's text is shown unchanged; our gameplay note sits in a separate, labeled box and never
  contains findings or safety numbers.
- **Not measurements:** the solar level is a *game mapping*, not a radiation measurement or forecast. The game says so.
- **No keys, no secrets, no restricted data:** both official APIs need no key; only study-level metadata is used.
- **Works offline:** it ships a real DONKI snapshot (fetched 2026-11-09) and the 13 OSDR studies. See `DATA_SOURCES.md`.

## Educational value
- Learning by deciding: trade-offs, planning under uncertainty, reading a forecast, and cause and effect (the result screen
  explains *why*).
- Real science context: what solar storms are and why shielding matters; what NASA studies about growing food, radiation,
  health and microbes in space, with a link to the real study.
- Language access: complete English and Arabic, with right-to-left layout and correct letter joining.
- Age-appropriate difficulty: the starting difficulty follows the player's skill; Easy is forgiving, Hard rewards planning.
- A separate **AI Space Assistant** (retrieval over NASA-based notes with Google Gemini, built-in offline answers) supports
  the 3D missions. It is *not* part of Outpost Command.

## Technical architecture
```
Ursina/Panda3D UI  ──  astro/game/outpost_ui.py   (setup, play, result, research cards; EN/AR)
        │
 OutpostSession  ──  astro/outpost_flow.py        (new / resume / advance / save; background loader)
   │        │
   │        └── NasaData ── nasa_data.py (DONKI) · osdr_data.py (OSDR)   requests, cache, bundled snapshot
   │
 outpost.py (pure simulation: step_sol, seeded events, immutable state)   outpost_config.py (every balance number)
        │
 SQLite  ──  astro/db.py  outpost_runs table (status enforced by triggers)
```
- **Simulation is pure Python**: no UI, no network, deterministic from a seed, so runs are reproducible, resumable and
  testable at scale.
- **NASA access never blocks the game:** background threads, results applied on the main thread, time budgets, atomic
  cache writes, and a fallback chain (live → cached → archived → default).
- **Balance in one file:** `astro/outpost_config.py`; changes are measured by simulation (`tests/test_outpost_balance.py`).
- **Tests:** 684 automated tests: the simulation, balance, NASA data (network mocked, real HTTP blocked suite-wide), saving,
  loader safety, and real-window UI tests (layout, clickability, English and Arabic). Smoke tests play the whole mode.

## Limitations (honest list)
- The game needs a desktop with graphics; there is no browser or phone version yet.
- DONKI offline data is a fixed 30-day snapshot (2026-10-10 to 2026-11-09); offline play does not follow current weather.
- Only 13 OSDR studies are bundled; study titles and descriptions stay in NASA's English even in the Arabic interface.
- Balance numbers are game-design choices from simulation, not from NASA, and have not been playtested with children.
- There is no screen for reviewing past runs; resuming restores only the latest unfinished run.
- Resuming a run needs the event settings in `outpost_config.py` to be unchanged since it was saved.
- The full test suite takes about 35 minutes because the UI tests open a real game window.
- One earlier unexplained drawing error (`KeyError: 'start'`) was never reproduced; the screens now report such errors
  visibly instead of hiding them.

## Where to look
`README.md` (install, controls, difficulties, offline mode, tests) · `DATA_SOURCES.md` (NASA sources and limits) ·
`docs/DEMO_SCRIPT.md` (4-minute demo) · `astro/outpost_config.py` (balance) · `Astro_Play_Proposal.pdf` (original proposal).
