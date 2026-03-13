# You Wouldn't Wanna Be — Prompting Guide

This guide covers prompt writing for NanoBanana Pro (images) and Veo 3.1 (video). For technical specs, see `production.md`.

---

## 1. Prompting Philosophy

### NanoBanana Pro (Images)

NanoBanana Pro generates keyframe images with character reference conditioning. Key principles:

- **MANDATORY STYLE block first.** Every prompt must start with the animation style enforcement block — flat cel-shaded, thick outlines, no 3D, no photorealistic elements.
- **Reference image is king.** Always pass the skeleton reference for character clips. NanoBanana Pro's image-to-image mode uses references to lock character appearance.
- **Be specific about the era.** Generic "ancient city" produces generic results. "Roman forum with terracotta columns and cracked flagstones" (all in flat 2D animation style) produces period accuracy.
- **Describe the skeleton's pose explicitly.** The translucent body is unusual — you need to tell the model exactly how it's positioned, what it's doing with its hands, where it's looking. Use cartoon reaction vocabulary.
- **Three depth layers are mandatory.** Foreground props, midground character, background historical setting. All rendered as flat 2D animation planes.

### Veo 3.1 (Video)

- **Think in sequences, not stills.** Describe what happens over the clip's duration — a progression.
- **Every clip is a mini-narrative.** Even a 4-second clip has a beginning and end.
- **Static camera always.** Locked-off compositions. No handheld, no drift.
- **ALL audio in the prompt.** Veo generates narrator speech, SFX, ambience, and music natively. Direct all of them.
- **Animation style enforcement.** The mandatory style block prevents Veo from drifting to photorealistic.

---

## 2. NanoBanana Pro Specifics

### Model Selection

- `nano-banana-pro` for scene keyframes (best quality, 20 credits at 1K)
- `nano-banana-fast` for quick iterations during development (5 credits)
- Always use `image-to-image` mode with skeleton reference for character shots
- Use `text-to-image` mode for establishing shots (no character)

### Reference Image Strategy

- Pass the canonical skeleton reference for every character image
- Angle-aware selection: the pipeline picks the best reference based on camera angle
- NanoBanana supports up to 8 reference images — use 1-3 for consistency

### Aspect Ratio and Resolution

- Always `9:16` for YouTube Shorts vertical format
- `2K` for final keyframes, `1K` for iterations
- Output format: `png`

### Prompt Structure for NanoBanana

```
MANDATORY STYLE — AMERICAN ADULT ANIMATION: [full style block]

Classic American adult animation frame, vertical 9:16 composition. [Location], [Time].

[CAMERA — static shot type, flat 2D composition]

[CHARACTER VISUAL CONSISTENCY BLOCK — full description]

[CHARACTER BLOCKING — specific cartoon pose, gesture, expression]

[DEPTH LAYERS — foreground, midground, background — all in flat 2D style]

[LIGHTING + PALETTE — flat even lighting, named color palette]

[PERIOD TEXTURE — one specific historical detail]

[BACKGROUND ACTIVITY — animated people doing things]

No text, no watermarks, no logos, no captions, no overlays. No photorealistic rendering.
```

---

## 3. Veo 3.1 Specifics

### Shot Types (all static)

| Shot | When to Use | Emotional Function |
|------|------------|-------------------|
| Wide | Establishing, scale | Setting dwarfs the character |
| Medium | Character grounding | Neutral observation, character readable |
| Close-up | Emotion, reaction | Maximum emotional impact |
| Low-angle | Dread, intimidation | Character feels small |
| High-angle | Vulnerability | Looking down on the doomed figure |

### Camera Rules

- **ALWAYS static locked camera.** No handheld, no shaky-cam, no drift.
- "Camera: Static [shot type]. Locked camera, flat composition, no movement."
- Clean cuts between clips. No dissolves.

### Audio Direction for Veo

Veo 3.1 generates ALL audio natively. Direct every layer:

```
Dialogue direction:
- Off-screen narrator says: "[exact narration line]"
- The on-screen character does NOT speak. Silent physical reactions only.

Voice direction:
- Narrator voice: Male, darkly amused British accent, [delivery notes].

Audio direction:
- Music: [cinematic underscore description — instruments, intensity, mood]
- SFX: [specific sound events — crumbling stone, distant explosion, etc.]
- Ambience: [continuous environment — crowd panic, wind, fire crackling]
```

All four blocks (dialogue, voice, music/SFX/ambience) must appear in EVERY video prompt.

---

## 4. Character Consistency

- **Repeat the full character visual consistency block in every prompt**: translucent pale skin, visible skeleton, thick black outlines, flat 2D cartoon rendering
- **Pose is critical**: since the character never speaks, every prompt must specify exactly what it's doing physically — use cartoon vocabulary (double-take, jaw-drop, arms flailing, frozen stiff)
- **The silhouette must read**: even in wide shots, the skeleton should be identifiable by its translucent form, thick outlines, and skeletal silhouette
- **Angle-aware references**: the pipeline selects the best reference images based on camera angle keywords in the prompt (front, side, three-quarter, back)

---

## 5. Prompt Rewriter Awareness (Veo)

Veo 3.1 has an always-active prompt rewriter:

- Be maximally explicit about non-negotiable elements (animation style, character description)
- Redundancy protects critical details — the mandatory style block reinforces flat 2D throughout
- Use negative prompts: "No text overlays. No watermarks. No photorealistic rendering. No 3D shading."
- Expect stylistic drift — the mandatory style block and reference images together prevent it
- NEVER use copyrighted show names in prompts — they trigger safety filters
