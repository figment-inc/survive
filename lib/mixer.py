"""ffmpeg video utilities — stitching with LUFS normalization, frame extraction, chain splitting, audio chunking."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TypedDict


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


NARRATION_DELAY = 0.5
NARRATION_BUFFER = 0.3
MAX_ATEMPO = 1.25

ASS_HEADER = """[Script Info]
Title: Episode Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,90,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,5,2,5,40,40,480,1
Style: Highlight,Montserrat,90,&H0000D5FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,5,2,5,40,40,480,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def probe_audio_duration(file_path: Path) -> float:
    """Get duration of an audio/video file in seconds using ffprobe.

    Uses stream-level duration (more accurate than container/format duration
    which can be off by 20-50ms due to AAC encoder priming samples).
    """
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "stream=duration",
        "-of", "csv=p=0",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return 0.0
    durations = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line and line != "N/A":
            try:
                durations.append(float(line))
            except ValueError:
                continue
    if not durations:
        cmd_fallback = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(file_path),
        ]
        result = subprocess.run(cmd_fallback, capture_output=True, text=True)
        if result.returncode != 0 or not result.stdout.strip():
            return 0.0
        return float(result.stdout.strip())
    return max(durations)


class WordTimestamp(TypedDict):
    word: str
    start: float
    end: float


def whisper_word_timestamps(
    audio_path: Path,
    openai_api_key: str,
) -> list[WordTimestamp]:
    """Get word-level timestamps from an audio file using OpenAI Whisper API.

    Returns a list of {word, start, end} dicts with timestamps in seconds.
    """
    import requests as _requests

    print(f"  [{_ts()}] Running Whisper word-level transcription on {audio_path.name}...")
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {openai_api_key}"}

    with open(audio_path, "rb") as f:
        resp = _requests.post(
            url,
            headers=headers,
            files={"file": (audio_path.name, f, "audio/mpeg")},
            data={
                "model": "whisper-1",
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
            },
            timeout=120,
        )
    resp.raise_for_status()
    data = resp.json()

    words: list[WordTimestamp] = []
    for w in data.get("words", []):
        words.append(WordTimestamp(
            word=w["word"],
            start=float(w["start"]),
            end=float(w["end"]),
        ))

    print(f"  [{_ts()}] Whisper returned {len(words)} word timestamps "
          f"(duration: {words[-1]['end']:.1f}s)" if words else "")
    return words


