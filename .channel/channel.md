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

- **Story first, encyclopedia never.** Each episode is a 35-second gut punch, not a lecture. The viewer should FEEL something — dread, then devastation, then relief they weren't there. A script that teaches facts but creates no emotion has failed.
- **Nature documentary meets apocalypse.** The narrator speaks like a British naturalist guiding you through the most extraordinary forces on Earth — geological, meteorological, human. The horror comes from the calm, measured delivery of devastating facts, not from snark or humor.
- **Immersive thriller, never lecture.** The viewer IS the skeleton — the disaster happens TO them. The script reads like a first-person survival story narrated by a world-class documentarian.
- **Teach through feeling, not exposition.** Facts land because the viewer encounters them in their body. Not "the tank holds two million gallons" (textbook) but "the tank above your street holds two million gallons — and it has been groaning all winter" (story). The viewer learns the same fact but FEELS the dread.
- **Measured gravitas, not dark comedy.** The narrator treats every disaster with the respect it deserves. Scientific precision. Genuine awe at scale.
- **The "thank god" test.** Every episode must leave the viewer physically relieved they didn't live through that event. Not intellectually aware of a tragedy — viscerally grateful to be alive now.
- **Second person address, present tense.** Always "you", "your" — and always present tense for immediacy. "You" must be the SUBJECT of sentences in EVERY clip. The disaster happens TO you, not around you.

## Format

- Vertical 9:16 short-form video optimized for YouTube Shorts, TikTok, and Instagram Reels
- **~35 seconds per episode** (40s raw, ~38s effective after crossfades — narration fills ~33s, final seconds are visual-only)
- **75–90 words of narration** at ~2.6 words/second (measured ElevenLabs pacing) as **continuous prose** — narration flows across clip boundaries as one unbroken audio stream, overlaid on the final stitched video in post-production
- Classic American adult animation style (flat cel-shaded, thick outlines)
- The skeleton appears on camera but never speaks — narration is off-screen voiceover
- **Split audio pipeline**:
  - **Veo 3.1**: Generates SILENT video with environmental SFX + ambient sounds only
  - **ElevenLabs TTS**: Generates narrator voiceover as ONE continuous audio file (Dan — British Documentary Narrator, voice ID `BHr135B5EUBtaWheVj8S`)
  - **ElevenLabs Music**: Generates cinematic nature documentary underscore
  - **Whisper**: Word-level timestamps on the continuous narration for visual sync reference
  - **ffmpeg**: Overlays full narration + music onto final stitched video in a single pass
- Remotion-rendered karaoke captions (Whisper transcription + transparent overlay)
- **5 clips** (all 8s) — target visual change every 8 seconds
- Static locked camera throughout — flat 2D animated compositions
- Native Veo output durations only — NEVER crop or trim video

## Episode Structure (3-Beat Narrative Arc with optional Turn)

Every episode follows this arc across 4-5 clips (~38s effective video, narration as continuous prose ~75-90 words):

1. **The Hook** (clip 01, 0–5s) — Voice starts IMMEDIATELY on frame 1. No silent establishing shots. No questions. The FIRST sentence is the conflict premise — the most interesting thing about this event stated plainly. The framing line ("You would not want to be in/at [Event], [Year]") comes LAST in clip 01, never first. Goal: instant conflict in the first second, then event identification.
2. **Easy Explanation** (clips 02–03, 5–18s) — Two clips that build the situation fast. Clip 02 grounds the viewer in a place and time with one sensory detail. Clip 03 introduces the fatal element and activates it. The viewer should understand the mechanism — WHY this disaster happened.
3. **The Turn + Catastrophe** (clip 03-04, 18–28s) — The strongest episodes have a TURN: a moment where the viewer thinks they understand how bad it is, then it gets WORSE in a way they didn't expect (a second failure, an escape closing, an authority refusing to act). Clip 04 is the catastrophe — staccato, sensory, physical. The disaster reaches you.
4. **Revelation Ending** (clip 05, 28–35s) — NOT a summary. A single revelation that recontextualizes the entire story. The viewer's brain should still be processing when the video cuts. Lead with cause or irony — embed scale inside the revelation. NEVER open with a death toll number. Abrupt cut — never signal the video is ending.

Each beat spans 1–2 clips. The narration is one continuous audio stream — sentences flow freely across clip boundaries. Visual cuts happen mid-narration, pulling the viewer forward.

## Retention Principles

