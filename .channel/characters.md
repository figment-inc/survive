# You Wouldn't Wanna Be — Character Sheet

This sheet is for internal reference only.

## The Skeleton — Main Character

- **Appearance**: A humanoid figure with translucent, ghostly pale skin revealing a complete bone structure underneath. The skeleton is visible through semi-transparent flesh — skull, ribcage, spine, pelvis, limb bones all clearly defined. Medium build, neutral height, standing upright. Rendered in **flat cel-shaded 2D animation style** with thick black outlines — classic American adult animation aesthetic. Eyes are visible as pale orbs set in the skull sockets. No hair. No clothing (the translucent body IS the costume). This appearance is fixed across all episodes regardless of era.
- **Role**: The hapless protagonist. Drops into every historical disaster and tries — always fails — to navigate it. Physical comedy through exaggerated cartoon body language: flinching, ducking, running, tripping, looking around in confusion, throwing hands up in disbelief. A silent victim of history's worst moments.
- **Visual reaction style**: Wide panicked eyes (the pale orbs in the skull), arms thrown up defensively, stumbling backward, crouching behind objects, running with exaggerated arm flailing, looking left and right in confusion, frozen stiff with shock, dramatic cartoon flinching from explosions/eruptions/impacts. Classic animated comedy reaction vocabulary: double-takes, slow head-turns, jaw-drops, full-body freezes. The translucent body means reactions read clearly even in wide shots — the skeleton silhouette is always recognizable. THE MOUTH MUST REMAIN CLOSED AT ALL TIMES — no lip movement, no jaw movement, no mouth animation.
- **Personality**: Eternally confused, perpetually doomed, somehow optimistic at the start of each episode before reality sets in. Not stupid — just hilariously unlucky. Every attempt to improve the situation makes it worse.

## Visual Consistency (for image and video prompts)

The skeleton has the **same fixed appearance in every episode**, regardless of historical era. This is a deliberate brand choice for cross-episode recognition. All renders use **flat cel-shaded 2D animation style** with thick black outlines.

When generating images or videos containing the character, include this description block:

> 2D animation character description: A humanoid figure with translucent, ghostly pale skin through which a complete skeleton is clearly visible — skull with pale orb-like eyes in the sockets, ribcage, spine, pelvis, and limb bones all defined beneath the semi-transparent surface. Medium build, no hair, no clothing. Thick black outlines. Rendered as a flat 2D cartoon character.

### Reference Images

Angle-aware reference sheets in `.channel/reference_images/` establish the character's appearance at 4 angles:

| File | Angle | Purpose |
|------|-------|---------|
| `skeleton_familyguy_front.png` | Front | Primary identity anchor, full-body |
| `skeleton_familyguy_side.png` | Side profile | Depth and silhouette |
| `skeleton_familyguy_threequarter.png` | 3/4 view | Most natural camera angle |
| `skeleton_familyguy_back.png` | Rear | For behind-the-character shots |
| `skeleton_front_neutral.jpg` | Front (original) | Photorealistic source / fallback |

The pipeline automatically selects the best 3 reference images based on camera angle keywords in each video prompt.

## Naming Rules for Veo Prompts

- Refer to the character as **the figure** or **the translucent character**
- NEVER reference copyrighted show names (Family Guy, Simpsons, etc.) — use "classic American adult animation style"
- The character NEVER speaks, NEVER moves their mouth in Veo prompts — include "The on-screen character does NOT speak and does NOT move their mouth. Mouth remains closed. Silent physical reactions only."
- Every prompt must include the MANDATORY STYLE block (flat cel-shaded, thick outlines, no 3D)
- Video prompts generate SILENT video — no narrator lines, no dialogue, no music
- The reference image handles visual identity
- If "skeleton" triggers safety filters, use "translucent anatomical figure" or "ghostly figure with visible bone structure"

## The Narrator

- **Voice**: Calm, measured, authoritative British naturalist — the voice of a National Geographic documentary. Warm curiosity and genuine reverence for the forces involved — geological, meteorological, human. Unhurried pacing, as if studying something extraordinary and fragile. The horror comes from the steady, composed delivery of devastating facts, not from humor or theatrics.
- **Address**: Second person — speaks directly to the viewer/skeleton as "you". "You stand on the cobblestones of Galveston Island, a sandbar barely 8 feet above sea level."
- **Educational depth**: Every clip includes at least one specific, verifiable fact — temperatures, distances, death tolls, chemical reactions, geological forces, engineering failures.
- **Sentence style**: Flowing documentary narration. Average 8-15 words per sentence. Measured, building, with pauses for impact.
- **Pacing**: ~3 words per second. ~20-25 words per 8s clip. Leaves room for Veo ambient audio to breathe.
- **Produced via**: **ElevenLabs TTS** (Dan — British Documentary Narrator, voice ID `BHr135B5EUBtaWheVj8S`). Mixed with Veo video in post-production. Voice settings: stability 0.85, similarity_boost 0.75, style 0.15.