def chunk_narration_audio(
    full_audio_path: Path,
    word_timestamps: list[WordTimestamp],
    clip_durations: list[tuple[str, float]],
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Split a continuous narration audio file into per-clip chunks.

    Uses word-level timestamps to determine split points. Each clip gets
    a proportional share of words based on clip duration relative to total
    video duration. Words are assigned greedily — the split happens at the
    word boundary closest to the ideal time-proportional split point.

    Narration that runs longer than video is distributed across all clips,
    so each clip's audio chunk may exceed its video duration. The mixer
    handles this by letting the narration play through the clip boundary
    (since clips are stitched into one continuous video anyway).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if not word_timestamps:
        print(f"  [{_ts()}] WARNING: No word timestamps — cannot chunk narration")
        return []

    total_video_duration = sum(dur for _, dur in clip_durations)
    total_narration_duration = word_timestamps[-1]["end"]
    total_words = len(word_timestamps)

    print(f"  [{_ts()}] Chunking narration: {total_words} words, "
          f"{total_narration_duration:.1f}s audio across "
          f"{len(clip_durations)} clips ({total_video_duration:.0f}s video)")

    split_points: list[int] = []
    cumulative_dur = 0.0
    word_idx = 0

    for i, (clip_id, clip_dur) in enumerate(clip_durations[:-1]):
        cumulative_dur += clip_dur
        target_time = (cumulative_dur / total_video_duration) * total_narration_duration

        best_idx = word_idx
        best_dist = abs(word_timestamps[word_idx]["end"] - target_time)
        for j in range(word_idx, min(total_words, word_idx + total_words // 2)):
            dist = abs(word_timestamps[j]["end"] - target_time)
            if dist < best_dist:
                best_dist = dist
                best_idx = j

        split_points.append(best_idx + 1)
        word_idx = best_idx + 1

    chunk_ranges: list[tuple[int, int]] = []
    start = 0
    for sp in split_points:
        chunk_ranges.append((start, sp))
        start = sp
    chunk_ranges.append((start, total_words))

    output_paths: list[Path] = []
    for i, ((clip_id, _), (w_start, w_end)) in enumerate(
        zip(clip_durations, chunk_ranges)
    ):
        out_path = output_dir / f"clip_{clip_id}.mp3"
        output_paths.append(out_path)

        if out_path.exists() and not force:
            print(f"  [{_ts()}] Skipping chunk (exists): {out_path.name}")
            continue

        if w_start >= w_end:
            print(f"  [{_ts()}] WARNING: Empty chunk for clip {clip_id}")
            continue

        audio_start = word_timestamps[w_start]["start"]
        audio_end = word_timestamps[w_end - 1]["end"]
        chunk_words = [word_timestamps[j]["word"] for j in range(w_start, w_end)]

        cmd = [
            "ffmpeg", "-y",
            "-i", str(full_audio_path),
            "-ss", f"{audio_start:.3f}",
            "-to", f"{audio_end:.3f}",
            "-c", "copy",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR chunking clip {clip_id}: {result.stderr[-300:]}")
            continue

        print(f"  [{_ts()}] Chunk clip_{clip_id}: words {w_start}-{w_end-1} "
              f"({audio_start:.1f}s-{audio_end:.1f}s, {w_end - w_start} words)")

    return output_paths


def _extend_video_with_freeze(video_path: Path, target_duration: float, extended_path: Path) -> bool:
    """Extend a video to target_duration by freeze-framing the last frame."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"tpad=stop_mode=clone:stop_duration={target_duration}",
        "-t", str(target_duration),
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        str(extended_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING: freeze-frame extension failed: {result.stderr[-300:]}")
        return False
    return True


def extract_last_frame(video_path: Path, output_path: Path) -> bool:
    """Extract the last frame of a video as a PNG image."""
    cmd = [
        "ffmpeg", "-y",
        "-sseof", "-0.1",
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "1",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING: Could not extract last frame from {video_path.name}")
        return False
    print(f"  [{_ts()}] Extracted last frame: {output_path.name}")
    return True


def mix_clip_veo_only(
    video_path: Path,
    output_path: Path,
    clip_duration: float = 8.0,
    veo_audio_volume: float = 0.15,
    force: bool = False,
) -> tuple[bool, float]:
    """Prepare a single clip with only Veo ambient audio at reduced volume.

    Narration and music are NOT mixed here — they are overlaid on the
    final stitched video via mix_final_audio() so narration flows
    unbroken across clip boundaries.
    """
    if output_path.exists() and not force:
        print(f"  [{_ts()}] Skipping (exists): {output_path.name}")
        return True, clip_duration

    if not video_path.exists():
        print(f"  WARNING: No video at {video_path}, skipping mix")
        return False, clip_duration

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-af", f"volume={veo_audio_volume}",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{clip_duration:.2f}",
        str(output_path),
    ]

    print(f"  [{_ts()}] Mixing {output_path.stem}: veo-only (vol={veo_audio_volume}, dur={clip_duration:.1f}s)")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR mixing: {result.stderr[-500:]}")
        return False, clip_duration

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Mixed: {output_path.name} ({size_mb:.1f} MB)")
    return True, clip_duration


def mix_clip_audio(
    video_path: Path,
    output_path: Path,
    narration_path: Path | None = None,
    music_path: Path | None = None,
    clip_duration: float = 8.0,
    narration_duration: float = 0.0,
    music_offset: float = 0.0,
    music_volume: float = 0.20,
    veo_audio_volume: float = 0.15,
    force: bool = False,
) -> tuple[bool, float]:
    """Mix a single clip: keep Veo native audio + layer narration + music.

    Returns (success, effective_duration).

    NOTE: For the new continuous-narration pipeline, use mix_clip_veo_only()
    per-clip and mix_final_audio() on the stitched video instead.
    """
    if output_path.exists() and not force:
        print(f"  [{_ts()}] Skipping (exists): {output_path.name}")
        return True, clip_duration

    if not video_path.exists():
        print(f"  WARNING: No video at {video_path}, skipping mix")
        return False, clip_duration

    output_path.parent.mkdir(parents=True, exist_ok=True)

    has_narration = narration_path and narration_path.exists()
    has_music = music_path and music_path.exists()

    max_narr_dur = clip_duration - NARRATION_DELAY - NARRATION_BUFFER
    video_dur = clip_duration
    speedup = 1.0
    actual_narration_path = narration_path

    if has_narration and narration_duration > max_narr_dur:
        ratio = (narration_duration + NARRATION_DELAY + NARRATION_BUFFER) / video_dur
        if ratio <= MAX_ATEMPO:
            speedup = ratio
            print(f"  [{_ts()}] Narration {narration_duration:.1f}s > clip {video_dur:.0f}s — "
                  f"speeding up narration {speedup:.2f}x")
        else:
            trimmed_path = narration_path.parent / f"{narration_path.stem}_trimmed.mp3"
            trim_cmd = [
                "ffmpeg", "-y",
                "-i", str(narration_path),
                "-t", f"{max_narr_dur:.3f}",
                "-c", "copy",
                str(trimmed_path),
            ]
            result = subprocess.run(trim_cmd, capture_output=True, text=True)
            if result.returncode == 0 and trimmed_path.exists():
                print(f"  [{_ts()}] Narration {narration_duration:.1f}s >> clip {video_dur:.0f}s — "
                      f"trimmed to {max_narr_dur:.1f}s (last words may be cut)")
                actual_narration_path = trimmed_path
                narration_duration = max_narr_dur
            else:
                print(f"  [{_ts()}] WARNING: trim failed, clamping atempo to {MAX_ATEMPO}x")
                speedup = MAX_ATEMPO

    effective_dur = clip_duration

    inputs = ["-i", str(video_path)]
    filter_parts: list[str] = []
    audio_streams: list[str] = []
    stream_idx = 1

    has_veo_audio = True
    if has_veo_audio:
        veo_vol = veo_audio_volume if has_narration else 0.30
        filter_parts.append(f"[0:a]volume={veo_vol},apad[veo]")
        audio_streams.append("[veo]")

    if has_narration:
        inputs.extend(["-i", str(actual_narration_path)])
        narr_filters = f"adelay={int(NARRATION_DELAY * 1000)}|{int(NARRATION_DELAY * 1000)}"
        if speedup > 1.0:
            narr_filters += f",atempo={speedup:.4f}"
        narr_filters += ",volume=1.0,apad"
        filter_parts.append(f"[{stream_idx}:a]{narr_filters}[narr]")
        audio_streams.append("[narr]")
        stream_idx += 1

    if has_music:
        inputs.extend(["-i", str(music_path)])
        filter_parts.append(
            f"[{stream_idx}:a]atrim=start={music_offset:.2f}:duration={effective_dur:.2f},"
            f"asetpts=PTS-STARTPTS,volume={music_volume},apad[mus]"
        )
        audio_streams.append("[mus]")
        stream_idx += 1

    mix_count = len(audio_streams)
    streams_str = "".join(audio_streams)
    filter_parts.append(f"{streams_str}amix=inputs={mix_count}:duration=first:normalize=0[a]")
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{effective_dur:.2f}",
        str(output_path),
    ]

    mode = "normal"
    if speedup > 1.0:
        mode = f"atempo {speedup:.2f}x"
    elif actual_narration_path != narration_path:
        mode = "narration trimmed"

    print(f"  [{_ts()}] Mixing {output_path.stem}: "
          f"veo={'yes'} narr={'yes' if has_narration else 'no'} "
          f"music={'yes' if has_music else 'no'} "
          f"(mode={mode}, dur={effective_dur:.1f}s)")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR mixing: {result.stderr[-500:]}")
        return False, clip_duration

    if actual_narration_path and actual_narration_path != narration_path and actual_narration_path.exists():
        actual_narration_path.unlink()

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Mixed: {output_path.name} ({size_mb:.1f} MB)")
    return True, effective_dur


def _format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp format (H:MM:SS.cc)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_word_captions(
    narration_text: str,
    narration_duration: float,
    output_path: Path,
    narration_delay: float = NARRATION_DELAY,
) -> bool:
    """Generate an ASS subtitle file with TikTok-style word-by-word captions.

    Shows 1-3 words at a time centered on screen, with the active word
    highlighted in yellow/orange and text in uppercase for punchy readability.
    """
    words = narration_text.split()
    if not words:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    word_duration = narration_duration / len(words)
    lines: list[str] = []

    for i, word in enumerate(words):
        start_time = narration_delay + i * word_duration
        end_time = narration_delay + (i + 1) * word_duration

        context_start = max(0, i - 1)
        context_end = min(len(words), i + 2)
        parts: list[str] = []
        for j in range(context_start, context_end):
            w = words[j].upper()
            if j == i:
                parts.append(r"{\c&H00D5FF&}" + w + r"{\c&HFFFFFF&}")
            else:
                parts.append(w)

        display_text = " ".join(parts)
        ass_start = _format_ass_time(start_time)
        ass_end = _format_ass_time(end_time)
        lines.append(
            f"Dialogue: 0,{ass_start},{ass_end},Default,,0,0,0,,{display_text}"
        )

    ass_content = ASS_HEADER + "\n".join(lines) + "\n"
    output_path.write_text(ass_content)
    print(f"  [{_ts()}] Generated captions: {output_path.name} ({len(words)} words)")
    return True


def burn_captions(
    video_path: Path,
    captions_path: Path,
    output_path: Path,
    force: bool = False,
) -> bool:
    """Burn ASS captions into a video file using ffmpeg."""
    if output_path.exists() and not force:
        print(f"  [{_ts()}] Skipping (exists): {output_path.name}")
        return True

    if not video_path.exists():
        print(f"  WARNING: No video at {video_path}, skipping caption burn")
        return False

    if not captions_path.exists():
        print(f"  WARNING: No captions at {captions_path}, skipping caption burn")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    escaped_path = str(captions_path).replace("\\", "/").replace(":", r"\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"ass='{escaped_path}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path),
    ]

    print(f"  [{_ts()}] Burning captions into {output_path.stem}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR burning captions: {result.stderr[-500:]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Captioned: {output_path.name} ({size_mb:.1f} MB)")
    return True


def split_chain_video(
    video_path: Path,
    clip_durations: list[tuple[str, float]],
    output_dir: Path,
    force: bool = False,
) -> list[Path]:
    """Split a single continuous chain video into per-clip segments.

    Args:
        video_path: Path to the chain video produced by Veo extension chain.
        clip_durations: List of (clip_id, duration_seconds) in order.
        output_dir: Directory to write individual clip files.
        force: Re-split even if output files exist.

    Returns:
        List of paths to the split clip files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    split_paths: list[Path] = []
    offset = 0.0

    for clip_id, duration in clip_durations:
        out_path = output_dir / f"clip_{clip_id}.mp4"
        split_paths.append(out_path)

        if out_path.exists() and not force:
            print(f"  [{_ts()}] Skipping split (exists): {out_path.name}")
            offset += duration
            continue

        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{offset:.3f}",
            "-i", str(video_path),
            "-t", f"{duration:.3f}",
            "-c:v", "copy",
            "-c:a", "copy",
            str(out_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR splitting clip {clip_id}: {result.stderr[-300:]}")
        else:
            size_mb = out_path.stat().st_size / (1024 * 1024)
            print(f"  [{_ts()}] Split: {out_path.name} "
                  f"(offset={offset:.1f}s, dur={duration:.1f}s, {size_mb:.1f} MB)")

        offset += duration

    return split_paths


def trim_video(video_path: Path, output_path: Path, target_seconds: float) -> bool:
    """Trim a video to a target duration using stream copy (no re-encode)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-t", f"{target_seconds:.3f}",
        "-c", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR trimming: {result.stderr[-300:]}")
        return False
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Trimmed to {target_seconds:.0f}s: {output_path.name} ({size_mb:.1f} MB)")
    return True


def stitch_clips(clip_paths: list[Path], output_path: Path) -> bool:
    """Concatenate clips into a final video with LUFS normalization.

    Two-pass approach:
      1. ffmpeg concat demuxer to join all clips
      2. loudnorm filter to normalize audio to -14 LUFS / -1.0 dBTP
    """
    if not clip_paths:
        print("  ERROR: No clips to stitch.")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output_path.parent / "concat_list.txt"
    concat_file.write_text("\n".join(f"file '{p}'" for p in clip_paths))

    raw_concat = output_path.parent / f"raw_concat_{output_path.stem}.mp4"
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(raw_concat),
    ]

    print(f"\n  [{_ts()}] Stitching {len(clip_paths)} clips...")
    result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: concat failed: {result.stderr[:500]}")
        concat_file.unlink(missing_ok=True)
        return False

    cmd_norm = [
        "ffmpeg", "-y",
        "-i", str(raw_concat),
        "-c:v", "copy",
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]

    print(f"  [{_ts()}] Normalizing to -14 LUFS...")
    result = subprocess.run(cmd_norm, capture_output=True, text=True)

    concat_file.unlink(missing_ok=True)
    raw_concat.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  ERROR: normalization failed: {result.stderr[:500]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Final video: {output_path} ({size_mb:.1f} MB)")
    return True


def stitch_clips_with_transitions(
    clip_paths: list[Path],
    output_path: Path,
    crossfade_duration: float = 0.3,
    hook_crossfade: float = 0.5,
    outro_fade: float = 1.5,
) -> bool:
    """Concatenate clips with crossfade transitions and LUFS normalization.

    Applies xfade crossfades between clips and a dip-to-black on the
    final clip. Falls back to hard-cut stitch_clips() on failure.
    """
    if not clip_paths:
        print("  ERROR: No clips to stitch.")
        return False

    if len(clip_paths) < 2:
        return stitch_clips(clip_paths, output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    inputs: list[str] = []
    for p in clip_paths:
        inputs.extend(["-i", str(p)])

    durations: list[float] = []
    for p in clip_paths:
        durations.append(probe_audio_duration(p))

    vf_parts: list[str] = []
    af_parts: list[str] = []
    n = len(clip_paths)

    cumulative_offset = 0.0
    current_video = "[0:v]"
    current_audio = "[0:a]"

    for i in range(1, n):
        fade_dur = hook_crossfade if i == 1 else crossfade_duration
        offset = cumulative_offset + durations[i - 1] - fade_dur

        if offset < 0:
            offset = max(0, cumulative_offset + durations[i - 1] - 0.1)
            fade_dur = cumulative_offset + durations[i - 1] - offset

        out_v = f"[v{i}]" if i < n - 1 else "[vmerged]"
        out_a = f"[a{i}]" if i < n - 1 else "[amerged]"

        vf_parts.append(
            f"{current_video}[{i}:v]xfade=transition=fade:duration={fade_dur:.3f}"
            f":offset={offset:.3f}{out_v}"
        )
        af_parts.append(
            f"{current_audio}[{i}:a]acrossfade=d={fade_dur:.3f}:c1=tri:c2=tri{out_a}"
        )

        cumulative_offset = offset
        current_video = out_v
        current_audio = out_a

    if outro_fade > 0:
        total_dur = cumulative_offset + durations[-1]
        fade_start = max(0, total_dur - outro_fade)
        vf_parts.append(f"[vmerged]fade=t=out:st={fade_start:.3f}:d={outro_fade:.3f}[vout]")
        af_parts.append(f"[amerged]afade=t=out:st={fade_start:.3f}:d={outro_fade:.3f}[aout]")
        final_v = "[vout]"
        final_a = "[aout]"
    else:
        final_v = "[vmerged]"
        final_a = "[amerged]"

    filter_complex = ";".join(vf_parts + af_parts)

    raw_xfade = output_path.parent / f"raw_xfade_{output_path.stem}.mp4"
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", final_v,
        "-map", final_a,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(raw_xfade),
    ]

    print(f"\n  [{_ts()}] Stitching {n} clips with crossfade transitions "
          f"(xfade={crossfade_duration}s, hook={hook_crossfade}s, outro={outro_fade}s)...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING: xfade stitch failed: {result.stderr[-500:]}")
        print(f"  [{_ts()}] Falling back to hard-cut stitch...")
        raw_xfade.unlink(missing_ok=True)
        return stitch_clips(clip_paths, output_path)

    cmd_norm = [
        "ffmpeg", "-y",
        "-i", str(raw_xfade),
        "-c:v", "copy",
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]

    print(f"  [{_ts()}] Normalizing to -14 LUFS...")
    result = subprocess.run(cmd_norm, capture_output=True, text=True)
    raw_xfade.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  ERROR: normalization failed: {result.stderr[:500]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Final video (with transitions): {output_path} ({size_mb:.1f} MB)")
    return True


def _escape_drawtext(text: str) -> str:
    """Escape a string for ffmpeg drawtext filter."""
    return text.replace("'", "'\\''").replace(":", "\\:")


def _location_fontsize(location: str) -> int:
    """Pick a fontsize that keeps the location line within 1080px frame width."""
    n = len(location)
    if n <= 18:
        return 56
    if n <= 26:
        return 44
    return 36


def validate_narration_timing(
    narration_path: Path,
    video_duration: float,
    narration_delay: float = NARRATION_DELAY,
) -> float:
    """Check if narration fits within the video and return the required atempo rate.

    Probes the actual narration MP3 duration and compares it against the
    available time window (video_duration - narration_delay). Returns:
      1.0  if narration fits
      >1.0 if atempo speedup is needed (capped at MAX_ATEMPO)

    Logs warnings for any overflow.
    """
    narr_duration = probe_audio_duration(narration_path)
    available = video_duration - narration_delay
    overflow = narr_duration - available

    print(f"  [{_ts()}] Timing check: narration={narr_duration:.1f}s, "
          f"video={video_duration:.1f}s, available={available:.1f}s "
          f"(delay={narration_delay}s)")

    if overflow <= 0:
        print(f"  [{_ts()}] Timing OK: narration fits with {-overflow:.1f}s margin")
        return 1.0

    needed_rate = narr_duration / available
    capped_rate = min(needed_rate, MAX_ATEMPO)

    if needed_rate <= 1.15:
        print(f"  [{_ts()}] Timing: slight overflow ({overflow:.1f}s). "
              f"Applying atempo={capped_rate:.3f}x (imperceptible).")
    elif needed_rate <= MAX_ATEMPO:
        print(f"  [{_ts()}] WARNING: narration overflows by {overflow:.1f}s. "
              f"Applying atempo={capped_rate:.3f}x — may be noticeable.")
    else:
        residual = narr_duration / MAX_ATEMPO - available
        print(f"  [{_ts()}] WARNING: major overflow ({overflow:.1f}s). "
              f"Applying max atempo={MAX_ATEMPO}x but ~{residual:.1f}s of "
              f"narration will still be truncated.")

    return capped_rate


def estimate_crossfade_loss(
    num_clips: int,
    hook_crossfade: float = 0.5,
    standard_crossfade: float = 0.3,
) -> float:
    """Calculate the total video time eaten by crossfade transitions."""
    if num_clips < 2:
        return 0.0
    return hook_crossfade + max(0, num_clips - 2) * standard_crossfade


def validate_clip_narration_alignment(
    word_timestamps: list[WordTimestamp],
    clip_durations: list[tuple[str, float]],
    dialogue_lines: list[str] | None = None,
    narration_delay: float = NARRATION_DELAY,
    narration_atempo: float = 1.0,
    hook_crossfade: float = 0.5,
    standard_crossfade: float = 0.3,
    drift_threshold: float = 0.5,
) -> float:
    """Check per-clip narration alignment against visual clip boundaries.

    Computes the effective time window for each clip in the stitched video
    (accounting for crossfade losses and narration delay), then checks
    whether the Whisper-timed narration words for each clip's portion fall
    within that clip's visual window.

    Returns the maximum absolute drift (seconds) across all clips.
    Logs warnings for any clip where drift exceeds drift_threshold.
    """
    if not word_timestamps or not clip_durations:
        print(f"  [{_ts()}] Alignment check: skipped (no timestamps or clip data)")
        return 0.0

    n = len(clip_durations)

    clip_visual_starts: list[float] = []
    clip_visual_ends: list[float] = []
    cumulative = 0.0
    for i, (clip_id, dur) in enumerate(clip_durations):
        if i == 0:
            fade_loss = 0.0
        elif i == 1:
            fade_loss = hook_crossfade
        else:
            fade_loss = standard_crossfade
        start = cumulative
        cumulative += dur - (fade_loss if i > 0 else 0.0)
        clip_visual_starts.append(start)
        clip_visual_ends.append(cumulative)

    total_video_dur = cumulative
    total_narr_dur = word_timestamps[-1]["end"]
    effective_atempo = narration_atempo if narration_atempo > 1.001 else 1.0

    total_raw_clip_dur = sum(d for _, d in clip_durations)
    total_words = len(word_timestamps)

    word_idx = 0
    clip_word_ranges: list[tuple[int, int]] = []
    cumul_dur = 0.0
    for i, (clip_id, clip_dur) in enumerate(clip_durations[:-1]):
        cumul_dur += clip_dur
        target_time = (cumul_dur / total_raw_clip_dur) * total_narr_dur

        best_idx = word_idx
        best_dist = abs(word_timestamps[word_idx]["end"] - target_time)
        for j in range(word_idx, min(total_words, word_idx + total_words // 2)):
            dist = abs(word_timestamps[j]["end"] - target_time)
            if dist < best_dist:
                best_dist = dist
                best_idx = j
        clip_word_ranges.append((word_idx, best_idx + 1))
        word_idx = best_idx + 1
    clip_word_ranges.append((word_idx, total_words))

    max_drift = 0.0
    print(f"\n  [{_ts()}] Per-clip narration alignment (delay={narration_delay}s, "
          f"atempo={effective_atempo:.3f}x):")

    for i, ((clip_id, clip_dur), (w_start_idx, w_end_idx)) in enumerate(
        zip(clip_durations, clip_word_ranges)
    ):
        if w_start_idx >= w_end_idx:
            continue

        narr_start_raw = word_timestamps[w_start_idx]["start"]
        narr_end_raw = word_timestamps[w_end_idx - 1]["end"]

        narr_start_effective = narration_delay + narr_start_raw / effective_atempo
        narr_end_effective = narration_delay + narr_end_raw / effective_atempo

        visual_start = clip_visual_starts[i]
        visual_end = clip_visual_ends[i]

        start_drift = narr_start_effective - visual_start
        end_drift = narr_end_effective - visual_end
        worst_drift = max(abs(start_drift), abs(end_drift))
        max_drift = max(max_drift, worst_drift)

        status = "OK" if worst_drift <= drift_threshold else "DRIFT"
        if worst_drift > drift_threshold:
            direction = "late" if end_drift > 0 else "early"
            print(f"    Clip {clip_id}: {status} — narration {direction} by "
                  f"{worst_drift:.2f}s (visual={visual_start:.1f}-{visual_end:.1f}s, "
                  f"narr={narr_start_effective:.1f}-{narr_end_effective:.1f}s)")
        else:
            print(f"    Clip {clip_id}: {status} ({worst_drift:.2f}s drift, "
                  f"visual={visual_start:.1f}-{visual_end:.1f}s)")

    if max_drift <= drift_threshold:
        print(f"  [{_ts()}] Alignment OK: max drift {max_drift:.2f}s "
              f"(threshold={drift_threshold}s)")
    else:
        print(f"  [{_ts()}] WARNING: max drift {max_drift:.2f}s exceeds "
              f"threshold ({drift_threshold}s) — narration may play over wrong clip")

    return max_drift


def mix_final_audio(
    video_path: Path,
    output_path: Path,
    narration_path: Path | None = None,
    music_path: Path | None = None,
    narration_delay: float = NARRATION_DELAY,
    narration_atempo: float = 1.0,
    music_volume: float = 0.20,
    veo_audio_volume: float = 0.15,
    force: bool = False,
) -> bool:
    """Overlay full continuous narration + music onto a stitched video in one pass.

    Unlike mix_clip_audio (which works per-clip), this operates on the
    already-stitched video so narration flows unbroken across clip boundaries.
    narration_atempo > 1.0 speeds up narration to fit within the video duration.

    If narration still overflows after atempo, the video is extended by freezing
    the last frame so audio is never cut off mid-sentence.
    """
    if output_path.exists() and not force:
        print(f"  [{_ts()}] Skipping (exists): {output_path.name}")
        return True

    if not video_path.exists():
        print(f"  WARNING: No video at {video_path}")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    has_narration = narration_path and narration_path.exists()
    has_music = music_path and music_path.exists()

    video_duration = probe_audio_duration(video_path)

    narr_end_time = 0.0
    if has_narration:
        raw_narr_dur = probe_audio_duration(narration_path)
        effective_atempo = narration_atempo if narration_atempo > 1.001 else 1.0
        narr_end_time = narration_delay + raw_narr_dur / effective_atempo

    output_duration = max(video_duration, narr_end_time)
    needs_video_extension = narr_end_time > video_duration + 0.1
    extension_secs = narr_end_time - video_duration if needs_video_extension else 0.0

    inputs = ["-i", str(video_path)]
    filter_parts: list[str] = []
    video_filter_parts: list[str] = []
    audio_streams: list[str] = []
    stream_idx = 1

    if needs_video_extension:
        video_filter_parts.append(
            f"[0:v]tpad=stop_mode=clone:stop_duration={extension_secs:.2f}[vout]"
        )
        print(f"  [{_ts()}] Extending video by {extension_secs:.1f}s (freeze last frame) "
              f"to prevent narration cutoff")

    veo_vol = veo_audio_volume if has_narration else 0.30
    filter_parts.append(f"[0:a]asetpts=PTS-STARTPTS,volume={veo_vol},apad[veo]")
    audio_streams.append("[veo]")

    if has_narration:
        inputs.extend(["-i", str(narration_path)])
        delay_ms = int(narration_delay * 1000)
        narr_chain = []
        if narration_atempo > 1.001:
            narr_chain.append(f"atempo={narration_atempo:.4f}")
        narr_chain.append(f"adelay={delay_ms}|{delay_ms}")
        narr_chain.append("volume=1.0")
        narr_chain.append("apad")
        narr_filters = ",".join(narr_chain)
        filter_parts.append(f"[{stream_idx}:a]{narr_filters}[narr]")
        audio_streams.append("[narr]")
        stream_idx += 1

    if has_music:
        inputs.extend(["-i", str(music_path)])
        filter_parts.append(
            f"[{stream_idx}:a]atrim=start=0:duration={output_duration:.2f},"
            f"asetpts=PTS-STARTPTS,volume={music_volume},apad[mus]"
        )
        audio_streams.append("[mus]")
        stream_idx += 1

    mix_count = len(audio_streams)
    streams_str = "".join(audio_streams)
    filter_parts.append(f"{streams_str}amix=inputs={mix_count}:duration=first:normalize=0[a]")

    all_filters = video_filter_parts + filter_parts
    filter_complex = ";".join(all_filters)

    video_map = "[vout]" if needs_video_extension else "0:v"
    video_codec = ["-c:v", "libx264", "-preset", "fast", "-crf", "18"] if needs_video_extension else ["-c:v", "copy"]

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", video_map,
        "-map", "[a]",
        *video_codec,
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{output_duration:.2f}",
        str(output_path),
    ]

    tempo_str = f", atempo={narration_atempo:.3f}x" if narration_atempo > 1.001 else ""
    ext_str = f", extended +{extension_secs:.1f}s" if needs_video_extension else ""
    print(f"  [{_ts()}] Final mix: narr={'yes' if has_narration else 'no'} "
          f"music={'yes' if has_music else 'no'} "
          f"(video={video_duration:.1f}s, output={output_duration:.1f}s, "
          f"delay={narration_delay}s{tempo_str}{ext_str})")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR final mix: {result.stderr[-500:]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Final mixed: {output_path.name} ({size_mb:.1f} MB)")
    return True


def burn_location_title(
    video_path: Path,
    output_path: Path,
    location: str,
    year: str,
    duration: float = 4.0,
    fade_in: float = 0.5,
    fade_out: float = 0.5,
    force: bool = False,
) -> bool:
    """Burn a two-line location / year title card onto the first seconds of a video.

    Line 1 (location) is dynamically sized so it never overflows 1080px width.
    Line 2 (year) is rendered smaller beneath it.  Both lines are centered
    horizontally in the bottom quarter of the frame with matching fade timing.
    """
    if output_path.exists() and not force:
        print(f"  [{_ts()}] Skipping (exists): {output_path.name}")
        return True

    if not video_path.exists():
        print(f"  WARNING: No video at {video_path}, skipping location title burn")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    loc_size = _location_fontsize(location)
    year_size = int(loc_size * 0.65)
    line_gap = 8

    escaped_loc = _escape_drawtext(location)
    escaped_year = _escape_drawtext(year)

    fade_out_start = duration - fade_out
    alpha_expr = (
        f"if(lt(t,{fade_in}),t/{fade_in},"
        f"if(lt(t,{fade_out_start}),1,"
        f"if(lt(t,{duration}),(({duration}-t)/{fade_out}),0)))"
    )

    font = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    common_style = (
        f"fontfile={font}:"
        f"fontcolor=white:"
        f"borderw=4:"
        f"bordercolor=black:"
        f"shadowcolor=black@0.6:"
        f"shadowx=2:shadowy=2:"
        f"alpha='{alpha_expr}':"
        f"enable='between(t,0,{duration})'"
    )

    loc_filter = (
        f"drawtext="
        f"text='{escaped_loc}':"
        f"fontsize={loc_size}:"
        f"{common_style}:"
        f"x=(w-tw)/2:"
        f"y=h*0.86-th-{line_gap}"
    )

    year_filter = (
        f"drawtext="
        f"text='{escaped_year}':"
        f"fontsize={year_size}:"
        f"{common_style}:"
        f"x=(w-tw)/2:"
        f"y=h*0.86+{line_gap}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"{loc_filter},{year_filter}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path),
    ]

    print(f"  [{_ts()}] Burning location title: \"{location}\" / \"{year}\" "
          f"(loc_size={loc_size}, year_size={year_size}, "
          f"duration={duration}s, fade_in={fade_in}s, fade_out={fade_out}s)")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR burning location title: {result.stderr[-500:]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Location title burned: {output_path.name} ({size_mb:.1f} MB)")
    return True


def _framing_fontsize(text: str) -> int:
    """Pick a fontsize for the framing line that fits within 1080px with padding."""
    n = len(text)
    if n <= 30:
        return 42
    if n <= 45:
        return 36
    if n <= 55:
        return 30
    return 26


def burn_framing_line(
    video_path: Path,
    output_path: Path,
    framing_line: str,
    duration: float = 4.0,
    fade_in: float = 0.3,
    fade_out: float = 0.5,
    force: bool = False,
) -> bool:
    """Burn the 'You would not want to be in...' framing line onto clip 01.

    Single centered line in the lower third, with fade in/out timing.
    Applied after the location title burn on the final stitched video.
    """
    if output_path.exists() and not force:
        print(f"  [{_ts()}] Skipping (exists): {output_path.name}")
        return True

    if not video_path.exists():
        print(f"  WARNING: No video at {video_path}, skipping framing line burn")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    font_size = _framing_fontsize(framing_line)
    escaped = _escape_drawtext(framing_line)

    fade_out_start = duration - fade_out
    alpha_expr = (
        f"if(lt(t,{fade_in}),t/{fade_in},"
        f"if(lt(t,{fade_out_start}),1,"
        f"if(lt(t,{duration}),(({duration}-t)/{fade_out}),0)))"
    )

    font = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

    text_filter = (
        f"drawtext="
        f"text='{escaped}':"
        f"fontfile={font}:"
        f"fontsize={font_size}:"
        f"fontcolor=white:"
        f"borderw=3:"
        f"bordercolor=black:"
        f"shadowcolor=black@0.5:"
        f"shadowx=2:shadowy=2:"
        f"alpha='{alpha_expr}':"
        f"enable='between(t,0,{duration})':"
        f"x=(w-tw)/2:"
        f"y=h*0.72"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", text_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        str(output_path),
    ]

    print(f"  [{_ts()}] Burning framing line: \"{framing_line}\" "
          f"(size={font_size}, duration={duration}s)")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR burning framing line: {result.stderr[-500:]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Framing line burned: {output_path.name} ({size_mb:.1f} MB)")
    return True