- **First frame is the thumbnail.** In autoplay environments (TikTok, Reels, Shorts), the first frame IS the thumbnail. The first image must show the TENSION from the hook, not a calm establishing shot.
- **Premise first, branding last.** The framing line is branding — it creates zero curiosity. Always open with the conflict premise.
- **Re-engagement via Turn.** The viewer needs at least one "wait, it gets WORSE?" moment — a shift they didn't predict. This prevents linear escalation from becoming predictable.
- **Revelation endings, not summary endings.** The final line should make the viewer's brain go "wait—" as the video cuts. Never open the final clip with a death toll number — that signals "we're summarizing now" and the thumb starts swiping.
- **Abrupt cut.** Never signal the video is ending. The ending is a revelation the viewer is still processing when the screen goes black.
- **Emotional stakes.** The viewer must CARE, not just understand. Sensory dread, reasonable decisions turning fatal, and hope being crushed create visceral engagement that statistics alone cannot.

## Narrator Voice

- Calm, measured, authoritative British naturalist — the voice of a National Geographic documentary narrator who has spent decades in the field
- Warm curiosity and genuine reverence for the forces involved — geological, meteorological, human
- The horror comes from the steady, composed delivery of devastating facts — not from humor or theatrics
- Scientific precision: specific numbers, temperatures, distances, chemical reactions
- Addresses the viewer directly in second person present tense: "you wake up", "you feel the ground shift"
- Pacing: ~2.6 words per second (measured ElevenLabs output), **75–90 words per episode** as continuous prose
- Narration is generated as ONE continuous audio file and overlaid on the final stitched video in post-production
- **Sentence structure**: Flowing for explanation clips, staccato for catastrophe. Sentences freely cross clip boundaries.
- **Sensory texture**: What does the disaster FEEL like to the viewer's body? Not just numbers but sensation — heat on skin, dust in lungs, the floor shaking.
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

- **Story first.** You are writing a 35-second story, not a lecture. If a sentence could appear unchanged on Wikipedia, rewrite it.
- **Premise first, framing line last.** Clip 01 opens with the conflict — the most interesting thing about this event. The framing line ("You would not want to be in...") comes LAST in the clip, never first.
- **Nature documentary tone.** Calm, measured, authoritative — National Geographic meets PBS. The horror comes from composure, never snark.
- **Continuous prose.** One flowing narrative across 4-5 clips. Sentences cross clip boundaries via em dash (—).
- **Second person, present tense.** Always "you." Always now. "You" appears in every clip — the disaster happens TO you.
- **Causal chain.** Every sentence connects to the one before it. If a sentence could be deleted without the next losing meaning, cut it.
- **No causal gaps.** If the situation changes between clips, the script must show what caused the change. Never skip from setup to catastrophe without the mechanism — the decision, the failure, the turning point that connects them.
- **The Turn.** The strongest scripts have a "wait, it gets worse?" moment — an unexpected escalation that re-engages the viewer mid-story.
- **Sensory texture.** What the disaster feels like in your body — heat, dust, shaking, cold. These moments separate a story from a report.
- **The narrator never foreshadows.** No "little did you know," no "until it doesn't," no commentary on what is about to happen. Let the viewer discover it.
- **Revelation ending.** The final clip is a reveal that recontextualizes the story, not a summary. Never open the final clip with a death toll number. Abrupt cut.
- **75–90 words total.** At 2.6 words/second, every word earns its 0.4 seconds. Continuous narration overlaid on the final stitched video.

## TikTok / YouTube Shorts Optimization

- **Voice on frame 1.** The hook plays over the very first visual. ZERO seconds of silence.
- **Premise first, framing line last.** Clip 01 opens with the conflict premise. The framing line ("You would not want to be in [Event], [Year]") comes LAST in the clip. Never burn the first 2-3 seconds on branding.
- **First frame = scroll-stop.** The first image must show the TENSION from the hook sentence, not a calm establishing shot. In autoplay, this image IS the thumbnail.
- Target **~35 seconds** total video (4-5 clips, ~38s effective after crossfades), narration 75–90 words as continuous prose
- **Visual change every 8 seconds** — each clip is a new shot, new information
- **Every clip raises the stakes** — no plateaus, no breathing room
- **At least one Turn** — a "wait, it gets worse?" moment that re-engages the viewer mid-video
- Narrator fills EVERY clip — no silent clips, no dead air
- **Revelation ending** — the last line recontextualizes the story, leaving the viewer's brain still processing when the video abruptly cuts. Never open the final clip with a death toll number.
- **Abrupt cut** — never signal the video is ending. The revelation lands and the screen goes black.
