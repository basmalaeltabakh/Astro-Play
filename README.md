#  Astro Play

### Don't just read about space. Be the astronaut who solves its problems.

Astro Play is an interactive 3D space-exploration game in **Arabic and English**, built for kids and teens in the Arab
world. Every level is a real problem inspired by NASA missions, and the player has to explore, analyze, decide and
live with the result of their decision.

> **NASA data → Mission → Player explores and analyzes → AI explains → Player decides → Sees the consequence**

---

## 💡 The idea

Most educational space games are quizzes: read a fact, pick an answer, move on. Astro Play flips this. There is no
"correct button" waiting at the end. The player is dropped into a situation, for example **a power outage at a lunar
base**, and has to work out what is wrong using the tools and data an astronaut would actually have.

The goal is to teach **scientific thinking, data analysis and problem solving** through a fun experience, in a language
young people in the Arab world feel at home in.

## 🎮 How a mission plays

1. **Sign in and choose your age.** The whole game adapts to it.
2. **Customize your astronaut** (suit colour) and open the **galaxy map**.
3. **Pick a world and a mission**: the Moon, Mars, an Orbital Lab or Jupiter's moon Europa.
4. **Mission briefing:** understand the problem and the objectives.
5. **Explore the surface in first person** with mission-specific tools:
   - **Scanner:** find and diagnose the broken system
   - **Sample Collector:** take a sample of the ground
   - **Spectrometer:** study what it is made of
   - **Repair Kit:** apply the fix
6. **Analyze** the sample at the habitat's science analyzer and read the evidence in the **evidence log**.
7. **Decide.** The repair stage asks real reasoning questions. Choosing the fix that works *in that environment* is the
   whole challenge, and a wrong choice has consequences.
8. **Debrief.** A summary of what you learned plus a short quiz for bonus XP, stars and achievements.

Then it's on to the next night, and the next world. Mars looks, sounds and behaves nothing like the Moon.

## 🤖 The AI Space Assistant (RAG)

Stuck on a term, a number or a graph? Press **Q** and ask.

- Answers are **grounded in NASA educational sources** through **retrieval-augmented generation** (ChromaDB vector
  search + Google Gemini), not made up.
- It has **clear limits**: if a question is outside its knowledge base, it says so instead of inventing an answer.
- It **nudges instead of spoiling.** It explains the science without handing over the mission's solution.
- It works fully in **Arabic and English**, streams answers as they are written, and falls back to built-in notes if
  there is no internet.
- No API key? The game and the assistant still work offline.

## 🎚️ A game that grows with the player

| Age group | What changes |
|---|---|
| **6-9** | Short, playful explanations, simple wording, easier questions, more visual guidance |
| **10-13** | Fuller explanations, real terminology, more reasoning in the repair questions |
| **14+** | Precise scientific detail, harder decisions, deeper analysis |

Difficulty also adapts to how the player performs (Easy / Normal / Hard), and it changes how fast oxygen drains.

## 🧑‍🚀 Feels like being there

- **Survival:** oxygen drains outside the habitat, with warnings and alarms at 30% and 15%. Tool batteries run down
  with use and are recharged at the tool locker.
- **A real habitat on every map:** airlock, science analyzer, bunk (rest + checkpoint), tool locker and an outdoor
  oxygen station.
- **First-person astronaut:** suited arms, the tool in your hand, and a wristwatch that shows your oxygen.
- **Living worlds:** craters, boulders, dust, footprints, dunes on Mars, ice shards on Europa, and skies with a real
  Earth, Jupiter and Sun.
- **Sound that reacts to you:** footsteps that change by surface (dust, gravel, ice, metal), breathing that speeds up
  as oxygen drops, doors, tools and alarms, plus original music.
- **Proper Arabic:** correctly joined, right-to-left, with the whole layout mirrored, and Arabic typing for names and
  questions.

## 🌍 Why it matters

- Arabic-language space education that treats kids as **problem solvers**, not quiz takers.
- Builds habits that matter beyond space: **read the evidence, test an idea, weigh a decision, learn from the result.**
- Made to be understood by a 7-year-old and still be worth playing at 17.
- Built around **NASA's real science and missions**, which makes the discoveries feel like theirs.

## 🛠️ Technologies

| Area | Technology |
|---|---|
| Language | Python 3.10+ |
| Game engine / 3D | [Ursina Engine](https://www.ursinaengine.org/) (built on Panda3D) |
| AI assistant | Google Gemini (`google-genai`) |
| RAG / knowledge base | NASA educational pages indexed in ChromaDB (vector search), with built-in keyword search as fallback |
| Database | SQLite: profiles, progress, XP, stars, achievements |
| Arabic support | `arabic-reshaper` + `python-bidi`, bundled Cairo font |
| Art and audio | Procedurally generated with NumPy, SciPy and Pillow |
| Configuration | `python-dotenv` |
| Testing | pytest, plus an automated smoke test that plays the game in both languages |



### Controls
| Key | Action |
|---|---|
| WASD / mouse | Move / look |
| 1-4 or scroll | Select tool |
| E or left click | Use the tool or station you are looking at |
| H | Hint |
| Q | Ask the AI Space Assistant |
| Tab | Evidence log |
| M | Music on/off |
| Esc | Close panel / leave mission |



## 👩‍🚀 Team
Made by the **Astro Play** team.

*Astro Play is an independent project. NASA sources are used for educational purposes, and the project is not
endorsed by NASA.*
