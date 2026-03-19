# You Wouldn't Wanna Be — Cinematography Bible

This document defines the visual language of the series. Every storyboard, image prompt, and video prompt must reference this guide. The goal: every clip should look like a frame from a classic American adult animated comedy — flat cel-shaded art, thick outlines, darkly comic staging, historically grounded settings.

---

## 1. Animation DNA

The visual identity of You Wouldn't Wanna Be is rooted in classic American adult animated comedy (Family Guy seasons 10-20 aesthetic) applied to dark historical scenarios.

### The Look

- **Flat cel-shaded coloring**: ZERO gradients. Clean flat colors on all characters, objects, and backgrounds. Every element has a single flat fill color.
- **Thick uniform black outlines**: On ALL elements — characters, props, architecture, landscape. Consistent line weight throughout.
- **Simplified features**: Dot eyes, simplified hands, clean vector rendering. No photorealistic detail.
- **No 3D**: No depth-of-field blur, no lighting effects, no shading variation, no volumetric atmosphere. All atmosphere conveyed through color and composition, not rendering effects.
- **Static locked camera**: Every shot is a locked-off composition. No handheld, no shaky-cam, no camera drift. Camera movements are clean pans or cuts only.
- **Flat 2D compositions**: Painted layered backgrounds with minimal parallax. Foreground, midground, and background as distinct 2D planes.
- **Period-accurate settings in animation style**: Historical architecture, costumes (on background characters), and environments rendered with flat colors and thick outlines.

### Color Approach

Each era gets its own distinctive flat color palette with environment-specific visual richness:
- **Ancient Rome/Greece**: Warm terracotta, dusty ochre, olive green — cracked mosaic floors, marble columns with chisel marks, amphora fragments, oil lamps with flat amber glow, togas with geometric borders
- **Medieval plague/siege**: Grey-green, brown, muted purple — half-timbered buildings, muddy cobblestones, tallow candle wax pools, iron-banded doors, faded heraldic banners
- **Age of Sail/Colonial**: Deep navy, weathered teal, salt-white, rope-brown — rigging lines, barnacled hulls, brass fittings gone green, tar-sealed planks, folded canvas
- **Victorian/Industrial**: Sooty amber, gas-lamp gold, dark teal, chimney-black — brick smokestacks, wrought-iron railings, soot-streaked glass, cobbled streets with horse-drawn carts
- **Early 20th Century**: Muted sepia, olive drab, dusty cream — ticker tape, newsprint, telegram paper, brass telephones, Art Deco metalwork
- **Nuclear/Cold War**: Cold grey-blue, hazard yellow, clinical white — concrete bunkers, Geiger counter dials, radiation trefoils, institutional green paint, steel blast doors
- **Natural Disaster (any era)**: Derived from the era palette above, pushed to extremes — fire events saturate toward orange/black, water events toward slate-grey/foam-white, earth events toward dust-brown/ash-grey

Characters always use their fixed color palette regardless of setting.

---

## 2. Shot Grammar

### Shot Types (all static, locked camera)

| Shot | When to Use | Emotional Function |
|------|------------|-------------------|
| **Wide establishing** | Opening shots, scene transitions | Scale of the setting, character dwarfed by history |
| **Medium two-shot** | Character interacting with environment | Grounding, neutral observation |
| **Medium close-up** | Reaction beats, dramatic moments | Emotional weight, reading the character's reaction |
| **Close-up** | Peak horror, peak comedy | Maximum emotional impact |
| **Low-angle** | Disaster approaching, scale of threat | Dread, intimidation, the figure feels small |
| **High-angle** | Character in peril, vulnerability | Helplessness, the viewer looks down on the doomed figure |
| **Over-shoulder** | The figure watching something terrible unfold | POV alignment, shared dread |

### Camera Rules

- **ALWAYS static**: Locked camera, flat composition. No handheld.
- **No parallax**: Minimal depth motion. Flat 2D staging.
- **Clean cuts between clips**: Hard cuts, no dissolves or transitions.
- **Flat framing**: Characters and environment on the same visual plane. Classic animated comedy staging.

### Dynamic World Within a Static Frame

