# You Wouldn't Wanna Be — Production Standards

## Clip Specs

- **Aspect ratio**: 9:16 vertical
- **Episode length**: 9–12 clips, **60–75 seconds** total (target 65s)
- **Narration target**: **200–230 words** at ~3 words/second — dense, no dead air
- **Native Veo output only** — NEVER crop, trim, or re-encode clips after generation
- **Narration-over format**: the skeleton appears on camera but never speaks — Veo generates ambient/SFX clips
- **Voice on frame 1** — narration starts over the very first clip, no silent openings

| Clip Type | Duration | Resolution | Reference Images | Character | Dialogue |
|-----------|----------|------------|------------------|-----------|----------|
| HOOK | 4s | 720p | No (text-only) | Optional | No |
| SCENE | 4s or 8s | 1080p | Yes (canonical ref) | Yes | **No** — character reacts silently |

- **Mix clip durations**: alternate 4s and 8s clips for visual rhythm. Use 4s for quick beats, 8s for continuous motion.
- **Typical episode**: 9–12 clips mixing 4s and 8s segments
- The skeleton is on camera in every SCENE clip but **never speaks**
- All exposition is carried by narrator voiceover (ElevenLabs TTS, mixed in post)

## Naming Rules

- Avoid "skeleton" in Veo prompts if it triggers safety filters
- Use **the figure** or **the translucent character** instead
- Every prompt with the character must include: "No dialogue. No speech."
- The reference image handles visual identity

## Clip Production Spec

Every clip in the storyboard must include these production fields:

- **Camera angle**: chosen for emotional function (see `cinematography.md`)
- **Shot motivation**: WHY this angle — what it communicates emotionally
- **Camera movement**: Steadicam, dolly push-in, tripod locked-off, tracking, camera shake for disaster beats
- **Lighting setup**: named from the playbook in `cinematography.md`
- **Composition**: character blocking, rule of thirds, leading lines, depth staging
- **Depth layers**: foreground object/texture, midground character space, background historical scale
- **Atmosphere**: haze, dust, steam, smoke, ash — air is never perfectly clear
- **Period texture**: at least one specific detail unique to this exact time and place
- **Background activity**: other people doing things in the scene
- **Visual transition**: how this clip's visual connects to the previous clip
- **Visual action**: what the skeleton is physically doing (reactions, gestures, movement)
- **Narration**: what the narrator says over this clip

## Models

- **Image generation**: NanoBanana Pro API (`nano-banana-pro` model, 2K resolution)
- **Video generation**: Veo 3.1 (`veo-3.1-generate-preview`)
- **Narrator voiceover**: ElevenLabs TTS API (`eleven_multilingual_v2`)
- **Background music**: ElevenLabs Music API
- **Sound effects**: Veo native audio (ambient/SFX generated with the video)
- **Safety settings**: `BLOCK_ONLY_HIGH` for all Gemini/Veo harm categories

## NanoBanana Pro Image Generation

- **API**: `POST https://nanobananapro.cloud/api/v1/image/nano-banana`
- **Poll results**: `POST https://nanobananapro.cloud/api/v1/image/nano-banana/result`
- **Model**: `nano-banana-pro` (20 credits per image at 1K, scales for 2K/4K)
- **Aspect ratio**: 9:16 for all frames
- **Image size**: 2K for scene keyframes, 1K for reference generation
- **Reference images**: up to 8 via multipart upload for character consistency
- **Mode**: `image-to-image` when using skeleton reference, `text-to-image` for establishing shots

## Veo 3.1 Duration/Resolution Constraints

- 4s clips: 720p only, supports first-frame conditioning from keyframe images
- 8s clips: 1080p, supports up to 3 reference images + `person_generation=allow_adult`
- Reference images and first/last frame modes **cannot be combined**
- All scene clips use 8s at 1080p with canonical reference images

## Character Consistency

- The skeleton has the **same fixed appearance** in every episode (see `characters.md`)
- **Canonical reference images** are passed to every 8s scene clip:
  1. `skeleton_front_neutral.png` — full-body, primary identity anchor
  2. `skeleton_headshot.png` — close-up for facial/skull detail
  3. `skeleton_side.png` — 3/4 angle for depth
