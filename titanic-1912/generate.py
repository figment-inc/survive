#!/usr/bin/env python3
"""
You Wouldn't Wanna Be — Sinking of the Titanic (1912)

90-second episode using Veo 3.1 extension chain for cohesive video.
13 clips: 1 initial (8s) + 12 extensions (7s each) = 92s, trimmed to 90s.

Usage:
  python generate.py                                # full pipeline (chain-extend)
  python generate.py --phase videos --chain-extend  # video chain only
  python generate.py --phase audio                  # ElevenLabs audio only
  python generate.py --phase mix                    # ffmpeg audio mix only
  python generate.py --phase captions               # burn captions only
  python generate.py --phase stitch                 # final concat only
  python generate.py --force                        # regenerate existing files
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

EPISODE_DIR = Path(__file__).parent
REPO_DIR = EPISODE_DIR.parent
sys.path.insert(0, str(REPO_DIR))

from lib.config import load_settings, CHANNEL_DIR
from lib.nanobanana import generate_image as nb_generate_image
from lib.veo import (
    get_client as veo_get_client, load_reference_images, generate_video,
    generate_initial, extend_video, save_chain_video,
    INITIAL_DURATION, EXTENSION_DURATION,
)
from lib.elevenlabs import generate_narration, generate_music
from lib.mixer import (
    mix_clip_audio, stitch_clips, probe_audio_duration, extract_last_frame,
    generate_word_captions, burn_captions, split_chain_video, trim_video,
    NARRATION_DELAY,
)
from lib.metricool import publish_to_metricool

OUTPUT_DIR = EPISODE_DIR / "output"
IMAGES_DIR = OUTPUT_DIR / "images"
VIDEOS_DIR = OUTPUT_DIR / "videos"
NARRATION_DIR = OUTPUT_DIR / "audio" / "narration"
MUSIC_DIR = OUTPUT_DIR / "audio" / "music"
MIXED_DIR = OUTPUT_DIR / "mixed"
CAPTIONS_DIR = OUTPUT_DIR / "captions"
CAPTIONED_DIR = OUTPUT_DIR / "captioned"


# ═══════════════════════════════════════════════════════════════
# EPISODE CONFIG — Titanic 1912 (90-second chain-extend format)
# ═══════════════════════════════════════════════════════════════

EPISODE_SLUG = "titanic-1912"
EPISODE_TITLE = "Sinking of the Titanic (1912)"


@dataclass
class Clip:
    id: str
    duration: int
    clip_type: str
    resolution: str
    use_reference: bool
    has_character: bool


# 13 clips for 90s target: 8s initial + 12 x 7s extensions = 92s -> trimmed to 90s
# All SCENE clips at 1080p with character reference for chain consistency
CLIPS = [
    Clip("01", 8,  "HOOK",  "720p", True, False),
    Clip("02", 7,  "SCENE", "720p", True, True),
    Clip("03", 7,  "SCENE", "720p", True, True),
    Clip("04", 7,  "SCENE", "720p", True, True),
    Clip("05", 7,  "SCENE", "720p", True, True),
    Clip("06", 7,  "SCENE", "720p", True, True),
    Clip("07", 7,  "SCENE", "720p", True, True),
    Clip("08", 7,  "SCENE", "720p", True, True),
    Clip("09", 7,  "SCENE", "720p", True, True),
    Clip("10", 7,  "SCENE", "720p", True, True),
    Clip("11", 7,  "SCENE", "720p", True, True),
    Clip("12", 7,  "SCENE", "720p", True, True),
    Clip("13", 5,  "SCENE", "720p", True, True),
]

CLIP_IDS = [c.id for c in CLIPS]
CLIP_MAP = {c.id: c for c in CLIPS}
TARGET_DURATION = 90

NARRATION_LINES: dict[str, str] = {
    "01": "What happens if you wake up on the Titanic two hours before it hits the iceberg?",
    "02": "You open your eyes in a third-class bunk. The sheets smell like coal dust. A baby is crying three doors down. It is April fourteenth, nineteen twelve.",
    "03": "You know exactly what is about to happen. You push through the corridor. You need to find a lifeboat. But you are six decks below the boat deck. And the gates are locked.",
    "04": "You grab a steward. You tell him the ship is going to sink. He smiles. He says the Titanic cannot sink. Everyone says that.",
    "05": "Eleven forty PM. You feel it. A shudder. Like the ship just exhaled. The engines stop. The silence is worse than the impact.",
    "06": "Water appears. It does not rush. It creeps. Ankle-deep in the mail room. Then knee-deep. Then the lights flicker.",
    "07": "You run for the stairs. The gates are still locked. A mother is pushing her children through the bars. A crewman fumbles with keys that do not fit.",
    "08": "On the boat deck, it is chaos disguised as calm. The band is playing. Women and children first. But there are not enough boats. There were never enough boats.",
    "09": "The bow drops. The stern rises. Fifteen hundred people realize at the same moment that the math does not work. Twenty lifeboats. Two thousand two hundred passengers.",
    "10": "The ship breaks in half. The sound is like nothing you have ever heard. Steel screaming. A thousand voices in the dark.",
    "11": "The water is twenty-eight degrees. You have fifteen minutes before your body shuts down. You can see the lifeboats. They are not coming back.",
    "12": "Two hours and forty minutes. That is how long it took. The unsinkable ship. Gone.",
    "13": "Seven hundred and ten people survived. You were not one of them.",
}

MUSIC_PROMPT = (
    "Dark cinematic underscore for a short documentary about the sinking of the Titanic. "
    "Begins with elegant, melancholy strings — a waltz-like motif suggesting Edwardian grandeur. "
    "Transitions to building tension with low cello drones and a ticking clock-like pulse. "
    "Peaks with massive, overwhelming orchestral intensity during the sinking — brass, "
    "timpani, dissonant strings. Resolves into silence broken only by a single piano note "
    "and distant, fading strings. The overall feel is tragedy foretold — beauty collapsing "
    "into catastrophe, then emptiness. No vocals. Instrumental only."
)

MUSIC_VOLUME_MAP: dict[str, float] = {
    "01": 0.25,
    "02": 0.20,
    "03": 0.20,
    "04": 0.20,
    "05": 0.25,
    "06": 0.25,
    "07": 0.25,
    "08": 0.25,
    "09": 0.30,
    "10": 0.35,
    "11": 0.30,
    "12": 0.25,
    "13": 0.35,
}


# ═══════════════════════════════════════════════════════════════
# Pipeline Implementation
# ═══════════════════════════════════════════════════════════════

def ts():
    return datetime.now().strftime("%H:%M:%S")


def load_prompt(subdir, filename):
    path = EPISODE_DIR / subdir / filename
    if not path.exists():
        return None
    return path.read_text().strip()


# ---------------------------------------------------------------------------
# Phase: Audio (ElevenLabs)
# ---------------------------------------------------------------------------

def run_audio_phase(settings, clip_ids, force=False):
    print(f"\n{'=' * 60}")
    print(f"  PHASE: AUDIO GENERATION (ElevenLabs)")
    print(f"{'=' * 60}")

    if not settings.elevenlabs_api_key:
        print("  ERROR: ELEVENLABS_API_KEY not found.")
        return
    if not settings.elevenlabs_voice_id:
        print("  ERROR: ELEVENLABS_VOICE_ID not set.")
        return

    for clip_id in clip_ids:
        if clip_id not in NARRATION_LINES:
            continue
        narr_path = NARRATION_DIR / f"narration_{clip_id}.mp3"
        generate_narration(
            settings.elevenlabs_api_key,
            settings.elevenlabs_voice_id,
            NARRATION_LINES[clip_id],
            narr_path,
            force=force,
        )

    music_path = MUSIC_DIR / "background_music.mp3"
    generate_music(settings.elevenlabs_api_key, MUSIC_PROMPT, music_path, force=force)


# ---------------------------------------------------------------------------
# Phase: Images (NanoBanana Pro)
# ---------------------------------------------------------------------------

def run_images_phase(settings, clip_ids, force=False):
    print(f"\n{'=' * 60}")
    print(f"  PHASE: IMAGE GENERATION (NanoBanana Pro)")
    print(f"{'=' * 60}")

    if not settings.nanobanana_api_key:
        print("  ERROR: NANOBANANA_API_KEY not found.")
        return

    ref_dir = CHANNEL_DIR / "reference_images"
    ref_paths = []
    for name in ["skeleton_front_neutral.jpg", "skeleton_front_neutral.png"]:
        path = ref_dir / name
        if path.exists():
            ref_paths.append(path)
            print(f"  Loaded reference: {name}")
            break

    for clip_id in clip_ids:
        clip = CLIP_MAP[clip_id]
        output_path = IMAGES_DIR / f"clip_{clip_id}_frame.png"

        if output_path.exists() and not force:
            print(f"  [{ts()}] Skipping (exists): {output_path.name}")
            continue

        prompt = load_prompt("02_image_prompts", f"clip_{clip_id}_frame.txt")
        if not prompt:
            print(f"  WARNING: Missing image prompt for clip {clip_id}, skipping")
            continue

        print(f"\n  --- Clip {clip_id} ({clip.clip_type}, {clip.duration}s) ---")
        nb_generate_image(
            api_key=settings.nanobanana_api_key,
            model=settings.nanobanana_model,
            prompt=prompt,
            output_path=output_path,
            reference_paths=ref_paths if clip.has_character else None,
            has_character=clip.has_character,
        )


# ---------------------------------------------------------------------------
# Phase: Videos — Independent (Veo 3.1, legacy mode)
# ---------------------------------------------------------------------------

def run_videos_phase(settings, clip_ids, force=False):
    print(f"\n{'=' * 60}")
    print(f"  PHASE: VIDEO GENERATION (Veo 3.1 — independent clips)")
    print(f"{'=' * 60}")

    if not settings.gemini_api_key:
        print("  ERROR: GEMINI_API_KEY not found.")
        return

    client = veo_get_client(settings.gemini_api_key)
    ref_images = load_reference_images(CHANNEL_DIR)

    for clip_id in clip_ids:
        clip = CLIP_MAP[clip_id]
        output_path = VIDEOS_DIR / f"clip_{clip.id}.mp4"
        if output_path.exists() and not force:
            print(f"  [{ts()}] Skipping (exists): {output_path.name}")
            continue

        prompt = load_prompt("03_veo_video_prompts", f"clip_{clip.id}.txt")
        if not prompt:
            print(f"  WARNING: Missing video prompt for clip {clip.id}, skipping")
            continue

        print(f"\n  --- Clip {clip.id} ({clip.clip_type}, {clip.duration}s @ {clip.resolution}) ---")
        first_frame = IMAGES_DIR / f"clip_{clip.id}_frame.png"

        generate_video(
            client=client,
            prompt=prompt,
            output_path=output_path,
            duration=clip.duration,
            resolution=clip.resolution,
            ref_images=ref_images if clip.use_reference else None,
            first_frame_path=first_frame if first_frame.exists() else None,
            use_reference=clip.use_reference,
        )


# ---------------------------------------------------------------------------
# Phase: Videos — Extension Chain (Veo 3.1 sequential extend)
# ---------------------------------------------------------------------------

def run_videos_chain_extend_phase(settings, clip_ids, force=False):
    """Generate all clips as a single continuous video via Veo extension chain."""
    print(f"\n{'=' * 60}")
    print(f"  PHASE: VIDEO GENERATION — EXTENSION CHAIN (Veo 3.1)")
    print(f"  Target: {TARGET_DURATION}s via {len(clip_ids)} chained segments")
    print(f"  Initial: {INITIAL_DURATION}s + {len(clip_ids) - 1} extensions @ {EXTENSION_DURATION}s")
    print(f"{'=' * 60}")

    if not settings.gemini_api_key:
        print("  ERROR: GEMINI_API_KEY not found.")
        return

    chain_video_path = VIDEOS_DIR / "chain_raw.mp4"
    chain_trimmed_path = VIDEOS_DIR / "chain_trimmed.mp4"

    all_split_exist = all(
        (VIDEOS_DIR / f"clip_{cid}.mp4").exists() for cid in clip_ids
    )
    if all_split_exist and not force:
        print(f"  [{ts()}] All split clips exist, skipping chain generation.")
        print(f"  Use --force to regenerate.")
        return

    client = veo_get_client(settings.gemini_api_key)
    ref_images = load_reference_images(CHANNEL_DIR)

    prompts: list[tuple[str, str]] = []
    for clip_id in clip_ids:
        prompt = load_prompt("03_veo_video_prompts", f"clip_{clip_id}.txt")
        if not prompt:
            print(f"  ERROR: Missing video prompt for clip {clip_id}. "
                  f"Generate prompts first.")
            return
        prompts.append((clip_id, prompt))

    handle = None
    for i, (clip_id, prompt) in enumerate(prompts):
        clip = CLIP_MAP[clip_id]
        print(f"\n  --- Clip {clip_id} ({clip.clip_type}, segment {i+1}/{len(prompts)}) ---")

        try:
            if i == 0:
                handle = generate_initial(
                    client=client,
                    prompt=prompt,
                    ref_images=ref_images if clip.use_reference else None,
                    duration=INITIAL_DURATION,
                    resolution=clip.resolution,
                )
            else:
                handle = extend_video(
                    client=client,
                    handle=handle,
                    prompt=prompt,
                    resolution=clip.resolution,
                )
        except Exception as e:
            print(f"  ERROR at clip {clip_id}: {e}")
            if handle and handle.duration_seconds > 0:
                print(f"  Saving partial chain ({handle.duration_seconds:.0f}s)...")
                save_chain_video(handle, chain_video_path)
            return

    save_chain_video(handle, chain_video_path)

    actual_duration = handle.duration_seconds
    if actual_duration > TARGET_DURATION:
        print(f"\n  Trimming {actual_duration:.0f}s -> {TARGET_DURATION}s...")
        trim_video(chain_video_path, chain_trimmed_path, TARGET_DURATION)
        source_for_split = chain_trimmed_path
    else:
        source_for_split = chain_video_path

    print(f"\n  Splitting chain into {len(clip_ids)} per-clip segments...")
    clip_durations = [(cid, float(CLIP_MAP[cid].duration)) for cid in clip_ids]
    split_chain_video(source_for_split, clip_durations, VIDEOS_DIR, force=force)


# ---------------------------------------------------------------------------
# Phase: Mix (ffmpeg)
# ---------------------------------------------------------------------------

def run_mix_phase(clip_ids, force=False):
    print(f"\n{'=' * 60}")
    print(f"  PHASE: AUDIO MIXING (ffmpeg — Veo audio + narration + music)")
    print(f"{'=' * 60}")

    narr_durations: dict[str, float] = {}
    for clip_id in clip_ids:
        narr_path = NARRATION_DIR / f"narration_{clip_id}.mp3"
        if narr_path.exists():
            dur = probe_audio_duration(narr_path)
            narr_durations[clip_id] = dur

    if narr_durations:
        print(f"\n  Narration durations (probed):")
        for cid, dur in sorted(narr_durations.items()):
            clip_dur = CLIP_MAP[cid].duration
            needed = dur + 0.5 + 0.3
            status = "OK" if needed <= clip_dur else f"+{needed - clip_dur:.1f}s over"
            print(f"    clip {cid}: {dur:.1f}s narration vs {clip_dur}s video — {status}")
        print()

    effective_durations: dict[str, float] = {}
    music_path = MUSIC_DIR / "background_music.mp3"

    for clip_id in clip_ids:
        clip = CLIP_MAP[clip_id]
        video_path = VIDEOS_DIR / f"clip_{clip_id}.mp4"
        mixed_path = MIXED_DIR / f"clip_{clip_id}.mp4"
        narr_path = NARRATION_DIR / f"narration_{clip_id}.mp3"

        music_offset = sum(effective_durations.get(c.id, c.duration) for c in CLIPS if c.id < clip_id)

        success, eff_dur = mix_clip_audio(
            video_path=video_path,
            output_path=mixed_path,
            narration_path=narr_path if narr_path.exists() else None,
            music_path=music_path if music_path.exists() else None,
            clip_duration=float(clip.duration),
            narration_duration=narr_durations.get(clip_id, 0.0),
            music_offset=music_offset,
            music_volume=MUSIC_VOLUME_MAP.get(clip_id, 0.20),
            force=force,
        )
        effective_durations[clip_id] = eff_dur

    total = sum(effective_durations.get(c.id, c.duration) for c in CLIPS)
    print(f"\n  Total episode duration: {total:.1f}s", end="")
    if total > 180:
        print(f" — WARNING: exceeds 3min Shorts limit")
    elif total > 90:
        print(f" — slightly over 90s target")
    else:
        print(f" — OK")


# ---------------------------------------------------------------------------
# Phase: Captions (ffmpeg)
# ---------------------------------------------------------------------------

def run_captions_phase(clip_ids, force=False):
    print(f"\n{'=' * 60}")
    print(f"  PHASE: ANIMATED CAPTIONS (word-by-word)")
    print(f"{'=' * 60}")

    narr_durations: dict[str, float] = {}
    for clip_id in clip_ids:
        narr_path = NARRATION_DIR / f"narration_{clip_id}.mp3"
        if narr_path.exists():
            narr_durations[clip_id] = probe_audio_duration(narr_path)

    for clip_id in clip_ids:
        if clip_id not in NARRATION_LINES:
            continue

        caption_path = CAPTIONS_DIR / f"clip_{clip_id}.ass"
        mixed_path = MIXED_DIR / f"clip_{clip_id}.mp4"
        captioned_path = CAPTIONED_DIR / f"clip_{clip_id}.mp4"

        narr_dur = narr_durations.get(clip_id, float(CLIP_MAP[clip_id].duration) - NARRATION_DELAY)
        generate_word_captions(
            narration_text=NARRATION_LINES[clip_id],
            narration_duration=narr_dur,
            output_path=caption_path,
        )

        burn_captions(
            video_path=mixed_path,
            captions_path=caption_path,
            output_path=captioned_path,
            force=force,
        )


# ---------------------------------------------------------------------------
# Phase: Stitch (ffmpeg)
# ---------------------------------------------------------------------------

def run_stitch_phase(clip_ids):
    print(f"\n{'=' * 60}")
    print(f"  STITCHING FINAL VIDEO")
    print(f"{'=' * 60}")

    clip_paths = []
    for cid in clip_ids:
        captioned = CAPTIONED_DIR / f"clip_{cid}.mp4"
        mixed = MIXED_DIR / f"clip_{cid}.mp4"
        raw = VIDEOS_DIR / f"clip_{cid}.mp4"
        if captioned.exists():
            clip_paths.append(captioned)
        elif mixed.exists():
            clip_paths.append(mixed)
            print(f"  WARNING: Using uncaptioned video for clip {cid}")
        elif raw.exists():
            clip_paths.append(raw)
            print(f"  WARNING: Using unmixed video for clip {cid}")
        else:
            print(f"  WARNING: Missing clip_{cid}.mp4, skipping")

    output_path = MIXED_DIR / f"final_{EPISODE_SLUG}.mp4"
    stitch_clips(clip_paths, output_path)


# ---------------------------------------------------------------------------
# Phase: Publish (Metricool)
# ---------------------------------------------------------------------------

def run_publish_phase(settings, schedule_at=""):
    print(f"\n{'=' * 60}")
    print(f"  PUBLISHING VIA METRICOOL")
    print(f"{'=' * 60}")

    final_path = MIXED_DIR / f"final_{EPISODE_SLUG}.mp4"
    if not final_path.exists():
        print(f"  ERROR: Final video not found: {final_path}")
        print("  Run the full pipeline first: python generate.py")
        return

    print(f"  NOTE: Metricool requires a public URL for the video.")
    print(f"  Upload {final_path} to a hosting service and provide the URL.")
    print(f"  Then use: python publish.py --episode {EPISODE_SLUG} --media-url <URL>")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=f"You Wouldn't Wanna Be — {EPISODE_TITLE}"
    )
    parser.add_argument(
        "--phase",
        choices=["images", "videos", "audio", "mix", "captions", "stitch", "publish", "all"],
        default="all",
    )
    parser.add_argument("--clip", type=str, choices=CLIP_IDS, help="Run a single clip only")
    parser.add_argument("--force", action="store_true", help="Regenerate existing files")
    parser.add_argument("--chain-extend", action="store_true", dest="chain_extend",
                        default=True,
                        help="Veo extension chain (default ON for this episode)")
    parser.add_argument("--no-chain-extend", action="store_false", dest="chain_extend",
                        help="Disable extension chain, use independent clip generation")
    parser.add_argument("--schedule", type=str, default="", help="ISO datetime for Metricool scheduling")
    args = parser.parse_args()

    settings = load_settings()

    for d in [IMAGES_DIR, VIDEOS_DIR, NARRATION_DIR, MUSIC_DIR, MIXED_DIR, CAPTIONS_DIR, CAPTIONED_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    if args.phase == "stitch":
        clip_ids = [args.clip] if args.clip else CLIP_IDS
        run_stitch_phase(clip_ids)
        return

    if args.phase == "publish":
        run_publish_phase(settings, args.schedule)
        return

    phases = ["audio", "images", "videos", "mix", "captions"] if args.phase == "all" else [args.phase]
    clip_ids = [args.clip] if args.clip else CLIP_IDS

    print(f"\n{'=' * 60}")
    print(f"  You Wouldn't Wanna Be — {EPISODE_TITLE}")
    print(f"  {'Extension Chain' if args.chain_extend else 'Independent Clips'} Format")
    print(f"{'=' * 60}")
    print(f"  Episode:       {EPISODE_SLUG}")
    print(f"  Clips:         {len(clip_ids)} ({TARGET_DURATION}s target)")
    print(f"  Phases:        {phases}")
    print(f"  Image model:   NanoBanana Pro ({settings.nanobanana_model})")
    print(f"  Video model:   Veo 3.1")
    print(f"  TTS:           ElevenLabs ({settings.elevenlabs_voice_id or 'NOT SET'})")
    print(f"  NanoBanana:    {'SET' if settings.nanobanana_api_key else 'MISSING'}")
    print(f"  Gemini key:    {'SET' if settings.gemini_api_key else 'MISSING'}")
    print(f"  ElevenLabs:    {'SET' if settings.elevenlabs_api_key else 'MISSING'}")
    print(f"  Chain extend:  {'ON' if args.chain_extend else 'OFF'}")
    print(f"  Output:        {OUTPUT_DIR}")
    print(f"{'=' * 60}")

    if "audio" in phases:
        run_audio_phase(settings, clip_ids, args.force)

    if "images" in phases:
        run_images_phase(settings, clip_ids, args.force)

    if "videos" in phases:
        if args.chain_extend:
            run_videos_chain_extend_phase(settings, clip_ids, args.force)
        else:
            run_videos_phase(settings, clip_ids, args.force)

    if "mix" in phases:
        run_mix_phase(clip_ids, args.force)

    if "captions" in phases:
        run_captions_phase(clip_ids, args.force)

    if args.phase == "all" and not args.clip:
        run_stitch_phase(clip_ids)

    print(f"\n{'=' * 60}")
    print(f"  PIPELINE COMPLETE")
    print(f"{'=' * 60}")

    images = list(IMAGES_DIR.glob("clip_*.png"))
    videos = list(VIDEOS_DIR.glob("clip_*.mp4"))
    narrations = list(NARRATION_DIR.glob("narration_*.mp3"))
    mixed = list(MIXED_DIR.glob("clip_*.mp4"))
    print(f"  Images:     {len(images)}")
    print(f"  Videos:     {len(videos)}")
    print(f"  Narrations: {len(narrations)}")
    print(f"  Mixed:      {len(mixed)}")

    final = MIXED_DIR / f"final_{EPISODE_SLUG}.mp4"
    if final.exists():
        size_mb = final.stat().st_size / (1024 * 1024)
        print(f"  Final:      {final} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
