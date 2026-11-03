🚀 Astro Play

Become an Astronaut. Explore Space. Make Every Decision Count.

An Adaptive 3D Space Exploration & Mission Training Game

NASA Space Apps Challenge 2026
Challenge: Build a Junior Astronaut Mission Trainer

---

🌌 About Astro Play

What if children could do more than learn about space? What if they could actually experience it?

Astro Play is an interactive 3D space exploration and mission training game designed for children and teenagers aged 8–17.

Players step into the role of astronauts, explore the Moon and Mars, complete scientific missions, solve unexpected problems, and make critical decisions that directly affect their missions.

But Astro Play is more than a space adventure. It transforms real space science into hands-on learning experiences, where every decision has consequences and every challenge is an opportunity to learn.

The experience adapts to each player's age and abilities, adjusting mission complexity, scientific explanations, hints, and difficulty to create an engaging and age-appropriate journey.

Our goal is simple: turn the dream of becoming an astronaut into an interactive learning experience.
💡 The Problem We're Solving

Space education often presents children with facts, images, and scientific information without allowing them to experience how space missions actually work.

Young learners may discover what astronauts do, but rarely get the opportunity to understand:

- How astronauts survive in extreme environments.
- Why managing oxygen, energy, and food is critical.
- How scientists investigate unknown environments.
- How a single decision can affect an entire mission.
- How real NASA data contributes to space exploration.

Astro Play bridges this gap by turning abstract scientific concepts into interactive missions where players explore, experiment, analyze, and make decisions.

🎯 Our Target Audience

Children and teenagers aged 8–17, with an adaptive experience designed around three developmental levels:

Age Group| Learning Experience
8–11 years| Simple scientific explanations, guided exploration, visual interactions, and introductory challenges.
12–14 years| Deeper scientific concepts, problem-solving missions, and analytical challenges.
15–17 years| Advanced mission simulations, strategic decisions, resource management, and more complex scientific scenarios.

The game also considers player performance and progress, gradually adjusting difficulty as players develop their skills.
🎮 How Astro Play Works

The player's journey follows an interactive mission cycle:

Explore → Scan → Collect → Analyze → Decide → Experience the Consequences → Learn

1. Choose Your Mission: Enter the space exploration journey and select an available destination.
2. Explore the Environment: Navigate immersive 3D worlds on the Moon or Mars.
3. Investigate: Scan locations, collect samples, and interact with scientific equipment.
4. Analyze: Examine collected data and identify environmental conditions or system failures.
5. Make Decisions: Choose how to solve problems using limited resources.
6. See the Consequences: Experience how decisions affect the mission and its survival conditions.
7. Learn and Improve: Receive feedback, explanations, and mission assessments.
🪐 Main Game Features

1. Immersive 3D Space Exploration

Explore realistic-inspired space environments through interactive 3D worlds.

- Moon and Mars exploration.
- Interactive space environments and scientific equipment.
- Astronaut movement and mission activities.
- Habitat exploration and resource stations.
- Additional destinations such as orbital laboratories and Europa.

2. Adaptive Learning Experience

Astro Play is designed to grow with its players.

The game adapts its:

- Scientific explanations and vocabulary.
- Mission difficulty and complexity.
- Hints and guidance.
- Challenges and problem-solving activities.
- Learning assessments.

A younger player might receive a simple explanation of oxygen consumption, while an older player could face a more complex mission involving life-support calculations and resource allocation.

3. AI Space Assistant (RAG)

An intelligent space companion that helps players understand the science behind their missions.

Powered by Google Gemini and Retrieval-Augmented Generation (RAG), the assistant uses a knowledge base built from NASA educational and scientific resources.

It can:

- Explain space concepts in age-appropriate language.
- Answer questions about the Moon, Mars, astronauts, and space exploration.
- Explain scientific terms encountered during missions.
- Provide hints instead of directly revealing solutions.
- Support both Arabic and English.
- Acknowledge when information is unavailable in its knowledge base.
4. Outpost Command: Every Decision Has a Cost

A strategic mission management mode where players operate a lunar or Martian outpost over several space days (Sols).

Players must manage three essential resource categories:

- Power: Keeps the outpost systems and equipment running.
- Life Support: Maintains oxygen and food supplies.
- Radiation Shielding: Protects astronauts from dangerous radiation.

Communication delays and unexpected space-weather events introduce additional challenges.

Example mission decisions:

- Reinforce radiation shielding before a solar event, sacrificing some available power.
- Use oxygen reserves for an additional scientific experiment, reducing the outpost's safety margin.
- Prioritize communication systems or preserve energy for life-support equipment.

