# Data sources

Astro Play's **Outpost Command** mode uses two official NASA services. This file says exactly what is used, where it comes
from, what is bundled with the game, and what the data does *not* mean.

> Astro Play is an independent project made for the NASA Space Apps Challenge. It uses publicly available NASA data and is
> **not endorsed by NASA**.

## At a glance

| | DONKI | OSDR |
|---|---|---|
| Full name | Space Weather Database Of Notifications, Knowledge, Information | Open Science Data Repository |
| Run by | NASA Community Coordinated Modeling Center (CCMC) | NASA Open Science Data Repository |
| Used for | How likely solar storms are in a mission | Research fact cards |
| Official docs | https://ccmc.gsfc.nasa.gov/DONKI/api/ | https://www.nasa.gov/osdr-api/ and https://visualization.osdr.nasa.gov/biodata/api/ |
| Base URL | `https://ccmc.gsfc.nasa.gov/DONKI-API/get` | `https://visualization.osdr.nasa.gov/biodata/api` |
| API key | **None** (the official spec declares no authentication) | **None** |
| Bundled copy | `data/donki_archive.json` | `data/osdr_studies.json` |
| Runtime cache (created on first success, git-ignored) | `data/donki_cache.json` | `data/osdr_cache.json` |
| Code | `astro/nasa_data.py` | `astro/osdr_data.py` |

No credentials are read, sent or stored for either service (a test checks that even a set `NASA_API_KEY` never appears in a
request or an error message). Requests identify themselves only as `AstroPlay/1.0 (educational game)`. The `NASA_API_KEY`
line in `.env.example` is not used by the game.

## DONKI (space weather)

**Endpoints used** (all `GET`, with `startDate` and `endDate` as `yyyy-MM-dd`, a 30-day window ending today):

| Endpoint | Event type |
|---|---|
| `/get/FLR` | Solar flares |
| `/get/CME` | Coronal mass ejections |
| `/get/GST` | Geomagnetic storms |
| `/get/SEP` | Solar energetic particle events |

