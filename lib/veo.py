"""Veo 3.1 video generation — Family Guy animation with silent video (SFX/ambience only, NO speech).

Supports two modes:
  1. Independent clips via generate_video() with angle-aware ASSET reference selection
  2. Extension chain via generate_initial() + extend_video() for cohesive long-form video
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

VIDEO_MODEL = "veo-3.1-generate-preview"

INITIAL_DURATION = 8
EXTENSION_DURATION = 7

STYLE_ENFORCEMENT = (
    "CRITICAL: This must be flat 2D cel-shaded animation with thick black outlines. "
    "ZERO photorealistic elements. ZERO gradients. ZERO 3D shading. "
    "Match the art style of the attached character reference sheet exactly.\n\n"
)

NO_TEXT_PREFIX = (
    "CRITICAL: Generate ZERO on-screen text, titles, captions, subtitles, "
    "watermarks, labels, or typography of any kind in the video. "
    "The frame must be purely visual with no rendered text.\n\n"
)

NO_SPEECH_PREFIX = (
    "CRITICAL: Generate ZERO spoken dialogue, narration, voiceover, or character speech. "
    "No crowd dialogue, no background conversations, no character vocalizations of any kind. "
    "The video must be COMPLETELY SILENT except for environmental SFX and ambient sounds. "
    "No character should move their mouth or appear to speak.\n\n"
)

NO_TEXT_SUFFIX = (
    "\n\nREMINDER: No text, titles, captions, or written words "
    "should appear anywhere in the video frame at any time. "
    "No speech, narration, or voiceover in the audio."
)


def _wrap_prompt(prompt: str, episode_style: str | None = None) -> str:
    """Prepend style enforcement + no-text + no-speech instructions and append reminders."""
    parts = [NO_TEXT_PREFIX, NO_SPEECH_PREFIX, STYLE_ENFORCEMENT]
    if episode_style:
        parts.append(f"EPISODE VISUAL IDENTITY: {episode_style}\n\n")
    parts.append(prompt)
    parts.append(NO_TEXT_SUFFIX)
    return "".join(parts)


@dataclass
class VeoVideoHandle:
    """Wraps a Veo generated video object for passing between generate/extend calls."""

    video: Any
    duration_seconds: float = 0
    extension_count: int = 0

SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
]


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def extract_first_frame(video_path: Path) -> Path:
    """Extract the first frame of a video as a PNG for use as a style anchor."""
    out = video_path.with_suffix(".frame1.png")
    if out.exists():
        return out
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vframes", "1", "-q:v", "1", str(out),
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not out.exists():
        print(f"  [{_ts()}] WARNING: Failed to extract first frame from {video_path.name}")
        return None
    print(f"  [{_ts()}] Style anchor frame extracted: {out.name} ({out.stat().st_size / 1024:.0f} KB)")
    return out


def get_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def load_reference_images(channel_dir: Path) -> dict[str, list[bytes]]:
    """Load skeleton reference images for angle-aware Veo conditioning.

    Returns a dict keyed by angle: 'front', 'side', 'threequarter', 'back'.
    Each value is a list of image bytes for that angle.
    Falls back to the single canonical reference if multi-angle images don't exist.
    """
    ref_dir = channel_dir / "reference_images"

    angle_map = {
        "front": [
            "skeleton_familyguy_front.png",
            "skeleton_front_neutral.jpg",
            "skeleton_front_neutral.png",
        ],
        "threequarter": [
            "skeleton_familyguy_threequarter.png",
        ],
        "side": [
            "skeleton_familyguy_side.png",
        ],
        "back": [
            "skeleton_familyguy_back.png",
        ],
    }

    all_refs: dict[str, list[bytes]] = {}
    for angle, filenames in angle_map.items():
        refs = []
        for name in filenames:
            path = ref_dir / name
            if path.exists():
                data = path.read_bytes()
                print(f"  Loaded ref ({angle}): {name} ({len(data) / 1024:.0f} KB)")
                refs.append(data)
        if refs:
            all_refs[angle] = refs

    total = sum(len(v) for v in all_refs.values())
    if not all_refs:
        print("  WARNING: No channel reference images found.")
    else:
        print(f"  Total reference images: {total} across {len(all_refs)} angles")

    return all_refs


def select_refs_for_prompt(all_refs: dict[str, list[bytes]], prompt_text: str) -> list[bytes]:
    """Select the best reference images based on camera angle keywords in the prompt.

    Parses the prompt for angle keywords and returns up to 3 refs for that angle.
    Falls back to front-facing refs if no angle is detected.
    """
    prompt_lower = prompt_text.lower()

    if any(kw in prompt_lower for kw in ["from behind", "from the back", "back view", "rear"]):
        angle = "back"
    elif any(kw in prompt_lower for kw in ["three-quarter", "three quarter", "3/4"]):
        angle = "threequarter"
    elif any(kw in prompt_lower for kw in ["side view", "from the side", "profile"]):
        angle = "side"
    else:
        angle = "front"

    refs = list(all_refs.get(angle, []))
    if not refs:
        refs = list(all_refs.get("front", []))
        angle = "front (fallback)"

    front_primary = all_refs.get("front", [None])[0] if all_refs.get("front") else None
    if front_primary and front_primary not in refs:
        refs = [front_primary] + refs

    selected = refs[:3]
    print(f"  [{_ts()}] Ref selection: angle={angle}, count={len(selected)}/3")
    return selected


def _wait_for_video(client: genai.Client, operation) -> object:
    poll_count = 0
    while not operation.done:
        time.sleep(15)
        operation = client.operations.get(operation)
        poll_count += 1
        print(f"  [{_ts()}] Generating... ({poll_count * 15}s)")
    return operation


def _submit_and_poll(client, gen_kwargs, config_kwargs, clip_id, ref_label) -> tuple[bool, object | None]:
    print(f"  [{_ts()}] Submitting video: clip_{clip_id}.mp4 (mode={ref_label})")

    try:
        gen_kwargs["config"] = types.GenerateVideosConfig(**config_kwargs)
        operation = client.models.generate_videos(**gen_kwargs)
    except Exception as e:
        print(f"  ERROR submitting: {e}")
        return False, None

    print(f"  [{_ts()}] Polling for completion...")
    operation = _wait_for_video(client, operation)

    if not operation.result or not operation.result.generated_videos:
        reasons = getattr(operation.result, "rai_media_filtered_reasons", None)
        if reasons:
            print(f"  BLOCKED: {reasons}")
        else:
            print(f"  ERROR: No video generated. Response: {operation}")
        return False, operation

    generated_video = operation.result.generated_videos[0]
    return True, (operation, generated_video)


def generate_video(
    client: genai.Client,
    prompt: str,
    output_path: Path,
    duration: int = 8,
    resolution: str = "1080p",
    ref_images: list[bytes] | None = None,
    first_frame_path: Path | None = None,
    use_reference: bool = True,
    style_anchor_refs: list[bytes] | None = None,
    episode_style: str | None = None,
) -> bool:
    """Generate a video clip via Veo 3.1.

    Native audio (ambient/SFX) is kept — not muted or stripped.
    Falls back through: ASSET refs -> first-frame -> text-only.
    style_anchor_refs are appended to character refs for cross-clip consistency.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = _wrap_prompt(prompt, episode_style=episode_style)
    base_config = {
        "aspect_ratio": "9:16",
        "duration_seconds": duration,
        "resolution": resolution,
    }

    combined_refs = list(ref_images or [])
    if style_anchor_refs:
        combined_refs.extend(style_anchor_refs)

    if use_reference and combined_refs:
        ref_entries = [
            types.VideoGenerationReferenceImage(
                reference_type="ASSET",
                image=types.Image(image_bytes=img_bytes, mime_type="image/png"),
            )
            for img_bytes in combined_refs
        ]
        config_kwargs = {**base_config, "reference_images": ref_entries, "person_generation": "allow_adult"}
        gen_kwargs = {"model": VIDEO_MODEL, "prompt": prompt}

        success, result = _submit_and_poll(client, gen_kwargs, config_kwargs, output_path.stem, f"{len(combined_refs)} refs")
        if success:
            operation, generated_video = result
            client.files.download(file=generated_video.video)
            generated_video.video.save(str(output_path))
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"  [{_ts()}] Video saved: {output_path} ({size_mb:.1f} MB)")
            return True

        print(f"  [{_ts()}] Auto-fallback: retrying with first-frame conditioning...")

        ff_path = first_frame_path
        if ff_path and ff_path.exists():
            frame_bytes = ff_path.read_bytes()
            gen_kwargs = {
                "model": VIDEO_MODEL,
                "prompt": prompt,
                "image": types.Image(image_bytes=frame_bytes, mime_type="image/png"),
            }
            success, result = _submit_and_poll(client, gen_kwargs, dict(base_config), output_path.stem, "first-frame (fallback)")
            if success:
                operation, generated_video = result
                client.files.download(file=generated_video.video)
                generated_video.video.save(str(output_path))
                size_mb = output_path.stat().st_size / (1024 * 1024)
                print(f"  [{_ts()}] Video saved: {output_path} ({size_mb:.1f} MB)")
                return True

        print(f"  [{_ts()}] Final fallback: text-only generation...")
        gen_kwargs = {"model": VIDEO_MODEL, "prompt": prompt}
        success, result = _submit_and_poll(client, gen_kwargs, dict(base_config), output_path.stem, "text-only (fallback)")
        if success:
            operation, generated_video = result
            client.files.download(file=generated_video.video)
            generated_video.video.save(str(output_path))
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"  [{_ts()}] Video saved: {output_path} ({size_mb:.1f} MB)")
            return True
        return False

    gen_kwargs: dict = {"model": VIDEO_MODEL, "prompt": prompt}
    if first_frame_path and first_frame_path.exists():
        frame_bytes = first_frame_path.read_bytes()
        gen_kwargs["image"] = types.Image(image_bytes=frame_bytes, mime_type="image/png")
        ref_label = "first-frame"
    else:
        ref_label = "text-only"

    success, result = _submit_and_poll(client, gen_kwargs, dict(base_config), output_path.stem, ref_label)
    if success:
        operation, generated_video = result
        client.files.download(file=generated_video.video)
        generated_video.video.save(str(output_path))
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  [{_ts()}] Video saved: {output_path} ({size_mb:.1f} MB)")
        return True

    if ref_label == "first-frame":
        print(f"  [{_ts()}] Fallback: retrying text-only (no first-frame)...")
        gen_kwargs = {"model": VIDEO_MODEL, "prompt": prompt}
        success, result = _submit_and_poll(client, gen_kwargs, dict(base_config), output_path.stem, "text-only (fallback)")
        if success:
            operation, generated_video = result
            client.files.download(file=generated_video.video)
            generated_video.video.save(str(output_path))
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"  [{_ts()}] Video saved: {output_path} ({size_mb:.1f} MB)")
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# Extension Chain API — produces a single continuous video
# ═══════════════════════════════════════════════════════════════


