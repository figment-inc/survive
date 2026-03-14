# You Wouldn't Wanna Be — Series Bible

## Premise

A hapless skeleton gets teleported into history's most horrific moments — plagues, sieges, volcanic eruptions, sinkings, collapses, and catastrophes of every kind. A calm, authoritative narrator — a seasoned British naturalist in the tradition of a National Geographic documentary — tells the story in second person ("you") while the skeleton stumbles through each scenario with wide-eyed physical comedy. Every episode ends terribly. The skeleton never survives. But the history is always real, always educational, and always precisely sourced.

## Visual Style

Classic American adult animation (Family Guy seasons 10-20 aesthetic):
- **Flat cel-shaded coloring** with ZERO gradients
- **Thick uniform black outlines** on ALL elements (characters, objects, backgrounds)
- **Simplified features**, clean vector rendering
- **No 3D rendering**, no photorealistic elements, no shading variation
- **Static locked camera** — no handheld, no shaky-cam, no drift
- **Flat 2D compositions** — painted layered backgrounds, minimal parallax

## Tone

- **Nature documentary meets apocalypse.** The narrator speaks like a British naturalist guiding you through the most extraordinary forces on Earth — geological, meteorological, human. The tone is reverent, unhurried, and intimately curious, as if studying a rare species in its final hours. The horror comes from the calm, measured delivery of devastating facts, not from snark or humor.
- **Immersive thriller, never lecture.** The viewer IS the skeleton — they make decisions, try to survive, and fail. The script reads like a first-person survival story narrated by a world-class National Geographic documentarian.
- **Agency and failure loops.** Every 10–15 seconds the character tries something and it fails. "You warn the officers. They have no reason to listen — no hurricane has ever struck Galveston." These micro-failures drive tension, retention, AND education.
- **Educational through lived experience with scientific depth.** Facts land because the viewer encounters them firsthand. Not "twenty thousand people lived here" but "you push through 37,000 people who live on a sandbar barely 8 feet above sea level." Every clip includes at least one specific, verifiable fact.
- **Measured gravitas, not dark comedy.** The narrator treats every disaster with the respect it deserves. Scientific precision. Genuine awe at scale. The tone of a National Geographic special — warm, wise, and unhurried — even as the world falls apart around you.
- **Second person address, present tense.** Always "you", "your" — and always present tense for immediacy. "You stand on the cobblestones of Galveston Island. The barometric pressure is dropping." Never past tense.

## Format

- Vertical 9:16 short-form video optimized for YouTube Shorts, TikTok, and Instagram Reels
- **45–50 seconds per episode** (target 48s video — narration MUST finish under 30 seconds)
- **60–72 words of narration** at ~2.3 words/second (measured ElevenLabs pacing) — punchy, dense, every word earns its place
- Classic American adult animation style (flat cel-shaded, thick outlines)
- The skeleton appears on camera but never speaks — narration is off-screen voiceover
- **Split audio pipeline**:
  - **Veo 3.1**: Generates SILENT video with environmental SFX + ambient sounds only
  - **ElevenLabs TTS**: Generates narrator voiceover (Dan — British Documentary Narrator, voice ID `BHr135B5EUBtaWheVj8S`)
  - **ElevenLabs Music**: Generates cinematic nature documentary underscore
  - **ffmpeg**: Mixes per clip: Veo audio 15% + narration 100% + music 20%
- Remotion-rendered karaoke captions (Whisper transcription + transparent overlay)
- **8 clips** (mix of 4s and 8s) — target visual change every 4–6 seconds
- Static locked camera throughout — flat 2D animated compositions
- Native Veo output durations only — NEVER crop or trim video

## Episode Structure (5 Narrative Beats)

Every episode follows this arc across 8 clips (~48s video, <30s narration):

1. **The Hook** (clip 01, 0–4s) — The figure is already in the scene, standing in the middle of the disaster about to unfold. Drop the viewer into danger on word one. NOT a question — a devastating fact that creates immediate dread. "You have eleven minutes before the pyroclastic surge reaches you. You cannot outrun it." Voice starts IMMEDIATELY on frame 1. No silent establishing shots. No setup.
2. **The Immersion** (clips 02–03, 4–16s) — Sensory arrival with one killer scientific detail per clip. Place the viewer in the scene FAST. Short, visceral sentences. "You stand on a sandbar eight feet above sea level. Thirty-seven thousand people live here. None of them have seen a hurricane."
3. **The Attempt** (clips 04–05, 16–28s) — The viewer tries to survive and FAILS. Each failure teaches one real fact. Try to warn people → learn why they don't listen. Try to run → discover the geography that traps you. Every clip raises the stakes. No plateaus.
4. **The Catastrophe** (clips 06–07, 28–40s) — Maximum intensity. Facts delivered with clinical precision at peak chaos — specific temperatures, wind speeds, structural failure points. The calm voice amid the destruction IS the horror. Staccato rhythm. Short punchy sentences.
5. **The Cliffhanger** (clip 08, 40–48s) — End with an unresolved, haunting fact that drives comments AND echoes the hook for structural satisfaction. "They found 6,000 bodies. They stopped counting." Never resolve cleanly. Leave the viewer wanting to comment, share, or rewatch.

