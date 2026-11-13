# Run Astro Play – Outpost Command on Windows (beginner guide)

All commands are for **Windows PowerShell** and were checked against this repository. Run every command from the project
root folder (`D:\Astro-play`) unless it says otherwise.

> **Do not clone from GitHub yet.** Outpost Command exists only in the local folder `D:\Astro-play` (its files are not
> committed). A fresh `git clone` would give you the old game without Outpost Command. Use the existing folder.

## 1. Required software
| Software | Needed? | Notes |
|---|---|---|
| **Python 3.13 (64-bit)** | Yes | The project's `.venv` uses 3.13.5 (verified). The README says 3.10+, but only 3.13 was verified. |
| A graphics-capable PC | Yes | The game opens a real 3D window; a display and OpenGL are required. |
| Git | No | Only for cloning or checking status. |
| Internet | No | Only for the one-time `pip install`. The game runs offline. |

If you have several Pythons installed, call the version explicitly with `py -3.13`. **Do not use Python 3.14**: Panda3D
1.10.16 (the 3D engine) has no build for it.

## 2. Open the project
```powershell
cd D:\Astro-play
```
Or open the folder in VS Code and use Terminal → New Terminal (it starts in the project root).

## 3. Virtual environment (PowerShell)
`D:\Astro-play\.venv` already exists with everything installed. Activate it:
```powershell
.\.venv\Scripts\Activate.ps1
```
You should see `(.venv)` at the start of the prompt. To create a fresh one instead:
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```
If PowerShell says *"running scripts is disabled on this system"*, run this once, then activate again:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## 4. Install dependencies
The only requirements file is `requirements.txt` in the project root:
```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
It installs `ursina` (which brings Panda3D), `python-dotenv`, `arabic-reshaper`, `python-bidi`, `google-genai`, `pytest`,
`fonttools`, `requests` and `chromadb`. With the existing `.venv` it should report everything as already satisfied. A fresh
`chromadb` install is large and can take a few minutes.

## 5. Configuration
**Nothing is required.** The game starts with no `.env` file at all.

| Setting | Required? | What it does |
|---|---|---|
| `.env` file | No | Already present, git-ignored, loaded automatically if it exists. |
| `GEMINI_API_KEY` | Optional | Turns on live Gemini answers in the AI Space Assistant (3D missions only). Without it the assistant answers from built-in notes. |
| `NASA_API_KEY` | **Not used** | The line in `.env.example` is never read. DONKI and OSDR need no key. Do not add one. |
| `ASTRO_DB_PATH`, `ASTRO_DONKI_URL`, `ASTRO_OSDR_URL`, `ASTRO_DONKI_CACHE`, `ASTRO_OSDR_CACHE` | Optional | Only to move files or point at other servers. |

Outpost Command itself needs none of these.