def generate_initial(
    client: genai.Client,
    prompt: str,
    ref_images: list[bytes] | None = None,
    duration: int = INITIAL_DURATION,
    resolution: str = "720p",
    episode_style: str | None = None,
) -> VeoVideoHandle:
    """Generate the first clip in an extension chain.

    Optionally conditions on ASSET reference images for character consistency.
    Returns a VeoVideoHandle that can be passed to extend_video().
    """
    config_kwargs: dict[str, Any] = {
        "aspect_ratio": "9:16",
        "duration_seconds": duration,
        "resolution": resolution,
    }
    prompt = _wrap_prompt(prompt, episode_style=episode_style)
    gen_kwargs: dict[str, Any] = {"model": VIDEO_MODEL, "prompt": prompt}

    if ref_images:
        print(f"  [{_ts()}] NOTE: Skipping ASSET refs for initial clip — "
              f"extension chain requires unmodified Veo output. "
              f"Character consistency maintained via prompt only.")
        # ASSET reference_images produce a video that Veo's extend API
        # rejects with "must be a video that has been processed".
        # Using text-only generation for chain compatibility.

    gen_kwargs["config"] = types.GenerateVideosConfig(**config_kwargs)

    print(f"  [{_ts()}] Chain: generating initial {duration}s clip "
          f"(refs={len(ref_images) if ref_images else 0})")

    operation = client.models.generate_videos(**gen_kwargs)
    operation = _wait_for_video(client, operation)

    if not operation.result or not operation.result.generated_videos:
        reasons = getattr(operation.result, "rai_media_filtered_reasons", None)
        msg = f"BLOCKED: {reasons}" if reasons else f"No video generated: {operation}"
        raise RuntimeError(msg)

    generated = operation.result.generated_videos[0]
    client.files.download(file=generated.video)

    print(f"  [{_ts()}] Chain: initial clip ready ({duration}s cumulative)")
    return VeoVideoHandle(video=generated.video, duration_seconds=duration, extension_count=0)


