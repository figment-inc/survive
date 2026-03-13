#!/usr/bin/env python3
"""
You Wouldn't Wanna Be — Automated Episode Pipeline

End-to-end from autonomous topic selection to published YouTube Short + Instagram Reel.

Phases:
  0. Topic generation (Claude — picks history's worst moments, avoids duplicates)
  1. Episode content generation (Claude — image prompts, video prompts, narration)
  1b. Write prompts to disk
  2. Audio generation (ElevenLabs — narration TTS + background music, runs FIRST)
  3. Image generation (NanoBanana Pro — keyframe images with skeleton reference)
  4. Video generation (Veo 3.1 — ambient/SFX clips with reference images)
  5. Mix + Captions + Stitch (ffmpeg — adaptive audio mixing, word-by-word captions, concat)
  6. Publish (GitHub Release upload + Metricool API → IG Reel + YT Short)

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
from dataclasses import dataclass
from datetime import datetime, timezone
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
        "Pick ONE specific, visually dramatic historical disaster/catastrophe that would make "
        "a great 60-second short. The event must be:\n"
        "- A real, well-documented historical event with a specific date/year\n"
        "- The WORST possible time and place to be alive — plagues, disasters, sieges, "
        "eruptions, sinkings, collapses, famines, nuclear incidents\n"
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

    model = load_env_key("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514"
    gen_model = "claude-sonnet-4-20250514"

    print(f"  [{ts()}] Sending topic to Claude: {topic}")
    print(f"  [{ts()}] Model: {gen_model}")

    max_retries = 2
    for attempt in range(max_retries + 1):
        response = client.messages.create(
            model=gen_model,
            max_tokens=16000,
            temperature=1.0,
            system=system_prompt,
            messages=[{"role": "user", "content": topic}],
        )

        stop_reason = response.stop_reason
        raw = response.content[0].text.strip()

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
        for d in ["images", "videos", "audio/narration", "audio/music", "mixed", "captions", "captioned"]
    ]

    for d in [img_dir, vid_dir] + out_dirs:
        d.mkdir(parents=True, exist_ok=True)

    for i, prompt in enumerate(episode["image_prompts"]):
        clip_id = f"{i + 1:02d}"
        (img_dir / f"clip_{clip_id}_frame.txt").write_text(prompt)

    for i, prompt in enumerate(episode["video_prompts"]):
        clip_id = f"{i + 1:02d}"
        (vid_dir / f"clip_{clip_id}.txt").write_text(prompt)

    if episode.get("narration_script"):
        (ep_dir / "04_narration_script.txt").write_text(episode["narration_script"])

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


# ── Phase 2: Audio generation (ElevenLabs — runs FIRST) ──


def run_audio_phase(episode, ep_dir):
    phase_banner("PHASE 2: AUDIO GENERATION (ElevenLabs)")

    from lib.elevenlabs import generate_narration, generate_music

    api_key = load_env_key("ELEVENLABS_API_KEY")
    voice_id = load_env_key("ELEVENLABS_VOICE_ID")

    if not api_key:
        print(f"  [{ts()}] ERROR: ELEVENLABS_API_KEY not found.")
        return False
    if not voice_id:
        print(f"  [{ts()}] ERROR: ELEVENLABS_VOICE_ID not set.")
        return False

    narr_dir = ep_dir / "output" / "audio" / "narration"
    music_dir = ep_dir / "output" / "audio" / "music"
    narr_dir.mkdir(parents=True, exist_ok=True)
    music_dir.mkdir(parents=True, exist_ok=True)

    narration_lines = episode.get("narration_lines", {})
    for clip_id, text in narration_lines.items():
        narr_path = narr_dir / f"narration_{clip_id}.mp3"
        generate_narration(api_key, voice_id, text, narr_path)

    music_prompt = episode.get("music_prompt", (
        "Dark cinematic underscore. Ominous low strings, building tension, "
        "orchestral intensity, resolving into melancholy. No vocals. Instrumental only."
    ))
    music_path = music_dir / "background_music.mp3"
    generate_music(api_key, music_prompt, music_path, duration_ms=75000)

    print(f"  [{ts()}] Audio phase complete.")
    return True


# ── Phase 3: Image generation (NanoBanana Pro) ──


def run_images_phase(episode, ep_dir):
    phase_banner("PHASE 3: IMAGE GENERATION (NanoBanana Pro)")

    from lib.nanobanana import generate_image

    api_key = load_env_key("NANOBANANA_API_KEY")
    model = load_env_key("NANOBANANA_MODEL") or "nano-banana-pro"

    if not api_key:
        print(f"  [{ts()}] ERROR: NANOBANANA_API_KEY not found.")
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

    clips = episode.get("clips", [])
    for i, prompt in enumerate(episode["image_prompts"]):
        clip_id = f"{i + 1:02d}"
        output_path = images_dir / f"clip_{clip_id}_frame.png"

        if output_path.exists():
            print(f"  [{ts()}] Skipping (exists): {output_path.name}")
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
        )

    print(f"  [{ts()}] Images phase complete.")
    return True


# ── Phase 4: Video generation (Veo 3.1) ──


def run_videos_phase(episode, ep_dir):
    phase_banner("PHASE 4: VIDEO GENERATION (Veo 3.1)")

    from lib.veo import get_client, load_reference_images, generate_video

    gemini_key = load_env_key("GEMINI_API_KEY")
    if not gemini_key:
        print(f"  [{ts()}] ERROR: GEMINI_API_KEY not found.")
        return False

    client = get_client(gemini_key)
    ref_images = load_reference_images(CHANNEL_DIR)

    videos_dir = ep_dir / "output" / "videos"
    images_dir = ep_dir / "output" / "images"
    videos_dir.mkdir(parents=True, exist_ok=True)

    clips = episode.get("clips", [])
    for i, prompt in enumerate(episode["video_prompts"]):
        clip_id = f"{i + 1:02d}"
        output_path = videos_dir / f"clip_{clip_id}.mp4"

        if output_path.exists():
            print(f"  [{ts()}] Skipping (exists): {output_path.name}")
            continue

        clip_meta = clips[i] if i < len(clips) else {}
        duration = clip_meta.get("duration", 8)
        resolution = clip_meta.get("resolution", "1080p")
        if duration <= 5 and resolution == "1080p":
            resolution = "720p"
        use_reference = clip_meta.get("has_character", True)
        first_frame = images_dir / f"clip_{clip_id}_frame.png"

        print(f"\n  --- Clip {clip_id} ({duration}s @ {resolution}) ---")

        max_safety_retries = 3
        for attempt in range(max_safety_retries):
            success = generate_video(
                client=client,
                prompt=prompt,
                output_path=output_path,
                duration=duration,
                resolution=resolution,
                ref_images=ref_images if use_reference else None,
                first_frame_path=first_frame if first_frame.exists() else None,
                use_reference=use_reference,
            )
            if success:
                break
            if attempt < max_safety_retries - 1:
                print(f"  [{ts()}] Safety retry {attempt + 1}/{max_safety_retries}...")

    print(f"  [{ts()}] Videos phase complete.")
    return True


# ── Phase 5: Mix + Captions + Stitch ──


def run_post_phase(episode, ep_dir):
    phase_banner("PHASE 5: MIX + CAPTIONS + STITCH (ffmpeg)")

    from lib.mixer import (
        mix_clip_audio, probe_audio_duration, generate_word_captions,
        burn_captions, stitch_clips, NARRATION_DELAY,
    )

    slug = episode["episode_slug"]
    clips = episode.get("clips", [])
    narration_lines = episode.get("narration_lines", {})

    videos_dir = ep_dir / "output" / "videos"
    narr_dir = ep_dir / "output" / "audio" / "narration"
    music_dir = ep_dir / "output" / "audio" / "music"
    mixed_dir = ep_dir / "output" / "mixed"
    captions_dir = ep_dir / "output" / "captions"
    captioned_dir = ep_dir / "output" / "captioned"

    for d in [mixed_dir, captions_dir, captioned_dir]:
        d.mkdir(parents=True, exist_ok=True)

    music_path = music_dir / "background_music.mp3"

    narr_durations = {}
    for clip_id in narration_lines:
        narr_path = narr_dir / f"narration_{clip_id}.mp3"
        if narr_path.exists():
            narr_durations[clip_id] = probe_audio_duration(narr_path)

    music_volume_map = {
        "01": 0.25, "02": 0.20, "03": 0.20, "04": 0.20, "05": 0.20,
        "06": 0.20, "07": 0.25, "08": 0.25, "09": 0.25, "10": 0.35,
    }

    effective_durations = {}
    for clip_meta in clips:
        clip_id = clip_meta["id"]
        clip_duration = float(clip_meta["duration"])

        video_path = videos_dir / f"clip_{clip_id}.mp4"
        mixed_path = mixed_dir / f"clip_{clip_id}.mp4"
        narr_path = narr_dir / f"narration_{clip_id}.mp3"

        music_offset = sum(
            effective_durations.get(c["id"], float(c["duration"]))
            for c in clips if c["id"] < clip_id
        )

        success, eff_dur = mix_clip_audio(
            video_path=video_path,
            output_path=mixed_path,
            narration_path=narr_path if narr_path.exists() else None,
            music_path=music_path if music_path.exists() else None,
            clip_duration=clip_duration,
            narration_duration=narr_durations.get(clip_id, 0.0),
            music_offset=music_offset,
            music_volume=music_volume_map.get(clip_id, 0.20),
        )
        effective_durations[clip_id] = eff_dur

    print(f"\n  [{ts()}] Generating captions...")
    for clip_id, text in narration_lines.items():
        caption_path = captions_dir / f"clip_{clip_id}.ass"
        mixed_path = mixed_dir / f"clip_{clip_id}.mp4"
        captioned_path = captioned_dir / f"clip_{clip_id}.mp4"

        clip_meta = next((c for c in clips if c["id"] == clip_id), None)
        clip_dur = float(clip_meta["duration"]) if clip_meta else 8.0
        narr_dur = narr_durations.get(clip_id, clip_dur - NARRATION_DELAY)

        generate_word_captions(
            narration_text=text,
            narration_duration=narr_dur,
            output_path=caption_path,
        )
        burn_captions(
            video_path=mixed_path,
            captions_path=caption_path,
            output_path=captioned_path,
        )

    print(f"\n  [{ts()}] Stitching final video...")
    clip_paths = []
    for clip_meta in clips:
        clip_id = clip_meta["id"]
        captioned = captioned_dir / f"clip_{clip_id}.mp4"
        mixed = mixed_dir / f"clip_{clip_id}.mp4"
        raw = videos_dir / f"clip_{clip_id}.mp4"
        if captioned.exists():
            clip_paths.append(captioned)
        elif mixed.exists():
            clip_paths.append(mixed)
        elif raw.exists():
            clip_paths.append(raw)
        else:
            print(f"  WARNING: Missing clip_{clip_id}.mp4, skipping")

    final_path = mixed_dir / f"final_{slug}.mp4"
    stitch_clips(clip_paths, final_path)

    return final_path


# ── Phase 6: Publish ──


def create_github_release(slug, title, final_path):
    """Create a GitHub Release and upload the final MP4. Return the asset download URL."""
    phase_banner("PHASE 6a: GITHUB RELEASE")

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


def publish_to_metricool_api(episode, asset_url):
    """Publish to YouTube Shorts + Instagram Reels via Metricool API."""
    phase_banner("PHASE 6b: METRICOOL PUBLISH")

    from lib.config import load_settings
    from lib.metricool import publish_to_metricool

    settings = load_settings()

    title = episode.get("title", "You Wouldn't Wanna Be")
    hook = episode.get("hook", "")

    caption = (
        f"{title}\n\n"
        f"{hook}\n\n"
        f"#YouWouldntWannaBe #History #Shorts #HistoryFacts "
        f"#LearnOnTikTok #HistoryTok #DarkHistory #Education"
    )

    result = publish_to_metricool(
        settings=settings,
        media_url=asset_url,
        title=title[:100],
        caption=caption,
        caption_instagram=caption,
        caption_youtube=caption,
    )

    print(f"  [{ts()}] Publish status: {result.status}")
    if result.error_message:
        print(f"  [{ts()}] Error: {result.error_message}")
    return result.status == "published"


def publish_to_metricool_direct(episode, final_path):
    """Publish to Metricool via direct file upload (no GitHub Release needed)."""
    phase_banner("PHASE 6b: METRICOOL PUBLISH (Direct Upload)")

    from lib.config import load_settings
    from lib.metricool import publish_to_metricool

    settings = load_settings()

    title = episode.get("title", "You Wouldn't Wanna Be")
    hook = episode.get("hook", "")

    caption = (
        f"{title}\n\n"
        f"{hook}\n\n"
        f"#YouWouldntWannaBe #History #Shorts #HistoryFacts "
        f"#LearnOnTikTok #HistoryTok #DarkHistory #Education"
    )

    print(f"  [{ts()}] Uploading {final_path.name} ({final_path.stat().st_size / (1024*1024):.1f} MB)...")

    result = publish_to_metricool(
        settings=settings,
        media_file_path=str(final_path),
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


# ── Main ──


def main():
    parser = argparse.ArgumentParser(description="You Wouldn't Wanna Be — Automated Pipeline")
    parser.add_argument("topic", nargs="*", help="Episode topic (omit for autonomous selection)")
    parser.add_argument("--publish", action="store_true", help="Publish to YouTube + Instagram via Metricool")
    parser.add_argument("--skip-audio", action="store_true", help="Skip audio generation phase")
    parser.add_argument("--skip-images", action="store_true", help="Skip image generation phase")
    parser.add_argument("--skip-videos", action="store_true", help="Skip video generation phase")
    parser.add_argument("--skip-post", action="store_true", help="Skip mix/captions/stitch phase")
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
    ep_dir, slug = write_episode_files(episode)

    if not args.skip_audio:
        run_audio_phase(episode, ep_dir)

    if not args.skip_images:
        run_images_phase(episode, ep_dir)

    if not args.skip_videos:
        run_videos_phase(episode, ep_dir)

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
    narrations = list((ep_dir / "output" / "audio" / "narration").glob("*.mp3"))
    print(f"  Images: {len(images)}")
    print(f"  Videos: {len(videos)}")
    print(f"  Narrations: {len(narrations)}")

    if args.publish and final_path.exists():
        asset_url = create_github_release(slug, episode["title"], final_path)
        if asset_url:
            publish_to_metricool_api(episode, asset_url)
        else:
            print(f"  [{ts()}] GitHub Release failed, trying direct file upload to Metricool...")
            publish_to_metricool_direct(episode, final_path)

    phase_banner("ALL DONE")
    print(f"  Episode: {episode['title']}")
    print(f"  Slug: {slug}")


if __name__ == "__main__":
    main()