There is no universally perfect choice. Every decision involves a trade-off, and players must understand its consequences.

5. Real NASA Data Integration

Astro Play connects educational gameplay with real space science.

NASA Source| Role in Astro Play
DONKI – Space Weather Database| Solar activity and space-weather events inform radiation-related mission risks.
OSDR – Open Science Data Repository| Scientific findings about astronaut health and human biology become educational fact cards.
NASA Moon Resources| Support lunar exploration knowledge and mission content.
NASA Mars Resources| Provide scientific information about the Martian environment.
NASA Europa Resources| Support future exploration content.
NASA ISS Resources| Provide information about astronauts and life in space.

Data sources are identified within the game. Archived information is clearly labeled and never presented as live data.

6. Habitat & Survival Systems

Players interact with a space habitat containing:

- Airlock.
- Science analyzer.
- Sleeping quarters.
- Tool locker.
- Oxygen station.

Survival mechanics introduce practical challenges:

- Oxygen decreases while exploring outside the habitat.
- Tool batteries drain with use.
- Batteries can be recharged at the tool locker.
- Players must plan their activities and manage available resources.
 7. Learning, Debrief & Rewards

After completing a mission, players receive a debrief that includes:

- Mission performance.
- Decisions and their consequences.
- Scientific concepts learned.
- Explanations of mistakes and failed attempts.
- Short quizzes and bonus XP.
- Progress tracking across missions.

Failure is not simply losing. It is an opportunity to understand what happened and make better decisions next time.

8. Arabic & English Support

Astro Play supports Arabic and English to make space education accessible to a wider audience.

Arabic support includes:

- Correct Arabic letter shaping and joining.
- Right-to-left (RTL) interface layout.
- Language-appropriate explanations and interactions.

9. Offline Knowledge Support

When internet access or an external AI API is unavailable, the assistant can rely on built-in educational notes to provide basic explanations and maintain access to essential learning content.
🛰️ Core Gameplay: Outpost Command

Run a Moon or Mars outpost. Every choice costs something.

Outpost Command puts players in the position of mission planners.

Each Sol, players must decide how to allocate limited resources while responding to changing environmental conditions.

For example:

A solar event is approaching. The outpost needs stronger radiation protection, but reinforcing the shielding consumes power.

The player must decide:

- Protect the crew and sacrifice energy.
- Preserve energy and accept greater radiation exposure.
- Adjust other operations to balance the available resources.

Real NASA space-weather information from DONKI informs the radiation-risk system, while scientific findings from OSDR provide educational context.

Mission events can vary between playthroughs, encouraging players to experiment with different strategies and understand the consequences of their choices.
🛠️ Technology Stack

Component| Technology
Programming Language| Python 3.10+
3D Game Engine| Ursina Engine
3D Rendering Foundation| Panda3D
AI Model| Google Gemini
AI Architecture| Retrieval-Augmented Generation (RAG)
Vector Database| ChromaDB
Local Database| SQLite
NASA Data Integration| DONKI APIs and OSDR resources
Arabic Language Processing| arabic-reshaper, python-bidi
Configuration| python-dotenv
Testing| pytest

🏗️ Project Architecture

Astro Play combines interactive gameplay, scientific information, and AI-powered learning.

                 ASTRO PLAY
                      |
          +-----------+-----------+
          |                       |
      3D Game Engine          AI Assistant
          |                       |
    Mission System           Google Gemini
          |                       |
    Survival Mechanics       RAG Pipeline
          |                       |
    Resource Management      ChromaDB
          |                       |
          +-----------+-----------+
                      |
              NASA Knowledge Base
                      |
          +-----------+-----------+
          |                       |
        DONKI                    OSDR
     Space Weather          Scientific Research

     📚 Learning Outcomes

Through Astro Play, players develop:

- Basic knowledge of astronomy and planetary science.
- Understanding of astronaut life and space missions.
- Scientific observation and investigation skills.
- Critical thinking and decision-making.
- Problem-solving and resource management.
- Awareness of real NASA research and space exploration.
- Confidence in learning through experimentation.

👩‍🚀 Our Team

- Merhan Medhat
- Basmala Saeed
- Tahany Emad
- Aml Ashraf
- Rawan Hany
- Alaa Elsayed

🚀 Our Vision

We believe every child who dreams of becoming an astronaut deserves the opportunity to experience the excitement, challenges, and discoveries of space exploration.

Astro Play transforms that dream into an interactive journey where children don't just read about astronauts — they explore, investigate, experiment, and make decisions like real mission planners.

Because the future of space exploration starts with curiosity, imagination, and the courage to make the next decision.


\