**How it becomes gameplay.** The game counts recent events and turns them into **one number from 0 to 1** ("solar
activity"). That number only changes one thing: how likely a *solar storm* event is in the mission. It is shown as
*Calm / Active / Stormy*. The point values (for example an X-class flare counts more than a C-class flare) and the cut-offs
are **game-design choices** in `astro/outpost_config.py` (`DONKI`), calibrated against 24 real 30-day DONKI windows between
2024-11-20 and 2026-11-09 so that stormy periods are noticeably but not unfairly harder.

**It is not a NASA measurement.** The 0–1 number is *not* a scientific index, *not* a radiation measurement and *not* a
space-weather forecast. The game says so on screen.

**Where the data comes from, in order** (the screen always shows which one was used):

1. **Live**: fetched from NASA just now.
2. **Cached**: an earlier live result saved on this computer. Opening Outpost Command reuses it if it is under **1 hour** old; the **Refresh NASA data** button always asks NASA first.
3. **Archived**: the bundled snapshot `data/donki_archive.json` (dates shown in the game).
4. **Default**: no NASA data at all; a neutral value is used and the game does not call it NASA data.

**The bundled snapshot** was fetched from the official API on **2026-11-09** for **2026-10-10 to 2026-11-09**. It holds the
real events NASA returned (14 flares, 87 CMEs, 2 geomagnetic storms, 0 particle events) with only the fields the game
uses (IDs, class, times, Kp values), copied unchanged, plus the dates, retrieval time and provenance. The counts are
re-derived from the stored events by a check, so they cannot silently drift. Archived data is **never** shown as live.

## OSDR (space biology research cards)

**Endpoints used** (OSDR Biological Data API v2.0.0):

| Endpoint | Purpose |
|---|---|
| `GET /v2/datasets/` | List of study accessions |
| `GET /v2/dataset/{accession}/` | Study-level **metadata** (title, description, organism, mission, platform, release date) |
| `GET /v2/query/datasets/?format=json.records&...` | Filtered search (organism, spaceflight, radiation) |

Only study descriptions are used. **No data files, samples or restricted data are requested, stored or redistributed**, and
studies that are not yet publicly released are rejected.

**What a research card shows.** NASA's own study **title and description** (copied unchanged, in English), the study
number (for example `OSD-655`), a *Spaceflight* or *Ground-based* label taken from the study's own metadata, and a link to
the study on `https://osdr.nasa.gov/bio/repo/data/studies/<accession>`. Below that is a separate, clearly labeled
**"How the game uses this idea (educational)"** note written by the Astro Play team. NASA's facts and our gameplay notes are kept
visibly apart, and the notes never contain findings or safety numbers. Card titles are not translated: in Arabic the
interface and our notes are Arabic, while NASA's title and description stay in NASA's English.

**The bundled studies.** `data/osdr_studies.json` holds 13 studies chosen by the team across five topics, retrieved from the
official API on 2026-11-09:

| Topic | Studies |
|---|---|
| Plants | OSD-655, OSD-745, OSD-670 |
| Radiation | OSD-46, OSD-431, OSD-202 |
| Microgravity | OSD-48, OSD-310 |
| Health | OSD-174, OSD-569 |
| Microbes | OSD-65, OSD-26, OSD-267 |

In the file, everything under `verified` comes from NASA's API and everything under `app` is written by us.
Ground-based studies (for example OSD-670, OSD-46, OSD-202) are labeled as ground-based and never presented as spaceflight.

**Where the data comes from:** *Live* (just fetched), *Cached* (saved from a live fetch, reused when Outpost Command opens if under 1 day old; the Refresh button always asks NASA first), or *Offline*
(the bundled studies). A set is only called live if **every** card is live. The game loads up to 60 studies per refresh,
10 at a time.

## What the dates on screen mean

The setup screen keeps three different moments apart:

| On screen | Meaning |
|---|---|
| **Retrieved: 2026-11-13 18:28** | When the game got this data from NASA, in **your computer's local time**. Saved and archived data keeps its *original* retrieval time, so it never looks newer than it is. |
| **Newest NASA event: 2026-10-03 (UTC)** | The date of the newest solar event in the data, exactly as NASA reported it. It is never replaced by today's date. NASA lists events when they happen, so this can be days old; if NASA listed none, the screen says so. |
| **Last checked: 2026-11-13 18:30** | When the game last *asked* NASA, even if the answer failed. A failed check shows "Could not update NASA data. Using saved data." together with the last successful retrieval time. |

Retrieval times are stored with their UTC offset, so they stay correct if the computer's timezone or clock changes. The
bundled snapshot has no offset (it was saved on this machine) and is read as local time.

## How the game uses the network

- On entering Outpost Command, the game **starts from the bundled/cached data immediately** and asks NASA for fresher data
  **in the background**. The screen never waits for NASA, and results are applied on the main thread only.
- Each request has a time limit and the whole attempt has a total budget (25 s for DONKI, 40 s for OSDR). A dead service costs
  at most one timeout, never freezes the game, and shows a short message ("Could not reach NASA. Using saved data.").
- Files are written atomically (temporary file, then replace), so a crash cannot leave a half-written cache; a damaged cache
  is ignored and rebuilt.
- The simulation itself (`astro/outpost.py`) never imports the NASA modules and never touches the network. NASA data
  enters only as the single 0–1 solar-activity number, fixed when a run starts, so a saved run always resumes the same way.

## Refreshing the bundled data

Both scripts need internet access and refuse to overwrite an existing file without `--force`. If NASA cannot be reached,
nothing is written, and records are never invented.

```bash
python scripts/fetch_donki_archive.py [--force]    # rewrites data/donki_archive.json from live DONKI
python scripts/build_osdr_dataset.py  [--force]    # rewrites data/osdr_studies.json from live OSDR
```

## Limitations

- DONKI counts are an input to a **game**, not a forecast. They say nothing about real radiation doses at a real outpost.
- The bundled DONKI snapshot is a 30-day window as of 2026-11-09. Without internet the game keeps using it (and labels it
  *Archived*), so offline solar activity does not follow current space weather.
- OSDR cards show study **descriptions**, not results or measurements, and only 13 studies are bundled. NASA's text is in
  English only, and descriptions are shortened at a sentence end near 600 characters.
- The research cards are educational summaries of what a study is about, not scientific advice. Always check the original
  study page at https://osdr.nasa.gov.
- A live refresh depends on NASA's services being available and on their response format staying the same; the game
  falls back to saved data if a response is unusable.
- The AI Space Assistant's knowledge base (`data/knowledge_sources.txt`) is separate from Outpost Command and is not
  described here. Outpost Command does not use the assistant.

## Attribution

Space-weather event data: **NASA Community Coordinated Modeling Center (CCMC), DONKI** — https://ccmc.gsfc.nasa.gov/DONKI/.
Space biology study metadata: **NASA Open Science Data Repository (OSDR)** — https://osdr.nasa.gov/.
Each research card links to its study page. NASA data and names are used for education; this project is not endorsed by NASA.
Please check NASA's own terms of use before reusing the data outside this project.