- Passed as `VideoGenerationReferenceImage(reference_type="ASSET")`
- For 4s establishing shots: use first-frame conditioning from generated keyframe images

## Audio Pipeline

### Veo Native Audio (SFX + Ambience)

Veo generates video clips with native ambient audio and sound effects. This audio is **kept** in the final mix — it provides period-accurate environmental sound.

### ElevenLabs (Narration + Music)

| Layer | API Endpoint | Purpose |
|-------|-------------|---------|
| Narrator voiceover | `POST /v1/text-to-speech/{voice_id}` | Per-clip narration from script |
| Background music | `POST /v1/music` | Episode-wide instrumental track (3–600s) |

### Audio Mixing (ffmpeg, adaptive timing)

For each clip, audio layers are mixed with ffmpeg:
- **Video**: Veo clip with native audio KEPT (ambient/SFX)
- **Veo audio**: ducked to 40% volume during narration, 60% otherwise
- **Narration**: ElevenLabs TTS at 100% volume, 500ms delay
- **Music**: ElevenLabs instrumental at 20% volume, ducked under narration

**Adaptive duration handling** (narration drives clip timing):
1. After generating narration, probe actual TTS audio duration with ffprobe
2. If narration + delay fits within clip duration: mix normally
3. If narration slightly exceeds clip (up to 1.2x): speed up narration with `atempo`
4. If narration far exceeds clip (>1.2x): extend video via freeze-frame of last frame

## Pipeline Phases (audio-first ordering)

| Phase | Tool | What It Does |
|-------|------|-------------|
| `audio` | ElevenLabs | Generate narration and music (runs first to probe durations) |
| `images` | NanoBanana Pro | Generate keyframe images for all clips |
| `videos` | Veo 3.1 | Generate ambient/SFX video clips |
| `mix` | ffmpeg | Adaptive audio/video mixing (keep Veo audio + narration + music) |
| `captions` | ffmpeg | Burn animated word-by-word captions into mixed clips |
| `stitch` | ffmpeg | Concatenate captioned clips into final video |
| `publish` | Metricool | Multi-platform publish (Instagram, TikTok, YouTube) |
| `all` | All | Run full pipeline end to end |

## Animated Captions

- **Word-by-word animated captions** burned into every clip — critical for sound-off viewing (85% of social video)
- Generated from narration script with word-level timestamps derived from TTS audio duration
- Style: bold white text, black outline, positioned center-bottom (safe zone above platform UI)
- Format: ASS subtitles rendered via ffmpeg `ass` filter
- Each word highlights individually as it is spoken — karaoke-style timing
- Font: bold sans-serif, sized for mobile readability at 9:16

## Publishing (Metricool)

- Multi-platform scheduling via Metricool API
- Targets: Instagram (Reel), TikTok, YouTube Shorts
- Captions generated per platform
- Scheduling with timezone support

## File Naming

Each episode lives in its own folder: `<topic-slug>/`

```
<topic-slug>/
  01_storyboard.md
  02_image_prompts/
    clip_XX_frame.txt
  03_veo_video_prompts/
    clip_XX.txt
  04_narration_script.txt
  generate.py
  output/
    images/
    videos/
    audio/
      narration/
      music/
    mixed/
```

## Image Prompt Structure

See `templates/image_prompt.txt`. Every image prompt must include:
1. Format line: "Vertical 9:16 cinematic frame."
2. Depth layers: foreground / midground / background (mandatory three layers)
3. Atmosphere: haze, dust, smoke, ash, light quality
4. Period texture: one specific detail anchoring the time and place
5. Background activity: people doing things in the scene
6. Character description and blocking (if character present) — with physical reaction poses
7. Camera/composition: angle, movement, rule of thirds, leading lines
8. Lighting setup: named from the playbook in `cinematography.md`

## Video Prompt Structure

See `templates/video_prompt.txt`. Every video prompt must include:
1. Format + resolution line
2. Camera angle, movement, and shot motivation
3. Visual transition from previous clip
4. Lighting setup from the playbook
5. Depth layers in motion
6. Atmosphere, period texture, and background activity
7. Character description with posture/gesture/expression
8. Explicit "No dialogue. No speech." directive
9. Audio direction: SFX + Ambience only (no dialogue, no music from Veo)
