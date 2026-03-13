"""Veo 3.1 video generation — keeps native audio (ambient/SFX).

Supports two modes:
  1. Independent clips via generate_video() (original)
  2. Extension chain via generate_initial() + extend_video() for cohesive long-form video
"""

from __future__ import annotations

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


@dataclass
class VeoVideoHandle:
    """Wraps a Veo generated video object for passing between generate/extend calls."""

    video: Any
    duration_seconds: float = 0
    extension_count: int = 0

SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_ONLY_HIGH"),
]


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def get_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def load_reference_images(channel_dir: Path) -> list[bytes]:
    """Load canonical skeleton reference images for Veo conditioning.

    Returns up to 3 images (Veo 3.1 max):
      1. skeleton_front_neutral — full-body primary anchor
      2. skeleton_headshot — close-up for skull detail
      3. skeleton_side — 3/4 angle for depth
    """
    ref_dir = channel_dir / "reference_images"
    refs: list[bytes] = []

    for name in ["skeleton_front_neutral.jpg", "skeleton_front_neutral.png"]:
        path = ref_dir / name
        if path.exists():
            data = path.read_bytes()
            print(f"  Loaded ref (full-body): {name} ({len(data) / 1024:.0f} KB)")
            refs.append(data)
            break

    for name in ["skeleton_headshot.png", "skeleton_side.png"]:
        path = ref_dir / name
        if path.exists():
            data = path.read_bytes()
            print(f"  Loaded ref: {name} ({len(data) / 1024:.0f} KB)")
            refs.append(data)

    if not refs:
        print("  WARNING: No channel reference images found.")
    else:
        print(f"  Total reference images: {len(refs)}/3 (Veo 3.1 max)")

    return refs


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
) -> bool:
    """Generate a video clip via Veo 3.1.

    Native audio (ambient/SFX) is kept — not muted or stripped.
    Falls back through: ASSET refs -> first-frame -> text-only.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base_config = {
        "aspect_ratio": "9:16",
        "duration_seconds": duration,
        "resolution": resolution,
    }

    if use_reference and ref_images:
        ref_entries = [
            types.VideoGenerationReferenceImage(
                reference_type="ASSET",
                image=types.Image(image_bytes=img_bytes, mime_type="image/png"),
            )
            for img_bytes in ref_images
        ]
        config_kwargs = {**base_config, "reference_images": ref_entries, "person_generation": "allow_adult"}
        gen_kwargs = {"model": VIDEO_MODEL, "prompt": prompt}

        success, result = _submit_and_poll(client, gen_kwargs, config_kwargs, output_path.stem, f"{len(ref_images)} refs")
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
) -> VeoVideoHandle:
    """Extend an existing video by passing the previous clip as seed frames.

    Veo uses the last frames of the previous video to maintain visual continuity.
    Returns a new VeoVideoHandle with the extended video and updated duration.
    Retries with backoff if the server reports the video is not yet processed.
    """
    ext_num = handle.extension_count + 1
    new_duration = handle.duration_seconds + EXTENSION_DURATION

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
