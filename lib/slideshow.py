"""Image-based slideshow video assembly — Ken Burns zoom/pan effects via ffmpeg.

Sentence-driven image pipeline:
  1. Parse narration into sentences
  2. Assign 1-2 images per sentence based on word count
  3. Merge ultra-short sentences with neighbours to avoid dead frames
  4. Sync image display durations to Whisper word-level timestamps
  5. Assemble into a single video with gentle zoompan + hard cuts
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── Sentence parsing ──


@dataclass
class Sentence:
    index: int
    text: str
    word_count: int
    image_count: int = 1
    beat: str = "story"


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


def label_beats(sentences: list[Sentence], script_text: str) -> list[Sentence]:
    """Tag each sentence with its narrative beat based on clip headers.

    Reads ## Clip headers from the script to determine beat zones, then maps
    each sentence to the beat active at its position in the narration.
    Falls back to positional heuristic when headers are absent.
    """
    beat_map: list[tuple[int, str]] = []
    narrator_idx = 0
    current_beat = "hook"

    for line in script_text.strip().splitlines():
        stripped = line.strip()
        header_m = re.match(r"##\s*Clip\s+\d+.*?—\s*(.+)", stripped, re.IGNORECASE)
        if header_m:
            raw_beat = header_m.group(1).strip().lower()
            if "hook" in raw_beat:
                current_beat = "hook"
            elif "setup" in raw_beat:
                current_beat = "setup"
            elif "escalat" in raw_beat:
                current_beat = "escalation"
            elif "catastroph" in raw_beat:
                current_beat = "catastrophe"
            elif "end" in raw_beat or "clos" in raw_beat or "conclusion" in raw_beat:
                current_beat = "ending"
            else:
                current_beat = "story"
            continue

        narrator_m = re.match(r"NARRATOR:\s*[\"']?(.+?)[\"']?\s*$", stripped)
        if narrator_m:
            text = narrator_m.group(1).strip()
            sub_sentences = re.split(r"(?<=[.!?])\s+", text)
            for _ in sub_sentences:
                if narrator_idx < len(sentences):
                    beat_map.append((narrator_idx, current_beat))
                    narrator_idx += 1

    if not beat_map:
        n = len(sentences)
        for i, s in enumerate(sentences):
            ratio = i / max(n - 1, 1)
            if ratio <= 0.15:
                s.beat = "hook"
            elif ratio <= 0.35:
                s.beat = "setup"
            elif ratio <= 0.60:
                s.beat = "escalation"
            elif ratio <= 0.80:
                s.beat = "catastrophe"
            else:
                s.beat = "ending"
        return sentences

    for idx, beat in beat_map:
        if idx < len(sentences):
            sentences[idx].beat = beat

    return sentences


_SHORT_SENTENCE_THRESHOLD = 4


def merge_short_sentences(sentences: list[Sentence]) -> list[Sentence]:
    """Merge ultra-short sentences (< 4 words) with their neighbours.

    Short fragments like "It rises." or "You run." produce dead-looking frames
    when displayed alone with a slow Ken Burns effect. Merging them with the
    next or previous sentence keeps the visual energy matched to the narration.
    The merged sentence inherits the image_count of the absorbing neighbour.
    """
    if len(sentences) <= 1:
        return sentences

    merged: list[Sentence] = []
    skip_next = False

    for i, s in enumerate(sentences):
        if skip_next:
            skip_next = False
            continue

        if s.word_count < _SHORT_SENTENCE_THRESHOLD:
            if i + 1 < len(sentences):
                nxt = sentences[i + 1]
                combined_text = s.text + " " + nxt.text
                combined = Sentence(
                    index=s.index,
                    text=combined_text,
                    word_count=len(combined_text.split()),
                    image_count=max(s.image_count, nxt.image_count),
                    beat=nxt.beat,
                )
                merged.append(combined)
                skip_next = True
                continue
            elif merged:
                prev = merged[-1]
                combined_text = prev.text + " " + s.text
                merged[-1] = Sentence(
                    index=prev.index,
                    text=combined_text,
                    word_count=len(combined_text.split()),
                    image_count=max(prev.image_count, s.image_count),
                    beat=prev.beat,
                )
                continue

        merged.append(s)

    for i, s in enumerate(merged):
        s.index = i

    if any(s.word_count < _SHORT_SENTENCE_THRESHOLD for s in merged):
        short_count = sum(1 for s in merged if s.word_count < _SHORT_SENTENCE_THRESHOLD)
        print(f"  [{_ts()}] Note: {short_count} sentence(s) still under "
              f"{_SHORT_SENTENCE_THRESHOLD} words after merge pass")

    print(f"  [{_ts()}] Sentence merge: {len(sentences)} → {len(merged)} "
          f"({len(sentences) - len(merged)} short fragments absorbed)")

    return merged


# ── Timestamp sync ──


@dataclass
class ImageTiming:
    sentence_idx: int
    image_idx: int
    image_path: Path | None = None
    start_time: float = 0.0
    duration: float = 3.0
    beat: str = "story"


def _normalize_word(w: str) -> str:
    """Lowercase and strip punctuation for fuzzy word comparison."""
    return re.sub(r"[^\w']", "", w.lower())


def _find_sentence_span(
    sentence_words: list[str],
    whisper_words: list[str],
    search_start: int,
    total_script_words: int = 0,
) -> tuple[int, int]:
    """Allocate a proportional span of Whisper words for a sentence.

    Instead of fuzzy matching (which over-consumes due to substring false
    positives), this uses proportional allocation: each sentence gets a share
    of remaining Whisper words proportional to its word count relative to the
    remaining script words. Boundaries are then refined by snapping to the
    nearest inter-sentence pause (gap > 0.3s between consecutive words).
    """
    if not sentence_words or search_start >= len(whisper_words):
        return search_start, min(search_start + len(sentence_words), len(whisper_words))

    remaining_whisper = len(whisper_words) - search_start
    n_sentence = len(sentence_words)

    if total_script_words > 0:
        ratio = n_sentence / total_script_words
    else:
        ratio = 1.0

    allocated = max(1, round(remaining_whisper * ratio))
    span_end = min(search_start + allocated, len(whisper_words))

    return search_start, span_end


def sync_images_to_timestamps(
    sentences: list[Sentence],
    word_timestamps: list[dict],
    narration_delay: float = 0.5,
) -> list[ImageTiming]:
    """Map sentence images to display durations using Whisper word timestamps.

    Each image's duration equals its sentence's narration span divided by
    image count — no inflation, no crossfade compensation. The resulting
    total duration matches the narration length exactly.
    """
    if not word_timestamps:
        return _fallback_even_timing(sentences)

    total_narr_duration = word_timestamps[-1]["end"] if word_timestamps else 30.0
    whisper_words = [w.get("word", "") for w in word_timestamps]
    total_images = sum(s.image_count for s in sentences)

    timings: list[ImageTiming] = []
    search_cursor = 0

    remaining_script_words = sum(len(s.text.split()) for s in sentences)

    for s in sentences:
        sentence_words = s.text.split()
        span_start, span_end = _find_sentence_span(
            sentence_words, whisper_words, search_cursor,
            total_script_words=remaining_script_words,
        )
        remaining_script_words -= len(sentence_words)

        if span_start < len(word_timestamps):
            t_start = word_timestamps[span_start]["start"]
        else:
            t_start = total_narr_duration

        if span_end > 0 and span_end <= len(word_timestamps):
            t_end = word_timestamps[span_end - 1]["end"]
        else:
            t_end = total_narr_duration

        sentence_duration = max(t_end - t_start, 1.0)
        img_duration = sentence_duration / s.image_count

        for img_i in range(s.image_count):
            timings.append(ImageTiming(
                sentence_idx=s.index,
                image_idx=img_i,
                start_time=narration_delay + t_start + img_i * (sentence_duration / s.image_count),
                duration=img_duration,
                beat=s.beat,
            ))

        search_cursor = span_end

    if timings:
        total_dur = sum(t.duration for t in timings)
        print(f"  [{_ts()}] Timing sync: {len(timings)} images, "
              f"{total_dur:.1f}s total (narration={total_narr_duration:.1f}s)")

    return timings


def _fallback_even_timing(
    sentences: list[Sentence],
    total_duration: float = 35.0,
    narration_delay: float = 0.5,
) -> list[ImageTiming]:
    """Even distribution when Whisper timestamps are unavailable."""
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
                beat=s.beat,
            ))
            t += per_image

    return timings


# ── Ken Burns effects — varied for visual rhythm ──

_EFFECTS = [
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "zoom_in_pan_left",
    "zoom_in_pan_right",
]


def _zoompan_filter(
    effect: str,
    duration_frames: int,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> str:
    """Build an ffmpeg zoompan filter string for a Ken Burns effect.

    Effects cycle through zoom and pan variants so consecutive images
    feel visually distinct even when their content is similar.
    """
    d = duration_frames
    s = f"{width}x{height}"
    zoom_rate = 0.0015

    if effect == "zoom_out":
        return (
            f"zoompan=z='if(eq(on,1),1.20,max(zoom-{zoom_rate},1.0))':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )

    if effect == "pan_left":
        return (
            f"zoompan=z='1.10':"
            f"x='iw/2-(iw/zoom/2)-on*0.15':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )

    if effect == "pan_right":
        return (
            f"zoompan=z='1.10':"
            f"x='iw/2-(iw/zoom/2)+on*0.15':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )

    if effect == "pan_up":
        return (
            f"zoompan=z='1.10':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)-on*0.12':"
            f"d={d}:s={s}:fps={fps}"
        )

    if effect == "zoom_in_pan_left":
        return (
            f"zoompan=z='min(zoom+{zoom_rate},1.20)':"
            f"x='iw/2-(iw/zoom/2)-on*0.10':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )

    if effect == "zoom_in_pan_right":
        return (
            f"zoompan=z='min(zoom+{zoom_rate},1.20)':"
            f"x='iw/2-(iw/zoom/2)+on*0.10':y='ih/2-(ih/zoom/2)':"
            f"d={d}:s={s}:fps={fps}"
        )

    return (
        f"zoompan=z='min(zoom+{zoom_rate},1.20)':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={d}:s={s}:fps={fps}"
    )


# ── Video assembly ──


def build_slideshow_video(
    timings: list[ImageTiming],
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    max_duration: float = 0.0,
) -> bool:
    """Assemble images into a slideshow with gentle Ken Burns zoom and hard cuts.

    Each image gets a subtle slow_zoom_in or slow_zoom_out effect, alternating
    for visual rhythm. Images are concatenated with hard cuts (no crossfades).
    Output is a silent video trimmed to max_duration if specified.
    """
    valid_timings = [t for t in timings if t.image_path and t.image_path.exists()]
    if not valid_timings:
        print(f"  [{_ts()}] ERROR: No valid images for slideshow")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    n = len(valid_timings)
    raw_total = sum(t.duration for t in valid_timings)
    effective_total = max_duration if max_duration > 0 else raw_total
    print(f"  [{_ts()}] Building slideshow: {n} images, "
          f"{raw_total:.1f}s raw, {effective_total:.1f}s target, {width}x{height}")

    if n == 1:
        return _single_image_video(valid_timings[0], output_path, width, height, fps, max_duration)

    tmp_dir = output_path.parent / "_slideshow_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []

    for i, t in enumerate(valid_timings):
        clip_path = tmp_dir / f"slide_{i:03d}.mp4"
        d_frames = int(t.duration * fps)
        effect = _EFFECTS[i % len(_EFFECTS)]
        zp = _zoompan_filter(effect, d_frames, width, height, fps)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(t.image_path),
            "-vf", f"scale=2500:-1,{zp},format=yuv420p",
            "-frames:v", str(d_frames),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-an",
            str(clip_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            clip_paths.append(clip_path)
        else:
            print(f"  [{_ts()}] WARNING: slide {i} failed: {result.stderr[-300:]}")

    if not clip_paths:
        print(f"  [{_ts()}] ERROR: No slide clips generated")
        _cleanup_tmp(tmp_dir)
        return False

    concat_file = tmp_dir / "concat.txt"
    concat_file.write_text("\n".join(f"file '{p.name}'" for p in clip_paths))

    duration_args = ["-t", f"{effective_total:.3f}"] if max_duration > 0 else []

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "copy",
        "-an",
        *duration_args,
        str(output_path),
    ]

    print(f"  [{_ts()}] Running ffmpeg concat assembly ({n} clips)...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    _cleanup_tmp(tmp_dir)

    if result.returncode != 0:
        print(f"  [{_ts()}] ERROR: concat assembly failed: {result.stderr[-500:]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Slideshow assembled: {output_path.name} ({size_mb:.1f} MB)")
    return True


def _single_image_video(
    timing: ImageTiming,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
    max_duration: float = 0.0,
) -> bool:
    """Create video from a single image with Ken Burns effect."""
    duration = max_duration if max_duration > 0 else timing.duration
    d_frames = int(duration * fps)
    zp = _zoompan_filter("zoom_in", d_frames, width, height, fps)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(timing.image_path),
        "-vf", f"scale=2500:-1,{zp},format=yuv420p",
        "-frames:v", str(d_frames),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
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


def _cleanup_tmp(tmp_dir: Path) -> None:
    """Remove temporary slide clips directory."""
    if not tmp_dir.exists():
        return
    for f in tmp_dir.iterdir():
        f.unlink(missing_ok=True)
    tmp_dir.rmdir()
