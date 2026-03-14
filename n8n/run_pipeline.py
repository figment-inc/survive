#!/usr/bin/env python3
"""
You Wouldn't Wanna Be — Automated Episode Pipeline

End-to-end from autonomous topic selection to published YouTube Short + Instagram Reel.
Family Guy animation style with split audio pipeline: Veo 3.1 silent video + ElevenLabs British documentary narration/music.

Phases:
  0. Topic generation (Claude — picks history's worst moments, avoids duplicates)
  1. Episode content generation (Claude — image prompts, video prompts, dialogue script)
  1b. Write prompts to disk
  2. Image generation (NanoBanana Pro — keyframe images with skeleton reference, Family Guy style)
  2b. Audio generation (ElevenLabs — Dan British documentary narrator voice + cinematic underscore music)
  3. Video generation (Veo 3.1 — silent clips with SFX/ambience only, NO speech)
  3b. Per-clip audio mixing (ffmpeg — Veo SFX 40% + narration 100% + music 20%)
  4. Stitch + LUFS normalize (ffmpeg — concat mixed clips + loudnorm to -14 LUFS)
  5. Publish (GitHub Release upload + Metricool API → IG Reel + YT Short + TikTok)

Usage:
  python n8n/run_pipeline.py                          # autonomous topic + local only
  python n8n/run_pipeline.py "The Great Fire of London, 1666"  # manual topic
  python n8n/run_pipeline.py --publish                # autonomous + publish
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
CHANNEL_DIR = REPO_DIR / ".channel"
SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "system-prompts" / "generate-episode.txt"

sys.path.insert(0, str(REPO_DIR))


def ts():
    return datetime.now().strftime("%H:%M:%S")


def phase_banner(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def load_env_key(name):
    if os.environ.get(name):
        return os.environ[name]
    env_path = REPO_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def get_existing_slugs():
    """Return set of episode slugs already in the repo root."""
    return {
        d.name for d in REPO_DIR.iterdir()
        if d.is_dir()
        and not d.name.startswith((".", "_"))
        and d.name not in ("lib", "n8n", "output", "__pycache__")
        and (d / "01_storyboard.md").exists()
    }


# ── Phase 0: Autonomous topic generation ──


def generate_topic():
    phase_banner("PHASE 0: TOPIC GENERATION (Claude)")

    import anthropic
    client = anthropic.Anthropic(api_key=load_env_key("ANTHROPIC_API_KEY"))

    existing = sorted(get_existing_slugs())
    existing_list = "\n".join(f"- {s}" for s in existing) if existing else "(none yet)"

    system = (
        "You generate episode topics for 'You Wouldn't Wanna Be', a dark-comedy short-form "
        "video series where a hapless skeleton gets teleported into history's worst moments.\n\n"
        "Pick ONE specific historical disaster or catastrophe. Prioritize events that:\n"
        "- Most people have HEARD OF but don't know the full story\n"
        "- Are taught in schools or referenced in popular culture (movies, TV, books)\n"
        "- Have high search interest on YouTube and TikTok\n"
        "- Have a specific, dramatic moment that can anchor a 45-second video\n\n"
        "Good examples: the Titanic sinking, Pompeii, Chernobyl, the Black Death, "
        "the Hindenburg, the Great Fire of London, the sinking of the Lusitania, "
        "the Triangle Shirtwaist fire, the Challenger disaster, Hiroshima, the San "
        "Francisco earthquake, the Halifax explosion, the Donner Party, the "
        "Spanish Flu, the Dust Bowl, the eruption of Mount St. Helens.\n\n"
        "The event must be:\n"
        "- A real, well-documented historical event with a specific date/year\n"
        "- Visually spectacular and cinematically compelling\n"
        "- NOT primarily about explicit torture or sexual content\n"
        "- Safe for AI image/video generation (avoid content filter triggers)\n"
        "- Different from all previously produced episodes listed below\n\n"
        "Return ONLY the topic as a single line, like: "
        "'The eruption of Mount Vesuvius, Pompeii, 79 AD'\n\n"
        f"## ALREADY PRODUCED (do NOT repeat):\n{existing_list}"
    )

    print(f"  [{ts()}] Asking Claude for a new topic...")
    print(f"  [{ts()}] Existing episodes: {len(existing)}")

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        temperature=1.0,
        system=system,
        messages=[{"role": "user", "content": "Pick a new episode topic."}],
    )

    topic = response.content[0].text.strip().strip('"').strip("'")
    print(f"  [{ts()}] Selected topic: {topic}")
    return topic


# ── Phase 1: Generate episode content ──


def load_example_prompts():
    """Load one working image + video prompt as few-shot examples for Claude."""
    examples = ""
    for ep_slug in ["chernobyl-1986", "titanic-1912", "pompeii-79"]:
        ep_dir = REPO_DIR / ep_slug
        img_example = ep_dir / "02_image_prompts" / "clip_01_frame.txt"
        vid_example = ep_dir / "03_veo_video_prompts" / "clip_01.txt"
        if img_example.exists():
            examples += "\n\n--- EXAMPLE IMAGE PROMPT (clip 01 from a working episode) ---\n"
            examples += img_example.read_text().strip()
        if vid_example.exists():
            examples += "\n\n--- EXAMPLE VIDEO PROMPT (clip 01 from a working episode) ---\n"
            examples += vid_example.read_text().strip()
        if examples:
            break
    return examples


def generate_episode_content(topic):
    phase_banner("PHASE 1: GENERATE EPISODE CONTENT (Claude)")

    import anthropic
    client = anthropic.Anthropic(api_key=load_env_key("ANTHROPIC_API_KEY"))
    system_prompt = SYSTEM_PROMPT_PATH.read_text()

    examples = load_example_prompts()
    if examples:
        system_prompt += "\n\n## FEW-SHOT EXAMPLES FROM WORKING EPISODES\n"
        system_prompt += (
            "Your prompts MUST match this level of detail and length. "
            "Short/generic prompts will be blocked by safety filters or produce poor results. "
            "Every image prompt must be 15-25 lines with explicit scene composition, "
            "character blocking, foreground/midground/background layers, "
            "atmospheric details, period textures, and exclusion lines. "
            "Every video prompt must be 25-35 lines with camera behavior, depth layers, "
            "ambient audio direction, and physical performance descriptions."
        )
        system_prompt += examples

    model = load_env_key("ANTHROPIC_MODEL") or "claude-opus-4-6"

    print(f"  [{ts()}] Sending topic to Claude: {topic}")
    print(f"  [{ts()}] Model: {model}")

    max_retries = 2
    for attempt in range(max_retries + 1):
        collected = []
        with client.messages.stream(
            model=model,
            max_tokens=32000,
            temperature=1.0,
            system=system_prompt,
            messages=[{"role": "user", "content": topic}],
        ) as stream:
            for text in stream.text_stream:
                collected.append(text)
        response = stream.get_final_message()

        stop_reason = response.stop_reason
        raw = "".join(collected).strip()

        if stop_reason == "max_tokens":
            print(f"  [{ts()}] WARNING: Response truncated (max_tokens). "
                  f"Attempt {attempt + 1}/{max_retries + 1}.")
            if attempt < max_retries:
                print(f"  [{ts()}] Retrying with shorter prompt expectations...")
                continue
            print(f"  [{ts()}] Attempting to salvage truncated JSON...")

        break

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()

    try:
        episode = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [{ts()}] JSON parse error: {e}")
        print(f"  [{ts()}] Attempting truncated JSON repair...")
        episode = _repair_truncated_json(raw)

    print(f"  [{ts()}] Generated episode: {episode['title']}")
    print(f"  [{ts()}] Slug: {episode['episode_slug']}")
    print(f"  [{ts()}] Image prompts: {len(episode['image_prompts'])}")
    print(f"  [{ts()}] Video prompts: {len(episode['video_prompts'])}")
    return episode


def _repair_truncated_json(raw):
    """Attempt to repair JSON truncated mid-generation by closing open structures."""
    import re

    if raw.endswith(","):
        raw = raw[:-1]

    open_braces = raw.count("{") - raw.count("}")
    open_brackets = raw.count("[") - raw.count("]")
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string

    if in_string:
        raw += '"'

    if raw.rstrip().endswith(","):
        raw = raw.rstrip()[:-1]

    raw += "]" * max(0, open_brackets)
    raw += "}" * max(0, open_braces)

    return json.loads(raw)


# ── Phase 1b: Write prompts to disk ──


def write_episode_files(episode):
    slug = episode["episode_slug"]
    ep_dir = REPO_DIR / slug
    img_dir = ep_dir / "02_image_prompts"
    vid_dir = ep_dir / "03_veo_video_prompts"
    out_dirs = [
        ep_dir / "output" / d
        for d in ["images", "videos", "audio/narration", "mixed_clips", "mixed"]
    ]

    for d in [img_dir, vid_dir] + out_dirs:
        d.mkdir(parents=True, exist_ok=True)

    for i, prompt in enumerate(episode["image_prompts"]):
        clip_id = f"{i + 1:02d}"
        (img_dir / f"clip_{clip_id}_frame.txt").write_text(prompt)

    for i, prompt in enumerate(episode["video_prompts"]):
        clip_id = f"{i + 1:02d}"
        (vid_dir / f"clip_{clip_id}.txt").write_text(prompt)

    if episode.get("dialogue_script"):
        (ep_dir / "04_dialogue_script.txt").write_text(episode["dialogue_script"])

    storyboard = (
        f"# {episode['title']}\n\n"
        f"**Slug**: `{slug}`\n"
        f"**Setting**: {episode.get('setting', '')}\n"
        f"**Hook**: {episode.get('hook', '')}\n\n"
        f"## Clips\n\n"
    )
    for clip in episode.get("clips", []):
        storyboard += (
            f"### Clip {clip['id']}\n"
            f"- **Duration**: {clip['duration']}s\n"
            f"- **Type**: {clip['type']}\n"
            f"- **Character**: {'Yes' if clip.get('has_character') else 'No'}\n"
            f"- **Resolution**: {clip.get('resolution', '1080p')}\n\n"
        )
    (ep_dir / "01_storyboard.md").write_text(storyboard)

    print(f"  [{ts()}] Written episode files to: {ep_dir}")
    return ep_dir, slug


# ── Phase 2: Image generation (NanoBanana Pro) ──


def run_images_phase(episode, ep_dir):
    phase_banner("PHASE 2: IMAGE GENERATION (NanoBanana Pro)")

    from lib.nanobanana import generate_image

    api_key = load_env_key("NANOBANANA_API_KEY") or load_env_key("GEMINI_API_KEY")
    model = load_env_key("NANOBANANA_MODEL") or "gemini-3-pro-image-preview"

    if not api_key:
        print(f"  [{ts()}] ERROR: NANOBANANA_API_KEY / GEMINI_API_KEY not found.")
        return False

    ref_dir = CHANNEL_DIR / "reference_images"
    ref_paths = []
    for name in ["skeleton_front_neutral.jpg", "skeleton_front_neutral.png"]:
        path = ref_dir / name
        if path.exists():
            ref_paths.append(path)
            print(f"  [{ts()}] Loaded reference: {name}")
            break

    images_dir = ep_dir / "output" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    episode_style = episode.get("style_description")
    if episode_style:
        print(f"  [{ts()}] Episode style: {episode_style[:80]}...")

    style_anchor_path = None
    clips = episode.get("clips", [])
    for i, prompt in enumerate(episode["image_prompts"]):
        clip_id = f"{i + 1:02d}"
        output_path = images_dir / f"clip_{clip_id}_frame.png"

        if output_path.exists():
            print(f"  [{ts()}] Skipping (exists): {output_path.name}")
            if i == 0 and style_anchor_path is None:
                style_anchor_path = output_path
                print(f"  [{ts()}] Using existing clip 01 as style anchor")
            continue

        has_character = clips[i].get("has_character", True) if i < len(clips) else True
        print(f"\n  --- Clip {clip_id} ---")
        generate_image(
            api_key=api_key,
            model=model,
            prompt=prompt,
            output_path=output_path,
            reference_paths=ref_paths if has_character else None,
            has_character=has_character,
            style_anchor_path=style_anchor_path if i > 0 else None,
            episode_style=episode_style,
        )

        if i == 0 and output_path.exists():
            style_anchor_path = output_path
            print(f"  [{ts()}] Clip 01 set as style anchor for remaining images")

    print(f"  [{ts()}] Images phase complete.")
    return True


# ── Phase 2b: Audio generation (ElevenLabs narration + music) ──


MUSIC_PROMPT = (
    "National Geographic documentary orchestral underscore. Sweeping strings, "
    "warm French horns, gentle piano, and subtle timpani. Reverent and majestic. "
    "Slow building wonder and tension. Evokes vast landscapes and ancient forces. "
    "No vocals. No sudden jumps. No electronic elements."
)


def _parse_narration_lines(episode):
    """Extract per-clip narration text from the dialogue_script field."""
    import re

    script = episode.get("dialogue_script", "")
    clips = episode.get("clips", [])
    lines: dict[str, str] = {}
    current_clip = None

    for line in script.splitlines():
        clip_match = re.match(r"##\s*Clip\s+(\d+)", line)
        if clip_match:
            current_clip = clip_match.group(1).zfill(2)
            lines[current_clip] = ""
            continue
        narr_match = re.match(r"NARRATOR:\s*[\"']?(.+?)[\"']?\s*$", line)
        if narr_match and current_clip:
            existing = lines.get(current_clip, "")
            text = narr_match.group(1)
            lines[current_clip] = f"{existing} {text}".strip() if existing else text

    return lines


def run_audio_phase(episode, ep_dir):
    phase_banner("PHASE 2b: AUDIO GENERATION (ElevenLabs)")

    from lib.elevenlabs import generate_narration, generate_music

    el_key = load_env_key("ELEVENLABS_API_KEY")
    voice_id = load_env_key("ELEVENLABS_VOICE_ID")
    if not el_key or not voice_id:
        print(f"  [{ts()}] ERROR: ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID not found")
        return False

    narr_dir = ep_dir / "output" / "audio" / "narration"
    music_dir = ep_dir / "output" / "audio"
    narr_dir.mkdir(parents=True, exist_ok=True)

    narr_lines = _parse_narration_lines(episode)
    clips = episode.get("clips", [])

    for clip_meta in clips:
        clip_id = clip_meta["id"]
        text = narr_lines.get(clip_id, "")
        if not text:
            print(f"  [{ts()}] WARNING: No narration for clip {clip_id}")
            continue
        output_path = narr_dir / f"clip_{clip_id}.mp3"
        generate_narration(el_key, voice_id, text, output_path)

    music_path = music_dir / "music.mp3"
    generate_music(el_key, MUSIC_PROMPT, music_path, duration_ms=55000)

    print(f"  [{ts()}] Audio phase complete.")
    return True


# ── Phase 3: Video generation (Veo 3.1) ──


def run_videos_phase(episode, ep_dir):
    phase_banner("PHASE 3: VIDEO GENERATION (Veo 3.1)")

    from lib.veo import get_client, load_reference_images, select_refs_for_prompt, generate_video, extract_first_frame

    gemini_key = load_env_key("GEMINI_API_KEY")
    if not gemini_key:
        print(f"  [{ts()}] ERROR: GEMINI_API_KEY not found.")
        return False

    client = get_client(gemini_key)
    all_refs = load_reference_images(CHANNEL_DIR)

    videos_dir = ep_dir / "output" / "videos"
    images_dir = ep_dir / "output" / "images"
    videos_dir.mkdir(parents=True, exist_ok=True)

    episode_style = episode.get("style_description")
    if episode_style:
        print(f"  [{ts()}] Episode style: {episode_style[:80]}...")

    style_anchor_refs = None
    clips = episode.get("clips", [])
    for i, prompt in enumerate(episode["video_prompts"]):
        clip_id = f"{i + 1:02d}"
        output_path = videos_dir / f"clip_{clip_id}.mp4"

        if output_path.exists():
            print(f"  [{ts()}] Skipping (exists): {output_path.name}")
            if i == 0 and style_anchor_refs is None:
                anchor_frame = extract_first_frame(output_path)
                if anchor_frame and anchor_frame.exists():
                    style_anchor_refs = [anchor_frame.read_bytes()]
                    print(f"  [{ts()}] Using existing clip 01 first frame as style anchor")
            continue

        clip_meta = clips[i] if i < len(clips) else {}
        duration = clip_meta.get("duration", 8)
        resolution = clip_meta.get("resolution", "1080p")
        if duration <= 5 and resolution == "1080p":
            resolution = "720p"
        use_reference = clip_meta.get("has_character", True)
        first_frame = images_dir / f"clip_{clip_id}_frame.png"

        ref_images = select_refs_for_prompt(all_refs, prompt) if use_reference else None

        print(f"\n  --- Clip {clip_id} ({duration}s @ {resolution})"
              f"{' +style_anchor' if style_anchor_refs and i > 0 else ''} ---")

        max_safety_retries = 3
        for attempt in range(max_safety_retries):
            success = generate_video(
                client=client,
                prompt=prompt,
                output_path=output_path,
                duration=duration,
                resolution=resolution,
                ref_images=ref_images,
                first_frame_path=first_frame if first_frame.exists() else None,
                use_reference=use_reference,
                style_anchor_refs=style_anchor_refs if i > 0 else None,
                episode_style=episode_style,
            )
            if success:
                break
            if attempt < max_safety_retries - 1:
                print(f"  [{ts()}] Safety retry {attempt + 1}/{max_safety_retries}...")

        if i == 0 and output_path.exists() and style_anchor_refs is None:
            anchor_frame = extract_first_frame(output_path)
            if anchor_frame and anchor_frame.exists():
                style_anchor_refs = [anchor_frame.read_bytes()]
                print(f"  [{ts()}] Clip 01 first frame set as style anchor for remaining clips")

    print(f"  [{ts()}] Videos phase complete.")
    return True


# ── Phase 4: Per-clip audio mixing + Stitch + LUFS normalize ──


def run_mix_phase(episode, ep_dir):
    """Mix narration + music into each Veo clip, then stitch and LUFS normalize."""
    phase_banner("PHASE 3b: PER-CLIP AUDIO MIXING (Veo SFX + Narration + Music)")

    from lib.mixer import mix_clip_audio, probe_audio_duration

    clips = episode.get("clips", [])
    videos_dir = ep_dir / "output" / "videos"
    narr_dir = ep_dir / "output" / "audio" / "narration"
    music_path = ep_dir / "output" / "audio" / "music.mp3"
    mixed_dir = ep_dir / "output" / "mixed_clips"
    mixed_dir.mkdir(parents=True, exist_ok=True)

    music_offset = 0.0

    for clip_meta in clips:
        clip_id = clip_meta["id"]
        duration = clip_meta.get("duration", 8)
        video_path = videos_dir / f"clip_{clip_id}.mp4"
        narration_path = narr_dir / f"clip_{clip_id}.mp3"
        output_path = mixed_dir / f"clip_{clip_id}.mp4"

        narr_dur = probe_audio_duration(narration_path) if narration_path.exists() else 0.0

        mix_clip_audio(
            video_path=video_path,
            output_path=output_path,
            narration_path=narration_path if narration_path.exists() else None,
            music_path=music_path if music_path.exists() else None,
            clip_duration=duration,
            narration_duration=narr_dur,
            music_offset=music_offset,
            music_volume=0.20,
            veo_audio_volume=0.15,
        )
        music_offset += duration

    print(f"  [{ts()}] Mix phase complete.")
    return True


def run_post_phase(episode, ep_dir):
    phase_banner("PHASE 4: STITCH + LUFS NORMALIZE (ffmpeg)")

    from lib.mixer import stitch_clips

    slug = episode["episode_slug"]
    clips = episode.get("clips", [])

    mixed_clips_dir = ep_dir / "output" / "mixed_clips"
    videos_dir = ep_dir / "output" / "videos"
    final_dir = ep_dir / "output" / "mixed"
    final_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  [{ts()}] Stitching final video...")
    clip_paths = []
    for clip_meta in clips:
        clip_id = clip_meta["id"]
        mixed = mixed_clips_dir / f"clip_{clip_id}.mp4"
        raw = videos_dir / f"clip_{clip_id}.mp4"
        if mixed.exists():
            clip_paths.append(mixed)
        elif raw.exists():
            print(f"  WARNING: No mixed clip_{clip_id}.mp4, using raw video")
            clip_paths.append(raw)
        else:
            print(f"  WARNING: Missing clip_{clip_id}.mp4, skipping")

    final_path = final_dir / f"final_{slug}.mp4"
    stitch_clips(clip_paths, final_path)

    return final_path


# ── Phase 4b: Remotion captions ──


def run_captions_phase(final_path, ep_dir):
    phase_banner("PHASE 4b: REMOTION KARAOKE CAPTIONS (Whisper + Remotion)")

    from lib.captions import run_captions_pipeline

    openai_key = load_env_key("OPENAI_API_KEY")
    if not openai_key:
        print(f"  [{ts()}] WARNING: OPENAI_API_KEY not found — skipping captions")
        return final_path

    captioned_path = final_path.with_stem(final_path.stem + "_captioned")
    result = run_captions_pipeline(
        video_path=final_path,
        output_path=captioned_path,
        openai_api_key=openai_key,
    )

    if result and result.exists():
        print(f"  [{ts()}] Captioned video ready: {result}")
        return result

    print(f"  [{ts()}] Captions failed — using uncaptioned video")
    return final_path


# ── Phase 5: Publish ──


def create_github_release(slug, title, final_path):
    """Create a GitHub Release and upload the final MP4. Return the asset download URL."""
    phase_banner("PHASE 5a: GITHUB RELEASE")

    tag = f"episode-{slug}"
    print(f"  [{ts()}] Creating release: {tag}")

    result = subprocess.run(
        [
            "gh", "release", "create", tag,
            str(final_path),
            "--title", title,
            "--notes", f"Automated episode: {title}\nSlug: {slug}",
        ],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(f"  [{ts()}] gh release create failed: {result.stderr}")
        return None

    release_url = result.stdout.strip()
    print(f"  [{ts()}] Release created: {release_url}")

    view_result = subprocess.run(
        ["gh", "release", "view", tag, "--json", "assets"],
        capture_output=True, text=True,
    )

    if view_result.returncode != 0:
        print(f"  [{ts()}] Failed to get asset URL: {view_result.stderr}")
        return None

    assets = json.loads(view_result.stdout).get("assets", [])
    for asset in assets:
        if asset["name"].endswith(".mp4"):
            download_url = asset["url"]
            print(f"  [{ts()}] Asset URL: {download_url}")
            return download_url

    print(f"  [{ts()}] No MP4 asset found in release")
    return None


def publish_to_metricool_with_upload(episode, final_path, asset_url=None):
    """Upload video to Metricool S3 then publish to YouTube Shorts + Instagram Reels + TikTok."""
    phase_banner("PHASE 5b: METRICOOL PUBLISH")

    from lib.config import load_settings
    from lib.metricool import publish_to_metricool, upload_media_file

    settings = load_settings()

    title = episode.get("title", "You Wouldn't Wanna Be")
    hook = episode.get("hook", "")

    caption = (
        f"{title}\n\n"
        f"{hook}\n\n"
        f"#YouWouldntWannaBe #History #Shorts #HistoryFacts "
        f"#LearnOnTikTok #HistoryTok #DarkHistory #Education"
    )

    print(f"  [{ts()}] Uploading {final_path.name} ({final_path.stat().st_size / (1024*1024):.1f} MB) to Metricool S3...")
    try:
        media_url = upload_media_file(settings, str(final_path))
        print(f"  [{ts()}] S3 upload complete: {media_url[:80]}")
    except Exception as e:
        print(f"  [{ts()}] S3 upload failed: {e}")
        if asset_url:
            print(f"  [{ts()}] Falling back to GitHub Release URL")
            media_url = asset_url
        else:
            print(f"  [{ts()}] No fallback URL available, cannot publish")
            sys.exit(1)

    result = publish_to_metricool(
        settings=settings,
        media_url=media_url,
        title=title[:100],
        caption=caption,
        caption_instagram=caption,
        caption_youtube=caption,
    )

    print(f"  [{ts()}] Publish status: {result.status}")
    if result.error_message:
        print(f"  [{ts()}] Error: {result.error_message}")
    if result.status != "published":
        sys.exit(1)
    return True


def validate_word_counts(episode):
    """Check that narration word counts fit within clip durations.

    ElevenLabs TTS with the Dan voice delivers speech at ~2.3 words/sec
    (measured from actual output). If narration exceeds the clip duration
    budget, audio will be trimmed during mixing.
    """
    import re

    WORDS_PER_SEC = 2.3
    WORD_CEILING = 75
    NARRATION_DELAY = 0.5
    NARRATION_BUFFER = 0.3
    clips = episode.get("clips", [])
    script = episode.get("dialogue_script", "")

    clip_lines: dict[str, str] = {}
    current_clip = None
    for line in script.splitlines():
        clip_match = re.match(r"##\s*Clip\s+(\d+)", line)
        if clip_match:
            current_clip = clip_match.group(1).zfill(2)
            clip_lines[current_clip] = ""
            continue
        narr_match = re.match(r"NARRATOR:\s*[\"']?(.+?)[\"']?\s*$", line)
        if narr_match and current_clip:
            clip_lines[current_clip] = narr_match.group(1)

    total_words = 0
    any_over = False
    for clip_meta in clips:
        clip_id = clip_meta["id"]
        duration = clip_meta.get("duration", 8)
        max_words = int((duration - NARRATION_DELAY - NARRATION_BUFFER) * WORDS_PER_SEC)
        narration = clip_lines.get(clip_id, "")
        word_count = len(narration.split()) if narration else 0
        total_words += word_count
        status = "OK" if word_count <= max_words else "OVER"
        if status == "OVER":
            any_over = True
        print(f"  Clip {clip_id} ({duration}s): {word_count}/{max_words} words [{status}]")

    print(f"  Total narration: {total_words} words")
    narration_seconds = total_words / WORDS_PER_SEC
    print(f"  Estimated narration duration: {narration_seconds:.1f}s (at {WORDS_PER_SEC} wps)")
    if total_words > WORD_CEILING:
        print(f"  [{ts()}] WARNING: Total {total_words} words exceeds {WORD_CEILING}-word ceiling "
              f"(~{narration_seconds:.0f}s) — narration may be trimmed during mixing")
    if any_over:
        print(f"  [{ts()}] WARNING: Some clips exceed per-clip word budget — audio may be trimmed")


# ── Main ──


def main():
    parser = argparse.ArgumentParser(description="You Wouldn't Wanna Be — Automated Pipeline")
    parser.add_argument("topic", nargs="*", help="Episode topic (omit for autonomous selection)")
    parser.add_argument("--publish", action="store_true", help="Publish to YouTube + Instagram via Metricool")
    parser.add_argument("--skip-images", action="store_true", help="Skip image generation phase")
    parser.add_argument("--skip-videos", action="store_true", help="Skip video generation phase")
    parser.add_argument("--skip-post", action="store_true", help="Skip stitch phase")
    parser.add_argument("--skip-audio", action="store_true", help="Skip ElevenLabs audio generation phase")
    parser.add_argument("--skip-mix", action="store_true", help="Skip per-clip audio mixing phase")
    args = parser.parse_args()

    topic = " ".join(args.topic) if args.topic else None

    print(f"\n{'=' * 60}")
    print(f"  You Wouldn't Wanna Be — Automated Pipeline")
    print(f"  Mode: {'Autonomous' if not topic else 'Manual'}")
    print(f"  Publish: {'YES' if args.publish else 'no (local only)'}")
    print(f"{'=' * 60}")

    anthropic_key = load_env_key("ANTHROPIC_API_KEY")
    if not anthropic_key:
        print("  ERROR: ANTHROPIC_API_KEY not found")
        sys.exit(1)

    if not topic:
        topic = generate_topic()

    episode = generate_episode_content(topic)
    validate_word_counts(episode)
    ep_dir, slug = write_episode_files(episode)

    if not args.skip_images:
        run_images_phase(episode, ep_dir)

    if not args.skip_audio:
        run_audio_phase(episode, ep_dir)

    if not args.skip_videos:
        run_videos_phase(episode, ep_dir)

    if not args.skip_mix:
        run_mix_phase(episode, ep_dir)

    final_path = None
    if not args.skip_post:
        final_path = run_post_phase(episode, ep_dir)

    if final_path is None:
        final_path = ep_dir / "output" / "mixed" / f"final_{slug}.mp4"

    phase_banner("GENERATION COMPLETE")
    if final_path.exists():
        size_mb = final_path.stat().st_size / (1024 * 1024)
        print(f"  Final video: {final_path}")
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print(f"  WARNING: Final video not found at {final_path}")
        if args.publish:
            print(f"  Cannot publish without final video.")
            sys.exit(1)

    images = list((ep_dir / "output" / "images").glob("*.png"))
    videos = list((ep_dir / "output" / "videos").glob("*.mp4"))
    print(f"  Images: {len(images)}")
    print(f"  Videos: {len(videos)}")

    if args.publish and final_path.exists():
        asset_url = create_github_release(slug, episode["title"], final_path)
        publish_to_metricool_with_upload(episode, final_path, asset_url)

    phase_banner("ALL DONE")
    print(f"  Episode: {episode['title']}")
    print(f"  Slug: {slug}")


if __name__ == "__main__":
    main()