Each beat spans 1–2 clips. The viewer drives the story through their (failed) choices while history happens around them.

## Narrator Voice

- Calm, measured, authoritative British naturalist — the voice of a National Geographic documentary narrator who has spent decades in the field
- Warm curiosity and genuine reverence for the forces involved — geological, meteorological, human
- Unhurried pacing, as if guiding the viewer through something extraordinary and fragile
- The horror comes from the steady, composed delivery of devastating facts — not from humor or theatrics
- Scientific precision: specific numbers, temperatures, distances, chemical reactions
- Addresses the viewer directly in second person present tense: "you wake up", "you feel the ground shift"
- Pacing: ~2.3 words per second (measured ElevenLabs output), **60–72 words per episode** (HARD CEILING — narration must finish under 30 seconds)
- **Sentence structure**: Short, punchy sentences. Average 5-10 words. Staccato rhythm for catastrophe beats, slightly more flowing for immersion.
- **Sensory specificity**: Visceral, concrete details. Not "the fire is hot" but "eighteen hundred degrees — hot enough to melt your fillings."
- Generated via **ElevenLabs TTS** (Dan — British Documentary Narrator, voice ID `BHr135B5EUBtaWheVj8S`)
- Voice settings: stability 0.85, similarity_boost 0.75, style 0.15
- Mixed with Veo video in post-production at 100% volume

## Naming Rules (for Veo prompts)

- NEVER use the word "skeleton" in Veo prompts if it triggers safety filters
- NEVER reference copyrighted show names (Family Guy, Simpsons, South Park) in prompts
- In prompts: refer to the character as **the figure** or **the translucent character**
- Use "classic American adult animation style" for style enforcement
- The character NEVER speaks, NEVER moves their mouth in Veo prompts. All prompts must include: "The on-screen character does NOT speak and does NOT move their mouth. Mouth remains closed. Silent physical reactions only."
- Video prompts generate SILENT video — no narrator lines, no dialogue direction, no music
- The reference image handles visual identity — detailed descriptions reinforce it

## Script Writing Rules

- **Nature documentary tone.** Calm, measured, authoritative. Warm British naturalist guiding you through the extraordinary. Genuine awe. Scientific precision.
- **Present tense ONLY.** "You wake up" not "You've arrived." Immediacy is everything.
- **Short punchy sentences.** Average 5–10 words. Staccato rhythm for catastrophe beats, slightly more flowing for immersion. "The ground shifts. Limestone cracks beneath your feet."
- **Educational depth.** Every clip includes at least one specific, verifiable fact.
- **Sensory specificity.** Visceral, concrete details. Not "Vesuvius is erupting" but "four hundred fifty miles per hour. Superheated gas at a thousand degrees."
- **Agency verbs.** The viewer acts: "You run", "You grab", "You shout." Not passive observation.
- **Tension ratchet.** Every clip raises the stakes from the previous one. No plateaus. No breathing room.
- **One moment of genuine scientific awe per episode.** A fact so extraordinary it creates wonder.
- **Callback endings.** The cliffhanger should echo or invert the hook for structural satisfaction.
- **Open-loop endings.** End with an unresolved fact that drives comments: "The real number may never be known."
- **60–72 words total. HARD CEILING.** The entire narration must finish under 30 seconds of spoken audio.

## TikTok / YouTube Shorts Optimization

- **Voice on frame 1.** The dramatic hook statement plays over the very first visual. ZERO seconds of silence.
- **Hook = devastating fact**, NEVER a question. Drop the viewer into danger on word one.
- Target **45–50 seconds** total video (8 clips), narration under 30 seconds
- **Visual change every 4–6 seconds** — fast cuts, angle changes, new information in every shot
- **Every clip raises the stakes** — the tension ratchet is the retention engine
- Narrator fills EVERY clip — no silent clips, no dead air
- **Callback ending** — the cliffhanger echoes the hook for structural satisfaction
- End with an **open-loop** — an unresolved fact that drives comments and shares
