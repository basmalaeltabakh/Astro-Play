# Demo script: Outpost Command (about 4 minutes)

**Goal of the demo:** show that a child can run an outpost, see a real-NASA-driven risk, feel a trade-off, learn from a
research card, and understand why a mission ended.

**Before you start**
- Run `python main.py` once and create or pick a player. A display and graphics are needed; internet is *not*.
- The demo works with the network off. If you are online, you will see the data labels change from *Archived* to *Live*;
  mention that this is the game being honest about its sources.
- Events are random (every run has its own seed), so the exact storm turn differs each time. The tips below show how to
  steer toward the moments you want.
- Practise the full run once. A run on Normal takes about 2 minutes of play.

---

## 0:00 – Hook (20 s)
*Say:* "Space is full of decisions, not just facts. In Astro Play you run a Moon or Mars outpost, and every choice costs
something: power for shielding or power for science?"
*Show:* the main menu, then click **Outpost Command**.

## 0:20 – Setup and real NASA data (50 s)
*Show:* the setup screen.
- Pick **Mars** and **Normal** (mention Easy is gentler and Hard is harder; the default follows the player's skill).
- Point at the **NASA data** panel on the right:
  "This is real space weather from NASA's DONKI service. The game counts recent solar flares and eruptions and turns them
  into a *calm / active / stormy* level. Here it says *Archived*, with the date, because the game never calls saved data live."
- Point at the yellow note: "It's a game mapping, not a NASA radiation measurement."
- Mention the **Refresh NASA data** button and that the game works fully offline.
- Click **Start mission**.

## 1:10 – Play: the trade-off (60 s)
*Show:* the play screen (Resources on the left, Power allocation in the middle, Mission control forecast on the right).
- "Three things keep the outpost alive: **Power, Life Support** (oxygen and food) and **Radiation Shielding**. Each sol I
  split my power between Life Support, Shielding, Communications and Science."
- Move power with the **+ / −** buttons. Point at *If nothing unexpected happens*: "The game predicts tomorrow's numbers
  *before* I commit."
- Put **5 on Communications**: "The radio gives me a forecast. With enough power I even see the exact event coming."
- Click **Advance to next sol**. Repeat for two or three sols, pointing out *Last sol* and *Active effects*.

## 2:00 – A NASA-driven event (50 s)
*Tip:* Solar storms are the most likely hazard from sol 2 on, and likelier when the data says *active* or *stormy*. Keep the
radio at 5 and keep advancing until the forecast shows **Solar storm**.
- *Before the storm:* "Mission control warns me: charged particles are heading for the outpost, severity high. This is
  exactly where real space weather connects to my choice." Move power into **Radiation Shielding** (for example 10+).
- Advance. *Show* the *Last sol* panel: "The shield absorbed it. Without shielding, this would have hurt the crew."
- If the run is short on time, click **Reset** to show how quickly a plan can be changed.

## 2:50 – Research cards (40 s)
*Show:* click **Research cards**.
- "These are real NASA OSDR studies about plants, radiation, microgravity, health and microbes."
- Point at the card: NASA's own title and description at the top; below it, a separate box, "How the game uses this idea
  (educational)", written by us. "We never mix NASA's facts with our game rules."
- Click a topic filter (for example *Radiation*), then **Next**, and show **Open NASA study page**.
- Optional: click the language button to show the whole screen mirrored in **Arabic**.

## 3:30 – Result and replay (30 s)
*Show:* leave the cards (**Back**) and finish the mission (or show a saved example).
- On the **result screen**: stars, score, sols survived, and, if lost, a plain explanation under **What happened**. "Failing is part of learning here."
- Mention **Play again**, and that a run is **saved every sol**: leave, come back, and **Resume**.

## 3:55 – Close (10 s)
*Say:* "Real NASA data behind the risk, real research on the cards, honest labels, in English and Arabic, and it still
works with no internet."

---

## Backup plans
- **No storm appears:** switch to Mars (more dust storms) or Hard, or say "events vary every run" and show the dust-storm
  warning instead; the same forecast and *Active effects* panels apply.
- **Graphics trouble:** run `python scripts/smoke_outpost.py` to play the whole flow automatically in English and Arabic.
- **Mission ends early:** that is part of the story. Show the result screen and click **Play again**.
- **Nobody asks about the AI assistant:** it belongs to the 3D missions (press **Q** there). Outpost Command does not use it.
