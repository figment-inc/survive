# AGENTS.md

## Learned User Preferences

- Scripts must tell one continuous story with causality and narrative thread — narration is generated as one continuous ElevenLabs audio file overlaid on the final stitched video; clip boundaries are visual cuts only, narration flows unbroken with mid-sentence splits
- Scripts must prioritize emotional storytelling over fact delivery — "story first, not encyclopedia"; a script that teaches facts but creates no feeling has failed; facts should be felt through the viewer's body, not read from a textbook; sensory texture (heat, dust, shaking, cold) and human moments (hope, decision, loss) are mandatory
- Scripts should feel like National Geographic / PBS documentaries in tone but with TikTok-first pacing — no listicles, no PBS-slow scene-setting, front-load the punch
- Endings must land on a definitive beat that echoes the hook — weak, unresolved endings are not acceptable
- Hooks must never be questions — always a single, calmly stated impossibility that creates a "wait, what?" reaction; no prescribed formula or fragment template — the hook must contain a self-contained paradox, absurdity, or cruel irony that demands resolution without needing clip 02; 8-18 words total
- Visual consistency requires a global style reference image (`style_reference.png`) always passed as the first visual input to both Gemini image and Veo video generation — separate from and in addition to character angle references
- Second-person POV ("you") must never disappear in later clips — "you" must be the SUBJECT of at least one sentence in every catastrophe/conclusion clip; the disaster happens TO you, not around you while you watch statistics
- Use Claude Opus 4.6 (not Sonnet) for all content generation — always with streaming to avoid SDK timeouts
- Do not modify historical episode directories when updating system-wide rules — add override notes in the system prompt for few-shot examples instead
- Run Python commands with `-u` (unbuffered) for real-time progress output during long pipeline scripts
- The user works via plan files — implement them sequentially, do not edit the plan file itself, mark todos as in-progress, and complete all todos in a single session
- The user gives terse, lowercase instructions and expects immediate action without unnecessary clarifying questions — common one-shot commands include "push to main, run pipeline, publish to metricool" as a single workflow
- Always test-generate a script and review quality before committing changes or running full pipeline — the user gate-checks at each stage (generate → review → commit → deploy)

## Learned Workspace Facts

- Project is `survive.history` — an automated YouTube Shorts / TikTok / IG Reels pipeline for historical disaster episodes featuring an animated skeleton character
- Pipeline: `n8n/run_pipeline.py` orchestrates topic selection (Claude) → content generation (Claude Opus) → images (Gemini `gemini-3-pro-image-preview`) → audio (ElevenLabs TTS + music) → video (Veo 3.1) → mix/stitch (ffmpeg) → captions (Remotion) → publish (Metricool); phases run strictly sequentially with no parallelism
- Master system prompt lives at `n8n/system-prompts/generate-episode.txt` — this is the brain of the operation; `lib/ai_writer.py` per-clip chaining logic is dead code never called by production
- Channel config files live in `.channel/`: `channel.md` (series bible), `production.md` (specs), `cinematography.md` (visual guide), `templates/` (prompt templates)
- Episode structure follows the 5-beat narrative arc: Hook (0-4s) / Immersion (4-16s) / Attempt (16-28s) / Catastrophe (28-40s) / Conclusion (40-48s), 8 clips (4+8+4+8+4+4+8+8 = 48s raw, ~45.2s effective after crossfades), 95-105 words stated target (Claude inflates ~25% to 120-130 words, compensated by atempo)
- NanoBanana Pro is actually Google's `gemini-3-pro-image-preview` model via the `google.genai` SDK — use `GEMINI_API_KEY` from `.env`, not the third-party endpoint
- ElevenLabs voice is "Dan" (British documentary narrator, voice ID `BHr135B5EUBtaWheVj8S`), measured pacing ~2.4 words/second (not the earlier 2.3 estimate)
- Veo extension chain requires 720p — 1080p is rejected by the extension API; hard limit of 3 reference images per API call (exceeding causes fallback); ASSET refs break the extend API
- Style is flat 2D cel-shaded animation — photorealistic language (bokeh, film grain, depth of field) and the word "comedy" are banned from prompts and auto-sanitized in `lib/veo.py`; four character reference PNGs (front/side/threequarter/back) plus a global `style_reference.png` (converted from AVIF) are passed to all generation calls, with the style ref always first
- Video format is 9:16 portrait (1080x1920) for short-form platforms
- Cross-clip transitions use ffmpeg xfade (0.3s default, 0.5s hook boundary, 1.5s dip-to-black at end) in `lib/mixer.py`; transitions consume ~2.3s total, and `validate_narration_timing()` applies atempo speedup (capped at 1.25x) when narration overflows the effective video window
- Karaoke captions pipeline (`lib/captions.py`) uses Remotion + Whisper: renders transparent ProRes overlay then composites via ffmpeg; caption position y=72% (lower-third), font auto-scaled to video width, max 3 words/segment; wired as Phase 4b after stitching
- Visual QA pipeline (`lib/visual_qa.py`) extracts multi-point frames from each clip and scores drift severity; clips above threshold are auto-regenerated with style anchors before stitching
- A GitHub Actions cronjob runs the pipeline autonomously on a schedule; code must be pushed to `main` for cronjob updates to take effect
- Metricool publishing supports scheduled posts at specific future times via `desired_publish_at` ISO datetime parameter; the pipeline's `--schedule` flag passes this through