"Static camera" means the camera itself does not move. The world WITHIN the frame should be alive:
- **Layered movement**: Foreground elements (debris, smoke, water) move at different rates than midground (character) and background (crowds, fire). This creates depth and energy without camera motion.
- **Environmental animation**: Fire flickers, water flows, dust drifts, crowds mill, flags wave, smoke billows. Every frame should have at least 2-3 moving environmental elements appropriate to the era and beat.
- **Progressive intensity**: Calm beats have subtle movement (a breeze, distant figures). Catastrophe beats have maximum environmental chaos (flying debris, collapsing structures, rushing water) — all within the locked frame.
- **Light-as-color shifts**: Within a single clip, the flat color palette can shift to convey changing conditions — the sky darkening, fire glow intensifying, dust thickening. These are expressed as flat color overlay changes, not lighting physics.

---

## 3. Composition Rules

### Rule of Thirds (adapted for animation)
- Character typically at 1/3 from left or right
- Important environmental elements (the disaster, the landmark) fill the opposing 2/3
- Flat 2D staging — no converging perspective lines

### Depth Layers (as 2D planes)
Every shot must explicitly define three layers:
1. **Foreground**: Props, debris, environmental details closest to camera. Drawn larger, sometimes overlapping character.
2. **Midground**: The figure and immediate surroundings. The action zone.
3. **Background**: Historical setting at scale — architecture, crowds, landscapes. Painted flat.

### Character Staging
- The figure should be clearly readable even in wide shots — the translucent skeleton silhouette with thick outlines is always recognizable
- Cartoon physical comedy requires clear silhouette — no poses where limbs overlap confusingly
- Background characters are simplified animated figures (even simpler than the main character)

---

## 4. Lighting Playbook (adapted for animation)

Animation lighting is conveyed through **color palette shifts**, not through realistic light/shadow rendering. All lighting remains flat — no volumetric effects, no cast shadows, no rim lighting.

| Setup | Color Approach | When to Use |
|-------|---------------|-------------|
| **PERIOD AMBIENT** | Warm natural palette — era-appropriate flat colors, medium saturation | Normal scene establishment, immersion beats |
| **OMINOUS BUILDUP** | Same palette but darker and cooler — desaturated, blue/grey undertones creeping in | Pre-disaster tension, "something is wrong" |
| **HIGH CONTRAST CATASTROPHE** | Extreme warm/cool contrast — fire oranges against dark backgrounds, or bright flash whites | The disaster itself, maximum dramatic impact |
| **AFTERMATH GREY** | Nearly monochrome flat grey/brown palette — dust, ash, muted everything | Post-catastrophe, the cliffhanger, quiet horror |

### How to Direct Animation Lighting in Prompts

Instead of describing light sources (torches, sun angle), describe the **flat color palette**:
- "Warm flat amber palette with ochre and terracotta tones" (not "golden hour sunlight")
- "Dark desaturated blue-grey palette with cold undertones" (not "moonlit scene")
- "High contrast: bright orange fire glow against dark navy sky" (not "backlighting from flames")

### Banned Vocabulary (NEVER use in prompts)

These terms push AI generators toward photorealism and away from flat animation:

**Lighting physics**: film grain, shallow/deep depth of field, bokeh, lens flare, god rays, volumetric (light/fog/haze), rim lighting, rim lit, subsurface scattering, caustics, cinematic lighting, global illumination, specular highlight, natural lighting

**Camera/lens terms**: anamorphic, 35mm, DSLR, raw photo, motion blur, chromatic aberration, vignette, deep focus, rack focus

**Rendering terms**: photorealistic, hyper-realistic, ray tracing, PBR, realistic rendering

**Instead, describe**: flat color names, flat even lighting, flat atmospheric haze, flat 2D composition, dramatic (not cinematic)

---

## 5. Visual Pacing

### Energy Arc
Every episode follows this visual energy arc:

| Beat | Energy | Visual Approach |
|------|--------|----------------|
| Hook (clip 01) | 3/5 | Wide establishing shot, warm palette, curiosity |
| Setup (clip 02) | 3/5 → 4/5 | Medium shot, character grounded, palette shifting |
| Escalation (clip 03) | 4/5 → 5/5 | Tighter framing as stakes rise, character in motion |
| Catastrophe (clip 04) | 5/5 | Close-ups at peak chaos, maximum intensity, saturated palette |
| Twist Payoff (clip 05) | 5/5 → 2/5 | Wide aftermath — stunned stillness, muted palette |

### Pacing Rules
- **Visual change every 3-4 seconds**: New angle, new information, new framing
- **Tighten across the episode**: Start wide, end close — the disaster closes in
- **The figure gets physically smaller** as the catastrophe grows larger
- **Final clip is the quietest**: Wide framing, aftermath palette, lingering stillness
