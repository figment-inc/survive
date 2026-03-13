"""ffmpeg audio mixing and caption generation — keeps Veo native audio, layers narration + music, burns captions."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


NARRATION_DELAY = 0.5
NARRATION_BUFFER = 0.3
MAX_ATEMPO = 1.2

ASS_HEADER = """[Script Info]
Title: Episode Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,40,40,200,1
Style: Highlight,Arial,72,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,40,40,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def probe_audio_duration(file_path: Path) -> float:
    """Get duration of an audio/video file in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return 0.0
    return float(result.stdout.strip())


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


def mix_clip_audio(
    video_path: Path,
    output_path: Path,
    narration_path: Path | None = None,
    music_path: Path | None = None,
    clip_duration: float = 8.0,
    narration_duration: float = 0.0,
    music_offset: float = 0.0,
    music_volume: float = 0.20,
    veo_audio_volume: float = 0.40,
    force: bool = False,
) -> tuple[bool, float]:
    """Mix a single clip: keep Veo native audio + layer narration + music.

    Returns (success, effective_duration).
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

    needed = narration_duration + NARRATION_DELAY + NARRATION_BUFFER if narration_duration > 0 else 0.0
    video_dur = clip_duration

    speedup = 1.0
    extend_to = 0.0
    actual_video_path = video_path

    if needed > video_dur and narration_duration > 0:
        ratio = needed / video_dur
        if ratio <= MAX_ATEMPO:
            speedup = ratio
            print(f"  [{_ts()}] Narration {narration_duration:.1f}s > clip {video_dur:.0f}s — "
                  f"speeding up narration {speedup:.2f}x")
        else:
            extend_to = needed
            print(f"  [{_ts()}] Narration {narration_duration:.1f}s >> clip {video_dur:.0f}s — "
                  f"extending video to {extend_to:.1f}s via freeze-frame")
            extended_path = output_path.parent / f"{output_path.stem}_extended.mp4"
            if not _extend_video_with_freeze(video_path, extend_to, extended_path):
                print(f"  WARNING: freeze failed, falling back to atempo clamp")
                speedup = MAX_ATEMPO
            else:
                actual_video_path = extended_path
                video_dur = extend_to

    effective_dur = video_dur if extend_to == 0 else extend_to

    inputs = ["-i", str(actual_video_path)]
    filter_parts: list[str] = []
    audio_streams: list[str] = []
    stream_idx = 1

    has_veo_audio = (actual_video_path == video_path)
    if has_veo_audio:
        veo_vol = veo_audio_volume if has_narration else 0.60
        filter_parts.append(f"[0:a]volume={veo_vol},apad[veo]")
        audio_streams.append("[veo]")

    if has_narration:
        inputs.extend(["-i", str(narration_path)])
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

    use_copy = (actual_video_path == video_path)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy" if use_copy else "libx264",
        *([] if use_copy else ["-preset", "fast", "-crf", "18"]),
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", f"{effective_dur:.2f}",
        str(output_path),
    ]

    mode = "normal"
    if speedup > 1.0:
        mode = f"atempo {speedup:.2f}x"
    elif extend_to > 0:
        mode = f"extended to {extend_to:.1f}s"

    print(f"  [{_ts()}] Mixing {output_path.stem}: "
          f"veo={'yes'} narr={'yes' if has_narration else 'no'} "
          f"music={'yes' if has_music else 'no'} "
          f"(mode={mode}, dur={effective_dur:.1f}s)")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR mixing: {result.stderr[-500:]}")
        return False, clip_duration

    if actual_video_path != video_path and actual_video_path.exists():
        actual_video_path.unlink()

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
    """Generate an ASS subtitle file with word-by-word karaoke-style captions.

    Words are evenly distributed across the narration duration with a highlight
    effect: the current word is shown in yellow, surrounding words in white.
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

        context_start = max(0, i - 2)
        context_end = min(len(words), i + 3)
        parts: list[str] = []
        for j in range(context_start, context_end):
            if j == i:
                parts.append(r"{\c&H00FFFF&}" + words[j] + r"{\c&HFFFFFF&}")
            else:
                parts.append(words[j])

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
    """Concatenate clips into a final video via ffmpeg concat demuxer."""
    if not clip_paths:
        print("  ERROR: No clips to stitch.")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output_path.parent / "concat_list.txt"
    concat_file.write_text("\n".join(f"file '{p}'" for p in clip_paths))

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]

    print(f"\n  [{_ts()}] Stitching {len(clip_paths)} clips...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    concat_file.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  ERROR: ffmpeg stitch failed: {result.stderr[:500]}")
        return False

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [{_ts()}] Final video: {output_path} ({size_mb:.1f} MB)")
    return True
