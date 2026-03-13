# You Wouldn't Wanna Be — Prompting Guide

This guide covers prompt writing for NanoBanana Pro (images) and Veo 3.1 (video). For technical specs, see `production.md`.

---

## 1. Prompting Philosophy

### NanoBanana Pro (Images)

NanoBanana Pro excels at photorealistic image generation with strong character consistency when given reference images. Key principles:

- **Reference image is king.** Always pass the skeleton reference for character clips. NanoBanana Pro's image-to-image mode uses references to lock character appearance.
- **Be specific about the era.** Generic "ancient city" produces generic results. "Roman forum with travertine columns, terracotta roof tiles, graffiti scratched into plaster walls" produces period accuracy.
- **Describe the skeleton's pose explicitly.** The translucent body is unusual — you need to tell the model exactly how it's positioned, what it's doing with its hands, where it's looking.
- **Three depth layers are mandatory.** Foreground texture, midground character, background scale. This creates the cinematic depth that separates this from flat AI imagery.

### Veo 3.1 (Video)

- **Think in sequences, not stills.** Describe what happens over the clip's duration — a progression.
- **Every clip is a mini-narrative.** Even a 4-second clip has a beginning and end.
- **Be explicit about motion.** What moves, how, how fast. Camera movement and subject movement are separate.
- **Native audio matters.** Veo generates synchronized ambient audio. Describe the sound environment.

---

## 2. NanoBanana Pro Specifics

### Model Selection

- `nano-banana-pro` for scene keyframes (best quality, 20 credits at 1K)
- `nano-banana-fast` for quick iterations during development (5 credits)
- Always use `image-to-image` mode with skeleton reference for character shots
- Use `text-to-image` mode for establishing shots (no character)

### Reference Image Strategy

- Pass the canonical skeleton reference (`skeleton_front_neutral.png`) for every character image
- For close-ups, also pass the headshot reference
- NanoBanana supports up to 8 reference images — use 1-3 for consistency

### Aspect Ratio and Resolution

- Always `9:16` for YouTube Shorts vertical format
- `2K` for final keyframes, `1K` for iterations
- Output format: `png`

### Prompt Structure for NanoBanana

```
[SCENE DESCRIPTION — specific location, time period, atmosphere]

[CHARACTER — the translucent skeletal figure, specific pose and expression]

[DEPTH LAYERS — foreground, midground, background]

[LIGHTING — named from cinematography playbook]

[STYLE — period-accurate, cinematic, dark atmosphere]

No text, no watermarks, no logos, no captions, no overlays.
```

---

## 3. Veo 3.1 Specifics

### Cinematic Language

Veo 3.1 understands cinematic terminology natively:

| Term | Use for | Example |
|------|---------|---------|
| WS (Wide Shot) | Establishing, scale | "Wide shot of the city at dawn" |
| MS (Medium Shot) | Character grounding | "Medium shot, figure visible waist-up" |
| CU (Close-Up) | Emotion, reaction | "Close-up on the figure's skull, eye sockets widening" |
| OTS (Over-the-Shoulder) | POV alignment | "Over-the-shoulder, looking at the eruption" |

### Camera Movements

| Movement | Effect | Example |
|----------|--------|---------|
| Pan | Reveals space | "Slow pan across the harbor" |
| Dolly / Push-in | Increasing intensity | "Slow dolly forward toward the figure" |
| Tracking | Following action | "Tracking shot following the figure as it runs" |
| Handheld | Urgency, chaos | "Handheld, slight shake, disaster energy" |

### Audio Direction for Veo

Veo generates native audio. Direct it with:

```
Audio direction:
- SFX: [specific sound events — explosions, crumbling stone, screaming crowds]
- Ambience: [continuous environmental — wind, fire crackling, distant rumbling]
```

NEVER include dialogue or music direction. Those come from ElevenLabs in post.

---

## 4. Character Consistency

- **Repeat key visual identifiers in every prompt**: translucent pale skin, visible skeleton underneath, no hair, no clothing, pale orb eyes in skull sockets
- **Pose is critical**: since the character never speaks, every prompt must specify exactly what it's doing physically
- **The silhouette must read**: even in wide shots, the skeleton should be identifiable by its translucent form and skeletal outline

---

## 5. Prompt Rewriter Awareness (Veo)

Veo 3.1 has an always-active prompt rewriter:

- Be maximally explicit about non-negotiable elements
- Redundancy protects critical details — mention the camera angle twice
- Use negative prompts: "No text overlays. No watermarks. No dialogue."
- Expect stylistic drift — reinforce the dark, atmospheric look