**Files that must exist before launch** (all included in the repo): `assets\fonts\`, `assets\audio\`, `assets\sky\`,
`assets\ui\`, `assets\logo.png`, `data\donki_archive.json`, `data\osdr_studies.json`. The game creates
`data\astro_play.db` and `data\chroma\` by itself on first run.

## 6. Launch the game
With the venv active, from the project root:
```powershell
python main.py
```
This is the easiest method and the only one you need. If the first start is slow, or you are offline, this variant skips
the vector database and plays the same:
```powershell
python main.py --no-chroma
```
A 1280×720 window titled **Astro Play** opens. The logo splash leaves by itself after about 3 seconds (or press any key).

## 7. Main menu and Outpost Command
Main menu buttons (right side): **New Game**, **Continue**, **Outpost Command** (gold), **Quit**. Top-right icons: language
(العربية / EN), sound, music.

1. Click **Outpost Command**. You do not need a player profile (Continue stays grey until a profile exists).
2. On the setup screen choose **Moon** or **Mars**, and **Easy / Normal / Hard**.
3. Click **Start mission**.
4. Use **+ / −** to share power between Life Support, Shielding, Communications and Science, then click **Advance to next
   sol** (or press Enter). **Reset** (or R) clears the plan.
5. **Research cards** shows the NASA study cards. **Main Menu** (or Esc) leaves; a run in progress is saved and shows up as
   **Resume** next time.

## 8. Fully offline
Turn off Wi-Fi, or launch with no connection.

**Works with no internet:**
- All of Outpost Command: Moon and Mars, three difficulties, events, save/resume, results, Arabic.
- Solar activity from the bundled DONKI snapshot (labeled *Archived*, dated 2026-11-09).
- All 13 research cards from the bundled OSDR studies (labeled *Offline*).
- The 3D missions, quiz, profiles, progress and music.
- The AI assistant, answering from its built-in notes.

On the setup screen you will see "Could not reach NASA. Using saved data." This is expected, not an error.

**Needs internet:** `pip install`, the **Refresh NASA data** button (live data), live Gemini answers, and the first-time
download of the vector-search model used by `chromadb` (if it fails, the game falls back to keyword search by itself).

## 9. Common problems
| Symptom | Fix |
|---|---|
| `...Activate.ps1 cannot be loaded... disabled` | Run the `Set-ExecutionPolicy` command from step 3. |
| `python` not recognized, or wrong version | Use `py -3.13 ...`. After activating, `python --version` should say 3.13.x. |
| `No matching distribution found for panda3d` | You are on Python 3.14 (or 32-bit). Recreate the venv with `py -3.13 -m venv .venv`. |
| `ModuleNotFoundError: ursina` (or any package) | The venv is not active or dependencies are not installed. Redo steps 3 and 4. |
| First launch pauses or freezes for a while | `chromadb` is setting up its model. Wait, or run `python main.py --no-chroma`. |
| Window is black or crashes on start | Update your graphics driver. Do not set `ASTRO_SHADOWS=1` (experimental, off by default). |
| Arabic letters look disconnected | `arabic-reshaper` / `python-bidi` are missing. Re-run step 4. |
| "Could not reach NASA. Using saved data." | Normal when offline. The game continues with saved data. |
| `pip` fails on `chromadb` | It is optional. Run `python -m pip install ursina python-dotenv arabic-reshaper python-bidi google-genai pytest fonttools requests`, then launch with `python main.py --no-chroma`. |
| Tests fail with a "real HTTP blocked" message | That is the test guard working: tests must not use the internet. Report it if you see it. |

## 10. Run the tests
Run from the project root with the venv active.

**Fast tests (no game window, about 30 seconds, 583 tests):**
```powershell
python -m pytest --ignore=tests/test_outpost_ui.py -q
```
A narrower Outpost-only set (537 tests, about 28 seconds):
```powershell
python -m pytest tests/test_outpost.py tests/test_outpost_events.py tests/test_outpost_balance.py tests/test_outpost_flow.py tests/test_outpost_safety.py tests/test_nasa_data.py tests/test_osdr_data.py tests/test_netguard.py tests/test_core.py -q
```

**Full suite (684 tests, about 35 minutes):**
```powershell
python -m pytest
```
The slow part is `tests\test_outpost_ui.py`, which opens a real game window many times. Leave the PC alone while it runs and
do not minimize the window.

**Optional automatic play-through** (opens the window, plays Outpost Command in English and Arabic, offline):
```powershell
python scripts/smoke_outpost.py
```

## Checklist: is it running correctly?
- [ ] `python --version` shows 3.13.x and the prompt starts with `(.venv)`.
- [ ] `python main.py` opens a window titled **Astro Play** with the logo, then the main menu.
- [ ] The menu shows **New Game, Continue, Outpost Command, Quit**.
- [ ] **Outpost Command** opens the setup screen with a **NASA data** panel on the right.
- [ ] The panel shows solar activity (calm / active / stormy) labeled *Archived* or *Live*, and "13 research cards".
- [ ] **Start mission** opens the play screen; **+ / −** change the numbers and **Advance to next sol** goes from "Sol 1 of 10" to "Sol 2".
- [ ] **Research cards** shows a NASA study with a separate "How the game uses this idea" box.
- [ ] The **العربية** button switches to Arabic with a mirrored layout; **EN** switches back.
- [ ] The same steps still work with the internet off.
- [ ] `python -m pytest --ignore=tests/test_outpost_ui.py -q` ends with `583 passed`.
