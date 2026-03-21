"""Image-based slideshow video assembly — Ken Burns zoom/pan effects via ffmpeg.

Replaces Veo video generation with a sentence-driven image pipeline:
  1. Parse narration into sentences
  2. Assign 1-2 images per sentence based on word count
  3. Sync image display durations to Whisper word-level timestamps
  4. Assemble into a single video with zoompan + crossfade transitions
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── Sentence parsing ──


@dataclass
class Sentence:
    index: int
    text: str
    word_count: int
    image_count: int = 1


def parse_narration_sentences(script_text: str) -> list[Sentence]:
    """Split a dialogue script into sentence objects.

    Handles NARRATOR: prefixes, em-dash continuations, and multi-line scripts.
    Sentences split on '. ' boundaries; em-dash fragments within a single
    NARRATOR line stay as one sentence.
    """
    narrator_lines: list[str] = []
    for line in script_text.strip().splitlines():
        line = line.strip()
        if line.startswith("##") or not line:
            continue
        m = re.match(r"NARRATOR:\s*[\"']?(.+?)[\"']?\s*$", line)
        if m:
            narrator_lines.append(m.group(1).strip())

    full_text = " ".join(narrator_lines)
    full_text = re.sub(r"\s+", " ", full_text).strip()

    raw_sentences = re.split(r"(?<=[.!?])\s+", full_text)
    raw_sentences = [s.strip() for s in raw_sentences if s.strip()]

    sentences: list[Sentence] = []
    for i, text in enumerate(raw_sentences):
        wc = len(text.split())
        sentences.append(Sentence(index=i, text=text, word_count=wc))

    return sentences


def assign_image_counts(sentences: list[Sentence]) -> list[Sentence]:
    """Decide how many images each sentence gets (1 or 2).

    Heuristic: sentences with 8+ words or containing action keywords
    get 2 images (showing two moments). Short/simple sentences get 1.
    """
    action_patterns = re.compile(
        r"\b(then|suddenly|but|while|as|before|after|into|through|across|"
        r"behind|between|around|toward|against|beneath|above)\b",
        re.IGNORECASE,
    )

    for s in sentences:
        if s.word_count >= 10 and action_patterns.search(s.text):
            s.image_count = 2
        elif s.word_count >= 14:
            s.image_count = 2
        else:
            s.image_count = 1

    return sentences


# ── Timestamp sync ──


@dataclass
class ImageTiming:
    sentence_idx: int
    image_idx: int
    image_path: Path | None = None
    start_time: float = 0.0
    duration: float = 3.0


def _normalize_word(w: str) -> str:
    """Lowercase and strip punctuation for fuzzy word comparison."""
    return re.sub(r"[^\w']", "", w.lower())


def _find_sentence_span(
    sentence_words: list[str],
    whisper_words: list[str],
    search_start: int,
) -> tuple[int, int]:
    """Find the best matching span in whisper_words for a sentence's words.

    Uses a greedy forward scan starting from search_start: walks through
    whisper_words consuming matches to sentence_words. Returns (start, end)
    indices into the whisper_words list. Falls back to positional stepping
    if no matches are found.
    """
    if not sentence_words or search_start >= len(whisper_words):
        return search_start, min(search_start + len(sentence_words), len(whisper_words))

    norm_sentence = [_normalize_word(w) for w in sentence_words]

    best_start = -1
    sw_idx = 0
    ww_idx = search_start
    max_lookahead = min(len(whisper_words), search_start + len(sentence_words) * 3)

    while ww_idx < max_lookahead and sw_idx < len(norm_sentence):
        ww_norm = _normalize_word(whisper_words[ww_idx])
        if ww_norm == norm_sentence[sw_idx] or (
            norm_sentence[sw_idx] in ww_norm or ww_norm in norm_sentence[sw_idx]
        ):
            if best_start == -1:
                best_start = ww_idx
            sw_idx += 1
        ww_idx += 1

    if best_start == -1:
        return search_start, min(search_start + len(sentence_words), len(whisper_words))

    span_end = min(ww_idx, len(whisper_words))
    return best_start, span_end


def sync_images_to_timestamps(
    sentences: list[Sentence],
    word_timestamps: list[dict],
    narration_delay: float = 0.5,
    crossfade_duration: float = 0.3,
) -> list[ImageTiming]:
    """Map sentence images to display durations using Whisper word timestamps.

    Uses fuzzy text alignment to match script sentences to Whisper words,
    preventing cumulative drift from contractions/number expansions.
    Inflates each image duration to compensate for crossfade overlap loss
    so the assembled slideshow matches narration length.
    """
    if not word_timestamps:
        return _fallback_even_timing(sentences)

    total_narr_duration = word_timestamps[-1]["end"] if word_timestamps else 30.0
    whisper_words = [w.get("word", "") for w in word_timestamps]
    total_images = sum(s.image_count for s in sentences)

    xfade_loss_per_image = 0.0
    if total_images > 1:
        total_xfade_loss = (total_images - 1) * crossfade_duration
        xfade_loss_per_image = total_xfade_loss / total_images

    timings: list[ImageTiming] = []
    search_cursor = 0

    for s in sentences:
        sentence_words = s.text.split()
        span_start, span_end = _find_sentence_span(
            sentence_words, whisper_words, search_cursor,
        )

        if span_start < len(word_timestamps):
            t_start = word_timestamps[span_start]["start"]
        else:
            t_start = total_narr_duration

        if span_end > 0 and span_end <= len(word_timestamps):
            t_end = word_timestamps[span_end - 1]["end"]
        else:
            t_end = total_narr_duration

        sentence_duration = max(t_end - t_start, 1.0)
        img_duration = sentence_duration / s.image_count + xfade_loss_per_image

        for img_i in range(s.image_count):
            timings.append(ImageTiming(
                sentence_idx=s.index,
                image_idx=img_i,
                start_time=narration_delay + t_start + img_i * (sentence_duration / s.image_count),
                duration=img_duration,
            ))

        search_cursor = span_end

    if timings:
        print(f"  [{_ts()}] Timing sync: {len(timings)} images, "
              f"xfade compensation +{xfade_loss_per_image:.2f}s/image "
              f"({(total_images - 1) * crossfade_duration:.1f}s total)")

    return timings


def _fallback_even_timing(
    sentences: list[Sentence],
    total_duration: float = 55.0,
    narration_delay: float = 0.5,
) -> list[ImageTiming]:
    """Even distribution when Whisper timestamps are unavailable.

    Default 55s matches the Shorts/Reels ceiling for longer scripts.
    Callers should pass actual narration duration when known.
    """
    total_images = sum(s.image_count for s in sentences)
    if total_images == 0:
        return []

    per_image = (total_duration - narration_delay) / total_images
    timings: list[ImageTiming] = []
    t = narration_delay

    for s in sentences:
        for img_i in range(s.image_count):
            timings.append(ImageTiming(
                sentence_idx=s.index,
                image_idx=img_i,
                start_time=t,
                duration=per_image,
            ))
            t += per_image

    return timings


# ── Ken Burns effects ──


_EFFECTS = [
    "slow_zoom_in",
    "slow_zoom_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "zoom_in_pan_right",
    "zoom_out_pan_left",
]


def _zoompan_filter(
    effect: str,
    duration_frames: int,
    width: int = 720,
    height: int = 1280,
    fps: int = 30,
) -> str:
    """Build an ffmpeg zoompan filter string for a given Ken Burns effect."""
    d = duration_frames
    s = f"{width}x{height}"

    if effect == "slow_zoom_in":
        return (
            f"zoompan=z='min(zoom+0.0008,1.15)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )
    elif effect == "slow_zoom_out":
        return (
            f"zoompan=z='if(eq(on,1),1.15,max(zoom-0.0008,1.0))':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )
    elif effect == "pan_left":
        return (
            f"zoompan=z='1.08':"
            f"x='iw*0.08*(1-on/{d})':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )
    elif effect == "pan_right":
        return (
            f"zoompan=z='1.08':"
            f"x='iw*0.08*on/{d}':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )
    elif effect == "pan_up":
        return (
            f"zoompan=z='1.08':"
            f"x='iw/2-(iw/zoom/2)':y='ih*0.06*(1-on/{d})':"
            f"d={d}:s={s}:fps={fps}"
        )
    elif effect == "zoom_in_pan_right":
        return (
            f"zoompan=z='min(zoom+0.0006,1.12)':"
            f"x='iw*0.06*on/{d}':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )
    elif effect == "zoom_out_pan_left":
        return (
            f"zoompan=z='if(eq(on,1),1.12,max(zoom-0.0006,1.0))':"
            f"x='iw*0.06*(1-on/{d})':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )

    return (
        f"zoompan=z='min(zoom+0.0008,1.15)':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={d}:s={s}:fps={fps}"
    )


# ── Video assembly ──


def build_slideshow_video(
    timings: list[ImageTiming],
    output_path: Path,
    width: int = 720,
    height: int = 1280,
    fps: int = 30,
    crossfade_duration: float = 0.3,
) -> bool:
    """Assemble images into a single Ken Burns slideshow video with crossfade transitions.

    Each image gets a zoompan effect cycling through different Ken Burns styles.
    Adjacent images crossfade for smooth visual transitions.
    Output is a silent video (no audio track).
    """
    valid_timings = [t for t in timings if t.image_path and t.image_path.exists()]
    if not valid_timings:
        print(f"  [{_ts()}] ERROR: No valid images for slideshow")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    n = len(valid_timings)
    print(f"  [{_ts()}] Building slideshow: {n} images, "
          f"{sum(t.duration for t in valid_timings):.1f}s total")

    if n == 1:
        return _single_image_video(valid_timings[0], output_path, width, height, fps)

    inputs: list[str] = []
    filter_parts: list[str] = []

    for i, t in enumerate(valid_timings):
        inputs.extend(["-loop", "1", "-t", f"{t.duration:.3f}", "-i", str(t.image_path)])

        effect = _EFFECTS[i % len(_EFFECTS)]
        d_frames = int(t.duration * fps)
        zp = _zoompan_filter(effect, d_frames, width, height, fps)

        filter_parts.append(
            f"[{i}:v]scale=8000:-1,{zp},"
            f"setpts=PTS-STARTPTS,format=yuv420p[v{i}]"
        )

    current = "[v0]"
    cumulative_offset = 0.0
    xfade_dur = min(crossfade_duration, 0.3)

    for i in range(1, n):
        prev_dur = valid_timings[i - 1].duration
        offset = cumulative_offset + prev_dur - xfade_dur

        if offset < 0:
            offset = max(0, cumulative_offset + prev_dur - 0.1)
            xfade_dur = cumulative_offset + prev_dur - offset

        out_label = f"[xf{i}]" if i < n - 1 else "[vout]"
        filter_parts.append(
            f"{current}[v{i}]xfade=transition=fade:duration={xfade_dur:.3f}"
            f":offset={offset:.3f}{out_label}"
        )
        cumulative_offset = offset
        current = out_label

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]

    print(f"  [{_ts()}] Running ffmpeg slideshow assembly...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [{_ts()}] ERROR: ffmpeg slideshow failed: {result.stderr[-800:]}")
        return _fallback_concat_slideshow(valid_timings, output_path, width, height, fps)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Slideshow assembled: {output_path.name} ({size_mb:.1f} MB)")
    return True


def _single_image_video(
    timing: ImageTiming,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
) -> bool:
    """Create video from a single image with Ken Burns effect."""
    d_frames = int(timing.duration * fps)
    zp = _zoompan_filter("slow_zoom_in", d_frames, width, height, fps)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{timing.duration:.3f}",
        "-i", str(timing.image_path),
        "-vf", f"scale=8000:-1,{zp},format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [{_ts()}] ERROR: single image video failed: {result.stderr[-500:]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Single-image video: {output_path.name} ({size_mb:.1f} MB)")
    return True


def _fallback_concat_slideshow(
    timings: list[ImageTiming],
    output_path: Path,
    width: int,
    height: int,
    fps: int,
) -> bool:
    """Simpler fallback: generate each image as a clip, then concat without xfade."""
    print(f"  [{_ts()}] Falling back to simple concat slideshow (no crossfades)...")

    tmp_dir = output_path.parent / "_slideshow_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []

    for i, t in enumerate(timings):
        clip_path = tmp_dir / f"slide_{i:03d}.mp4"
        d_frames = int(t.duration * fps)
        effect = _EFFECTS[i % len(_EFFECTS)]
        zp = _zoompan_filter(effect, d_frames, width, height, fps)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", f"{t.duration:.3f}",
            "-i", str(t.image_path),
            "-vf", f"scale=8000:-1,{zp},format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            str(clip_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            clip_paths.append(clip_path)

    if not clip_paths:
        print(f"  [{_ts()}] ERROR: No slide clips generated")
        return False

    concat_file = tmp_dir / "concat.txt"
    concat_file.write_text("\n".join(f"file '{p}'" for p in clip_paths))

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "copy",
        "-an",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    for f in tmp_dir.iterdir():
        f.unlink(missing_ok=True)
    tmp_dir.rmdir()

    if result.returncode != 0:
        print(f"  [{_ts()}] ERROR: concat fallback failed: {result.stderr[-500:]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Slideshow (concat fallback): {output_path.name} ({size_mb:.1f} MB)")
    return True
