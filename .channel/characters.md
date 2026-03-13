# You Wouldn't Wanna Be — Character Sheet

This sheet is for internal reference only.

## The Skeleton — Main Character

- **Appearance**: A humanoid figure with translucent, ghostly pale skin revealing a complete bone structure underneath. The skeleton is visible through semi-transparent flesh — skull, ribcage, spine, pelvis, limb bones all clearly defined. Medium build, neutral height, standing upright. The overall look is anatomical-model-meets-ghost: clinical yet eerily comic. Eyes are visible as pale orbs set in the skull sockets. No hair. No clothing (the translucent body IS the costume). This appearance is fixed across all episodes regardless of era.
- **Role**: The hapless protagonist. Drops into every historical disaster and tries — always fails — to navigate it. Physical comedy through body language: flinching, ducking, running, tripping, looking around in confusion, throwing hands up in disbelief. A silent victim of history's worst moments.
- **Visual reaction style**: Wide panicked eyes (the pale orbs in the skull), arms thrown up defensively, stumbling backward, crouching behind objects, running with exaggerated arm flailing, looking left and right in confusion, frozen stiff with shock, dramatic flinching from explosions/eruptions/impacts. The translucent body means reactions read clearly even in wide shots — the skeleton silhouette is always recognizable.
- **Personality**: Eternally confused, perpetually doomed, somehow optimistic at the start of each episode before reality sets in. Not stupid — just hilariously unlucky. Every attempt to improve the situation makes it worse.

## Visual Consistency (for image and video prompts)

The skeleton has the **same fixed appearance in every episode**, regardless of historical era. This is a deliberate brand choice for cross-episode recognition.

When generating images or videos containing the character, include this description block:

> A humanoid figure with translucent, ghostly pale skin through which a complete skeleton is clearly visible — skull with visible eye sockets, ribcage, spine, pelvis, and limb bones all defined beneath the semi-transparent surface. Medium build, no hair, no clothing. The figure has an eerie, anatomical quality — like a medical model brought to life. Pale orb-like eyes sit in the skull sockets. The overall silhouette reads as unmistakably skeletal even in wide shots.

Canonical reference images in `.channel/reference_images/` establish the character's appearance. Always pass these as style/character conditioning when generating 8s video clips or character images.

## Naming Rules for Veo Prompts

- Refer to the character as **the figure** or **the translucent character**
- The character NEVER speaks in Veo prompts — include "No dialogue. No speech." in every prompt
- The reference image handles visual identity
- If "skeleton" triggers safety filters, use "translucent anatomical figure" or "ghostly figure with visible bone structure"

## The Narrator

- **Voice**: Darkly amused British male voice. Authoritative with gallows humor and genuine fascination. A morbidly delighted history professor who clearly enjoys cataloguing disasters.
- **Address**: Second person — speaks directly to the viewer/skeleton as "you". "You've just arrived in Pompeii. It is August 24th, 79 AD. This was a mistake."
- **Relationship to character**: Dark affection. "Our unfortunate friend", "our doomed visitor", occasionally just "you" with dripping sympathy.
- **Humor style**: Dry British understatement at peak horror. Litotes. Clinical precision about horrible details delivered with a hint of a smile. "Things are about to get, shall we say, suboptimal." Never laughing at real victims — the skeleton absorbs all the comedic punishment.
- **Pacing**: ~3 words per second. ~15-18 words per 8s clip. Leaves room for Veo ambient audio to breathe.
- **Produced via**: ElevenLabs TTS API.
