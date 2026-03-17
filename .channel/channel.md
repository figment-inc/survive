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
- **Global style reference** — `.channel/reference_images/style_reference.png` is passed as the first visual input to every image and video generation call, grounding all outputs in the canonical art style. Character angle references are separate and additive.

## Tone

- **Story first, encyclopedia never.** Each episode is a 45-second STORY, not a lecture. The viewer should FEEL something — dread, hope, then devastation. Facts are the skeleton; feeling is the flesh. A script that teaches five facts but creates no emotion has failed.
- **Nature documentary meets apocalypse.** The narrator speaks like a British naturalist guiding you through the most extraordinary forces on Earth — geological, meteorological, human. The tone is reverent, unhurried, and intimately curious. The horror comes from the calm, measured delivery of devastating facts, not from snark or humor.
- **Immersive thriller, never lecture.** The viewer IS the skeleton — they make decisions, try to survive, and fail. The script reads like a first-person survival story narrated by a world-class National Geographic documentarian.
- **Agency and failure loops.** Every 10-15 seconds the character tries something and it fails. Each attempt has HOPE behind it — the viewer tries because they believe it will work. The fact that kills the hope IS the teaching moment.
- **Teach through feeling, not exposition.** Facts land because the viewer encounters them in their body. Not "the tank holds two million gallons" (textbook) but "the tank above your street holds two million gallons — and it has been groaning all winter" (story). The viewer learns the same fact but FEELS the dread.
- **Measured gravitas, not dark comedy.** The narrator treats every disaster with the respect it deserves. Scientific precision. Genuine awe at scale. The tone of a National Geographic special — warm, wise, and unhurried — even as the world falls apart around you.
- **Suspense through contrast.** Real NatGeo documentaries build dread by showing safety BEFORE destruction. A moment of calm — children playing, birds singing, the ground still — makes the catastrophe devastating by contrast. A script that starts at maximum danger has nowhere to go. The calm before the storm IS the suspense. Include a false safety moment in the Immersion, a tiny domestic detail the viewer can picture, a tension checkpoint ("the nightmare hadn't begun"), and at least one comparison anchor that makes a number visceral ("faster than a galloping horse").
- **Second person address, present tense.** Always "you", "your" — and always present tense for immediacy. "You" must be the SUBJECT of sentences in EVERY clip including catastrophe and conclusion. The disaster happens TO you, not around you.

## Format

- Vertical 9:16 short-form video optimized for YouTube Shorts, TikTok, and Instagram Reels
- **~48 seconds per episode** (target 48s video)
- **95–105 words of narration** at ~2.4 words/second (measured ElevenLabs pacing) as **continuous prose** — narration flows across clip boundaries as one unbroken audio stream, overlaid on the final stitched video in post-production
- Classic American adult animation style (flat cel-shaded, thick outlines)
- The skeleton appears on camera but never speaks — narration is off-screen voiceover
- **Split audio pipeline**:
  - **Veo 3.1**: Generates SILENT video with environmental SFX + ambient sounds only
  - **ElevenLabs TTS**: Generates narrator voiceover as ONE continuous audio file (Dan — British Documentary Narrator, voice ID `BHr135B5EUBtaWheVj8S`)
  - **ElevenLabs Music**: Generates cinematic nature documentary underscore
  - **Whisper**: Word-level timestamps on the continuous narration for visual sync reference
  - **ffmpeg**: Overlays full narration + music onto final stitched video in a single pass
- Remotion-rendered karaoke captions (Whisper transcription + transparent overlay)
- **8 clips** (mix of 4s and 8s) — target visual change every 4–6 seconds
- Static locked camera throughout — flat 2D animated compositions
- Native Veo output durations only — NEVER crop or trim video

## Episode Structure (5-Beat Narrative Arc)

Every episode follows this arc across 8 clips (~48s video, narration as continuous prose ~95-105 words):

1. **The Hook + Framing Line** (clip 01, 0–4s) — Two parts in clip 01. Voice starts IMMEDIATELY on frame 1. No silent establishing shots. No questions. **Part A**: The narrator delivers a single, calmly stated impossibility — a paradox, an absurdity, or a cruel irony that makes the viewer think "wait, what?" The sentence must be self-contained: a viewer who hears ONLY Part A must need to keep watching. **Part B**: Immediately after the hook, the narrator says "You would not want to be in the [Event Name], [Year]." This framing line is MANDATORY — it tells the viewer what this video is about (narrated only, not rendered as on-screen text). Goal: curiosity gap + instant event identification.
2. **The Immersion** (clips 02–03, 4–16s) — The framing line already told the viewer WHAT and WHEN. Clip 02 goes straight into danger — the physical reality that makes this disaster terrifying. Build the world with visceral sensory detail — what you see, smell, hear, feel. Clip 03 tightens the trap with a specific scientific or historical detail. Flowing sentences, unhurried pacing.
3. **The Attempt** (clips 04–05, 16–28s) — The viewer tries to survive and FAILS. Agency verbs: "You run", "You warn", "You push toward the door." Each failure teaches one real fact. This is the educational heart: accessible, flowing, never a lecture. Sentences carry momentum across clip boundaries.
4. **The Catastrophe** (clips 06–07, 28–40s) — The disaster hits with clinical precision — specific temperatures, wind speeds, structural failure points. **RHYTHM SHIFT**: staccato punches, sentences averaging 5 words (max 8). Each sentence must CAUSE or REVEAL the next — not disconnected factoids but a causal chain of destruction. The calm voice amid the destruction IS the horror.
5. **The Conclusion** (clip 08, 40–48s) — End with a definitive, closing statement that lands like a verdict and echoes the hook for structural satisfaction. The callback is mandatory. "The mountain did not need fire. It only needed gravity." Goal: leave the viewer STUNNED by the completeness of the destruction.

