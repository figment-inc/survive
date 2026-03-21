"""Remotion-based karaoke captions via Whisper transcription.

Pipeline:
  1. transcribe_audio() — OpenAI Whisper API for word-level timestamps
  2. build_remotion_segments() — Convert to HydratedSegment[] JSON for Remotion
  3. render_caption_overlay() — Remotion CLI renders transparent ProRes 4444 MOV
  4. composite_captions() — ffmpeg overlays transparent captions onto video
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

REMOTION_PROJECT = Path(
    os.environ.get(
        "REMOTION_PROJECT_DIR",
        "/Users/eliotchang/Local/Github/Figment/captions/captions-cloudflare/apps/remotion",
    )
)
FPS = 30


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


@dataclass
class WordTimestamp:
    word: str
    start: float
    end: float


NARRATION_DELAY = 0.5


def build_words_from_script(
    narration_text: str,
    video_duration: float,
    narration_delay: float = NARRATION_DELAY,
    narration_duration: float | None = None,
    narration_atempo: float = 1.0,
) -> list[WordTimestamp]:
    """Build proportionally-timed word timestamps from the original script text.

    When narration_duration and narration_atempo are provided (from the mixer),
    the caption window is computed as narration_duration / atempo — matching
    the actual speed-adjusted audio playback. Otherwise falls back to
    video_duration - narration_delay (which can desync if the video was
    extended by freeze-frame or the audio was sped up).
    """
    words = narration_text.split()
    if not words:
        return []

    effective_atempo = narration_atempo if narration_atempo > 1.001 else 1.0

    if narration_duration is not None and narration_duration > 0:
        available = narration_duration / effective_atempo
    else:
        available = video_duration - narration_delay

    if available <= 0:
        return []

    word_dur = available / len(words)
    result = []
    for i, w in enumerate(words):
        start = narration_delay + i * word_dur
        end = start + word_dur
        result.append(WordTimestamp(word=w, start=round(start, 3), end=round(end, 3)))

    tempo_note = f", atempo={effective_atempo:.3f}x" if effective_atempo > 1.0 else ""
    source = "narration audio" if narration_duration is not None else "video duration"
    print(f"  [{_ts()}] Built {len(result)} word timestamps from script text "
          f"({available:.1f}s window from {source}{tempo_note}, {word_dur:.3f}s/word)")
    return result


def transcribe_audio(video_path: Path, api_key: str | None = None) -> list[WordTimestamp]:
    """Extract audio from video and transcribe with OpenAI Whisper for word-level timestamps."""
    from openai import OpenAI

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY required for Whisper transcription")

    audio_path = video_path.with_suffix(".wav")
    print(f"  [{_ts()}] Extracting audio from {video_path.name}...")

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path),
        ],
        capture_output=True,
        check=True,
    )

    print(f"  [{_ts()}] Transcribing with Whisper...")
    client = OpenAI(api_key=api_key)

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )

    audio_path.unlink(missing_ok=True)

    words = []
    for w in getattr(response, "words", []):
        words.append(WordTimestamp(word=w.word, start=w.start, end=w.end))

    print(f"  [{_ts()}] Transcribed {len(words)} words")
    return words


def build_remotion_segments(
    words: list[WordTimestamp],
    max_words_per_segment: int = 3,
    video_width: int = 1080,
) -> list[dict]:
    """Convert Whisper word timestamps into Remotion HydratedSegment[] JSON.

    Groups words into small segments (default 3) for punchy TikTok-style readability.
    Each word gets karaoke styling: highlighted word in yellow (#FFD500),
    other words in white with heavy black stroke.
    Font size scales proportionally to video width (58px at 1080px reference).
    """
    if not words:
        return []

    font_size_px = round(58 * video_width / 1080)

    segments = []
    paragraph_idx = 0

    for seg_start in range(0, len(words), max_words_per_segment):
        seg_words = words[seg_start:seg_start + max_words_per_segment]
        segment_start_time = seg_words[0].start
        segment_end_time = seg_words[-1].end

        hydrated_words = []
        for i, w in enumerate(seg_words):
            word_id = f"w_{seg_start + i}"
            html = _karaoke_html(w.word, font_size_px=font_size_px)
            hydrated_words.append({
                "wordId": word_id,
                "html": html,
                "startTime": w.start,
                "endTime": w.end,
                "isSkipped": False,
                "isHidden": False,
                "isHiddenInCaptions": False,
            })

        segments.append({
            "words": hydrated_words,
            "startTime": segment_start_time,
            "endTime": segment_end_time,
            "paragraphIndex": paragraph_idx,
        })
        paragraph_idx += 1

    print(f"  [{_ts()}] Built {len(segments)} caption segments from {len(words)} words "
          f"(font={font_size_px}px for {video_width}px wide)")
    return segments


def _karaoke_html(word: str, font_size_px: int = 58) -> str:
    """Build HTML for a single word with TikTok-style bold uppercase styling.

    Font size defaults to 58px (tuned for 1080px-wide portrait canvas).
    Callers should scale proportionally for other resolutions.
    """
    stroke = max(1, round(font_size_px / 29))
    glow = max(4, round(font_size_px / 7))
    return (
        f'<span style="'
        f"font-family: 'Montserrat', 'Inter', sans-serif; "
        f"font-weight: 900; "
        f"font-size: {font_size_px}px; "
        f"text-transform: uppercase; "
        f"color: #FFFFFF; "
        f"text-shadow: 0 0 {glow}px rgba(0,0,0,0.95), "
        f"{stroke}px {stroke}px 0 #000, -{stroke}px -{stroke}px 0 #000, "
        f"{stroke}px -{stroke}px 0 #000, -{stroke}px {stroke}px 0 #000, "
        f"0 {stroke}px 0 #000, 0 -{stroke}px 0 #000, "
        f"{stroke}px 0 0 #000, -{stroke}px 0 0 #000; "
        f"letter-spacing: 0.04em;"
        f'">{word}</span>'
    )


def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds via ffprobe.

    Uses stream-level duration (more accurate than container/format duration
    which can be off by 20-50ms due to AAC encoder priming samples).
    Falls back to format-level duration if stream duration is unavailable.
    """
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "stream=duration",
            "-of", "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        durations = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line and line != "N/A":
                try:
                    durations.append(float(line))
                except ValueError:
                    continue
        if durations:
            return max(durations)

    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Get video width and height via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    w, h = result.stdout.strip().split("x")
    return int(w), int(h)


def render_caption_overlay(
    segments: list[dict],
    video_path: Path,
    output_path: Path,
) -> bool:
    """Render transparent caption overlay via Remotion CLI.

    Outputs ProRes 4444 MOV with alpha channel for compositing.
    Returns False gracefully if the Remotion project directory is missing.
    """
    if not REMOTION_PROJECT.exists():
        print(f"  [{_ts()}] Remotion project not found at {REMOTION_PROJECT} — skipping caption render")
        return False

    duration_secs = _get_video_duration(video_path)
    total_frames = math.ceil(duration_secs * FPS)
    actual_w, actual_h = _get_video_dimensions(video_path)

    props = {
        "segments": segments,
        "position": {"x": 50, "y": 72},
        "styleToggles": {
            "scrapbook": False,
            "scatter": False,
            "pulse": False,
            "highlightBorderRadius": 8,
            "singleWord": False,
            "lineByLine": True,
            "karaokeHighlight": True,
            "karaokeTextColor": "#FFD500",
            "entranceAnimation": "none",
            "entranceSpeed": "fast",
            "emphasisAnimation": "none",
            "highlightAnimation": "none",
            "highlightScale": 1.0,
            "highlightColor": "#FFD500",
        },
        "backgroundColor": "transparent",
        "transparentBackground": True,
        "debugMode": False,
        "videoWidth": actual_w,
        "videoHeight": actual_h,
        "videoDuration": duration_secs,
    }

    props_file = output_path.resolve().with_suffix(".props.json")
    props_file.write_text(json.dumps(props, indent=2))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"  [{_ts()}] Rendering caption overlay ({total_frames} frames @ {FPS}fps, {actual_w}x{actual_h})...")

    env = {**os.environ, "TRANSPARENT_EXPORT": "true"}

    cmd = [
        "npx", "remotion", "render",
        "CaptionsOnly",
        str(output_path.resolve()),
        f"--props={props_file}",
        "--codec=prores",
        "--prores-profile=4444",
        f"--width={actual_w}",
        f"--height={actual_h}",
        f"--fps={FPS}",
        f"--frames=0-{total_frames - 1}",
    ]

    result = subprocess.run(
        cmd,
        cwd=str(REMOTION_PROJECT),
        env=env,
        capture_output=True,
        text=True,
    )

    props_file.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"  [{_ts()}] Remotion render FAILED:")
        print(f"    stdout: {result.stdout[-500:]}" if result.stdout else "")
        print(f"    stderr: {result.stderr[-500:]}" if result.stderr else "")
        return False

    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  [{_ts()}] Caption overlay saved: {output_path} ({size_mb:.1f} MB)")
        return True

    print(f"  [{_ts()}] ERROR: Remotion rendered but output not found at {output_path}")
    return False