def extend_video(
    client: genai.Client,
    handle: VeoVideoHandle,
    prompt: str,
    resolution: str = "720p",
    max_retries: int = 3,
    episode_style: str | None = None,
) -> VeoVideoHandle:
    """Extend an existing video by passing the previous clip as seed frames.

    Veo uses the last frames of the previous video to maintain visual continuity.
    Returns a new VeoVideoHandle with the extended video and updated duration.
    Retries with backoff if the server reports the video is not yet processed.
    """
    ext_num = handle.extension_count + 1
    new_duration = handle.duration_seconds + EXTENSION_DURATION
    prompt = _wrap_prompt(prompt, episode_style=episode_style)

    # Brief delay to let the server finish processing the previous video
    print(f"  [{_ts()}] Waiting 10s for server-side video processing...")
    time.sleep(10)

    for attempt in range(max_retries):
        if attempt > 0:
            wait = 15 * attempt
            print(f"  [{_ts()}] Retry {attempt}/{max_retries} — "
                  f"waiting {wait}s for server-side processing...")
            time.sleep(wait)

        print(f"  [{_ts()}] Chain: extending #{ext_num} "
              f"({handle.duration_seconds:.0f}s -> {new_duration:.0f}s)")

        try:
            operation = client.models.generate_videos(
                model=VIDEO_MODEL,
                video=handle.video,
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    aspect_ratio="9:16",
                    resolution=resolution,
                ),
            )
        except Exception as e:
            if "has been processed" in str(e) and attempt < max_retries - 1:
                print(f"  [{_ts()}] Server says video not yet processed, will retry...")
                continue
            raise

        operation = _wait_for_video(client, operation)

        if not operation.result or not operation.result.generated_videos:
            reasons = getattr(operation.result, "rai_media_filtered_reasons", None)
            msg = f"BLOCKED: {reasons}" if reasons else f"Extension #{ext_num} failed: {operation}"
            raise RuntimeError(msg)

        generated = operation.result.generated_videos[0]
        client.files.download(file=generated.video)

        print(f"  [{_ts()}] Chain: extension #{ext_num} ready ({new_duration:.0f}s cumulative)")
        return VeoVideoHandle(
            video=generated.video,
            duration_seconds=new_duration,
            extension_count=ext_num,
        )

    raise RuntimeError(f"Extension #{ext_num} failed after {max_retries} retries")


def save_chain_video(handle: VeoVideoHandle, output_path: Path) -> None:
    """Save the accumulated extension chain video to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle.video.save(str(output_path))
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Chain video saved: {output_path} "
          f"({size_mb:.1f} MB, {handle.duration_seconds:.0f}s, "
          f"{handle.extension_count} extensions)")
