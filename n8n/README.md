# You Wouldn't Wanna Be — Automated Pipeline

End-to-end automation: autonomous topic selection → content generation → image/video/audio creation → publishing to Instagram Reels + YouTube Shorts every 6 hours.

## Prerequisites

- Python 3.10+
- `ffmpeg` and `ffprobe` installed and on PATH
- `gh` CLI installed and authenticated (for GitHub Releases)
- All Python dependencies: `pip install -r requirements.txt`

## Required API Keys

Create a `.env` file in the repo root with:

```env
# AI Content Generation
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Image Generation (NanoBanana Pro)
NANOBANANA_API_KEY=...
NANOBANANA_MODEL=nano-banana-pro

# Video Generation (Veo 3.1 via Gemini)
GEMINI_API_KEY=...

# Narrator TTS + Music (ElevenLabs)
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...

# Publishing (Metricool)
METRICOOL_PUBLISH_ENABLED=true
METRICOOL_USER_TOKEN=...
METRICOOL_USER_ID=...
METRICOOL_BLOG_ID=...
METRICOOL_TARGET_PLATFORMS=instagram,youtube
```

## CLI Usage

### Autonomous mode (Claude picks a topic)

```bash
python n8n/run_pipeline.py
```

### Manual topic

```bash
python n8n/run_pipeline.py "The Great Fire of London, 1666"
```

### With publishing

```bash
python n8n/run_pipeline.py --publish
```

### Skip phases (for resuming after failures)

```bash
python n8n/run_pipeline.py --skip-audio --skip-images   # resume from videos
python n8n/run_pipeline.py --skip-audio --skip-images --skip-videos  # just mix/stitch
```

## n8n Workflow Setup

### Import the workflow

1. Open your n8n instance
2. Go to Workflows → Import from File
3. Import `n8n/survive-history-workflow.json`
4. Open the **Set Environment** node and fill in ALL API keys
5. Set `REPO_DIR` to the absolute path of this repository on the n8n host
6. (Optional) Set `DISCORD_WEBHOOK_URL` for success/failure notifications
7. Activate the workflow

### Rebuild the workflow JSON

If you modify `_build_workflow.py`:

```bash
python n8n/_build_workflow.py
```

### Schedule

The workflow runs every 6 hours by default. Each run:
1. Claude picks a new historical disaster (avoids duplicates)
2. Claude generates all prompts (image, video, narration)
3. ElevenLabs generates narrator TTS + background music
4. NanoBanana Pro generates keyframe images with skeleton reference
5. Veo 3.1 generates video clips with ambient audio
6. ffmpeg mixes audio layers, burns word-by-word captions, stitches final video
7. Uploads to GitHub Releases
8. Publishes to Instagram Reels + YouTube Shorts via Metricool

## Pipeline Phases

| Phase | Tool | Duration | What It Does |
|-------|------|----------|-------------|
| 0 | Claude | ~5s | Pick new historical disaster topic |
| 1 | Claude | ~30s | Generate storyboard, image/video prompts, narration |
| 2 | ElevenLabs | ~2min | TTS narration (10 clips) + background music |
| 3 | NanoBanana | ~10min | Keyframe images (10 clips with skeleton reference) |
| 4 | Veo 3.1 | ~20min | Video clips (10 clips with ambient/SFX audio) |
| 5 | ffmpeg | ~3min | Audio mix + captions + stitch |
| 6 | gh + Metricool | ~1min | GitHub Release + social publish |

Total: ~35-45 minutes per episode.

## Output Structure

Each episode creates a directory:

```
<episode-slug>/
  01_storyboard.md
  02_image_prompts/clip_XX_frame.txt
  03_veo_video_prompts/clip_XX.txt
  04_narration_script.txt
  output/
    images/clip_XX_frame.png
    videos/clip_XX.mp4
    audio/narration/narration_XX.mp3
    audio/music/background_music.mp3
    mixed/clip_XX.mp4 + final_<slug>.mp4
    captions/clip_XX.ass
    captioned/clip_XX.mp4
```

## Troubleshooting

**Safety filter blocks**: Veo/NanoBanana may block prompts with violent content. The pipeline retries up to 3 times. If persistent, the topic may need manual adjustment.

**Missing reference image**: Ensure `skeleton_front_neutral.jpg` exists at `.channel/reference_images/`.

**ffmpeg errors**: Check that ffmpeg supports AAC encoding and the ASS subtitle filter.

**Metricool publish fails**: Verify credentials and that the video URL from GitHub Releases is publicly accessible.
