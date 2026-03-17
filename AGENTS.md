# AGENTS.md

## Learned User Preferences

- Scripts must tell one continuous story with causality and narrative thread, not isolated factoids per clip — narration flows across clip boundaries with mid-sentence splits
- Narration is generated as one continuous ElevenLabs audio file, then overlaid on the final stitched video in a single ffmpeg pass — clip boundaries are visual cuts only, narration flows unbroken
- Scripts should feel like National Geographic / PBS documentaries in tone but with TikTok-first pacing — no listicles, no PBS-slow scene-setting, front-load the punch
- Endings must land on a definitive beat that echoes the hook — weak, unresolved endings are not acceptable
- Hooks must never be questions — always a devastating opening fact that creates a knowledge gap (establishes WHY the topic is interesting), not just a shocking number; the first three words must be the most arresting part, and the hook must be self-contained (a viewer who hears only clip 01 understands the danger)
- Second-person POV ("you") must never disappear in later clips — the viewer stays inside the story throughout; scripts that shift to third person in the payoff are broken
- Use Claude Opus 4.6 (not Sonnet) for all content generation — always with streaming to avoid SDK timeouts
- Do not modify historical episode directories when updating system-wide rules — add override notes in the system prompt for few-shot examples instead
- Run Python commands with `-u` (unbuffered) for real-time progress output during long pipeline scripts
- The user works via plan files — implement them sequentially, do not edit the plan file itself, mark todos as in-progress, and complete all todos in a single session
- The user gives terse, lowercase instructions and expects immediate action without unnecessary clarifying questions
- Always test-generate a script and review quality before committing changes or running full pipeline — the user gate-checks at each stage (generate → review → commit → deploy)

## Learned Workspace Facts

- Project is `survive.history` — an automated YouTube Shorts / TikTok / IG Reels pipeline for historical disaster episodes featuring an animated skeleton character
- Pipeline: `n8n/run_pipeline.py` orchestrates topic selection (Claude) → content generation (Claude Opus) → images (Gemini `gemini-3-pro-image-preview`) → audio (ElevenLabs TTS + music) → video (Veo 3.1) → mix/stitch (ffmpeg) → publish (Metricool); phases run strictly sequentially with no parallelism
- Master system prompt lives at `n8n/system-prompts/generate-episode.txt` — this is the brain of the operation; `lib/ai_writer.py` per-clip chaining logic is dead code never called by production
- Channel config files live in `.channel/`: `channel.md` (series bible), `production.md` (specs), `cinematography.md` (visual guide), `templates/` (prompt templates)
- Episode structure follows the 5-beat narrative arc: Hook (0-4s) / Immersion (4-16s) / Attempt (16-28s) / Catastrophe (28-40s) / Conclusion (40-48s), 8 clips (4+8+4+8+4+4+8+8 = 48s raw, ~45.2s effective after crossfades), 95-105 words stated target (Claude inflates ~25% to 120-130 words, compensated by atempo)
- NanoBanana Pro is actually Google's `gemini-3-pro-image-preview` model via the `google.genai` SDK — use `GEMINI_API_KEY` from `.env`, not the third-party endpoint
- ElevenLabs voice is "Dan" (British documentary narrator, voice ID `BHr135B5EUBtaWheVj8S`), measured pacing ~2.4 words/second (not the earlier 2.3 estimate)
- Veo extension chain requires 720p — 1080p is rejected by the extension API; hard limit of 3 reference images per API call (exceeding causes fallback); ASSET refs break the extend API
- Style is flat 2D cel-shaded animation — photorealistic language (bokeh, film grain, depth of field) and the word "comedy" are banned from prompts and auto-sanitized in `lib/veo.py`
- Four flat-animation character reference PNGs exist in `.channel/reference_images/` (front/side/threequarter/back) — the original photorealistic `skeleton_front_neutral.jpg` is the seed source only
- Video format is 9:16 portrait (1080x1920) for short-form platforms
- Cross-clip transitions use ffmpeg xfade (0.3s default, 0.5s hook boundary, 1.5s dip-to-black at end) in `lib/mixer.py`; transitions consume ~2.3s total, and `validate_narration_timing()` applies atempo speedup (capped at 1.25x) when narration overflows the effective video window