def composite_captions(video_path: Path, overlay_path: Path, output_path: Path) -> bool:
    """Overlay transparent caption MOV onto the video using ffmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"  [{_ts()}] Compositing captions onto video...")

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(overlay_path),
            "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto",
            "-map", "0:a",
            "-c:a", "aac", "-b:a", "192k",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            str(output_path),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  [{_ts()}] ffmpeg composite FAILED:")
        print(f"    stderr: {result.stderr[-500:]}" if result.stderr else "")
        return False

    if output_path.exists():
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  [{_ts()}] Captioned video saved: {output_path} ({size_mb:.1f} MB)")
        return True

    print(f"  [{_ts()}] ERROR: ffmpeg ran but output not found at {output_path}")
    return False


def run_captions_pipeline(
    video_path: Path,
    output_path: Path,
    openai_api_key: str | None = None,
    narration_text: str | None = None,
    narration_duration: float | None = None,
    narration_atempo: float = 1.0,
) -> Path | None:
    """Full captions pipeline: transcribe -> build segments -> render overlay -> composite.

    When narration_text is provided, uses proportionally-timed word timestamps
    from the original script instead of Whisper transcription. narration_duration
    and narration_atempo (from the mixer phase) ensure caption timing matches the
    actual speed-adjusted audio playback rather than the video duration (which may
    include freeze-frame extension).

    Returns the path to the captioned video, or None if any step fails.
    """
    print(f"  [{_ts()}] Starting Remotion captions pipeline...")

    if narration_text and narration_text.strip():
        video_duration = _get_video_duration(video_path)
        words = build_words_from_script(
            narration_text.strip(),
            video_duration,
            narration_duration=narration_duration,
            narration_atempo=narration_atempo,
        )
    else:
        words = transcribe_audio(video_path, api_key=openai_api_key)

    if not words:
        print(f"  [{_ts()}] WARNING: No words produced — skipping captions")
        return None

    actual_w, _ = _get_video_dimensions(video_path)
    segments = build_remotion_segments(words, video_width=actual_w)

    overlay_path = output_path.with_suffix(".overlay.mov")
    if not render_caption_overlay(segments, video_path, overlay_path):
        print(f"  [{_ts()}] WARNING: Caption overlay render failed — skipping captions")
        return None

    if not composite_captions(video_path, overlay_path, output_path):
        print(f"  [{_ts()}] WARNING: Caption composite failed — skipping captions")
        return None

    overlay_path.unlink(missing_ok=True)
    return output_path