Each beat spans 1–3 clips. The narration is one continuous audio stream — sentences flow freely across clip boundaries. Visual cuts happen mid-narration, pulling the viewer forward.

## Narrator Voice

- Calm, measured, authoritative British naturalist — the voice of a National Geographic documentary narrator who has spent decades in the field
- Warm curiosity and genuine reverence for the forces involved — geological, meteorological, human
- Unhurried pacing, as if guiding the viewer through something extraordinary and fragile
- The horror comes from the steady, composed delivery of devastating facts — not from humor or theatrics
- Scientific precision: specific numbers, temperatures, distances, chemical reactions
- Addresses the viewer directly in second person present tense: "you wake up", "you feel the ground shift"
- Pacing: ~2.4 words per second (measured ElevenLabs output), **95–105 words per episode** as continuous prose
- Narration is generated as ONE continuous audio file and overlaid on the final stitched video in post-production
- **Sentence structure**: Varies by beat — flowing and immersive for Immersion/Attempt, staccato punches for Catastrophe/Cliffhanger. Sentences freely cross clip boundaries.
- **Sensory texture**: What does the disaster FEEL like to the viewer's body? Not just numbers but sensation — heat on skin, dust in lungs, the floor shaking. "Eighteen hundred degrees" is a number. "The heat blisters your hands before the flames reach you" is a story.
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

- **Story first.** You are writing a 45-second story, not a 45-second lecture. If a sentence could appear unchanged on Wikipedia, rewrite it with "you" as the subject or add sensory texture.
- **Nature documentary tone.** Calm, measured, authoritative. Warm British naturalist guiding you through the extraordinary. Genuine awe. Scientific precision.
- **Continuous prose.** Write one flowing narrative, not isolated per-clip scripts. Sentences flow across clip boundaries.
- **Present tense ONLY.** "You wake up" not "You've arrived." Immediacy is everything.
- **Rhythm varies by beat.** Immersion + Attempt: longer, flowing sentences that build the world. Catastrophe: staccato punches averaging 5 words (max 8), each sentence causing or revealing the next. The rhythm shift IS the pacing.
- **Causal narrative thread.** Every sentence connects to the one before it — causation, not just sequence. If a sentence could be deleted without the next sentence losing meaning, it's a factoid, not a story beat.
- **Sensory texture.** At least two sentences must describe what the disaster FEELS like to the viewer's body — heat on skin, dust in lungs, the floor shaking, something cracking above you. These moments separate a story from a report.
- **You in the catastrophe.** "You" must be the SUBJECT of at least one sentence in clips 06, 07, and 08. The disaster happens TO you, not around you while you watch statistics.
- **Facts through feeling.** Every beat includes at least one specific, verifiable fact — but delivered through the viewer's experience, not as exposition.
- **Sensory continuity.** If clip 03 establishes smoke, clip 04 still has smoke. The environment accumulates.
- **Agency verbs.** The viewer acts: "You run", "You grab", "You shout." Not passive observation.
- **Tension ratchet.** Every clip raises the stakes from the previous one. No plateaus. No breathing room.
- **Callback endings.** The twist/payoff should echo or invert the hook for structural satisfaction.
- **Definitive ending.** End with a verdict that lands on YOU, not a statistic. Leave the viewer stunned.
- **95-105 words total.** Continuous prose, overlaid on the final stitched video.

## TikTok / YouTube Shorts Optimization

- **Voice on frame 1.** The dramatic hook statement plays over the very first visual. ZERO seconds of silence.
- **Hook + framing line.** Hook = devastating fact (NEVER a question), immediately followed by "You would not want to be in the [Event], [Year]." The framing line tells the cold viewer what this video is about (narrated only, not rendered as on-screen text).
- Target **~48 seconds** total video (8 clips), narration 95-105 words as continuous prose
- **5-beat formula**: Hook + Framing (0-4s) grabs attention + identifies the event, Immersion (4-16s) builds the world, Attempt (16-28s) teaches through failure, Catastrophe (28-40s) delivers clinical devastation, Conclusion (40-48s) leaves the viewer stunned
- **Visual change every 4–6 seconds** — fast cuts, angle changes, new information in every shot
- **Every clip raises the stakes** — the tension ratchet is the retention engine
- Narrator fills EVERY clip — no silent clips, no dead air
- **Callback ending** — the twist/payoff echoes the hook for structural satisfaction
- End with an **open-loop** — an unresolved fact that drives comments and shares
