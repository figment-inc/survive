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

REMOTION_PROJECT = Path("/Users/eliotchang/Local/Github/Figment/captions/captions-cloudflare/apps/remotion")
FPS = 30
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


@dataclass
class WordTimestamp:
    word: str
    start: float
    end: float


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
) -> list[dict]:
    """Convert Whisper word timestamps into Remotion HydratedSegment[] JSON.

    Groups words into small segments (default 3) for punchy TikTok-style readability.
    Each word gets karaoke styling: highlighted word in yellow (#FFD500),
    other words in white with heavy black stroke.
    """
    if not words:
        return []

    segments = []
    paragraph_idx = 0

    for seg_start in range(0, len(words), max_words_per_segment):
        seg_words = words[seg_start:seg_start + max_words_per_segment]
        segment_start_time = seg_words[0].start
        segment_end_time = seg_words[-1].end

        hydrated_words = []
        for i, w in enumerate(seg_words):
            word_id = f"w_{seg_start + i}"
            html = _karaoke_html(w.word)
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

    print(f"  [{_ts()}] Built {len(segments)} caption segments from {len(words)} words")
    return segments


def _karaoke_html(word: str) -> str:
    """Build HTML for a single word with TikTok-style bold uppercase styling."""
    return (
        f'<span style="'
        f"font-family: 'Montserrat', 'Inter', sans-serif; "
        f"font-weight: 900; "
        f"font-size: 90px; "
        f"text-transform: uppercase; "
        f"color: #FFFFFF; "
        f"text-shadow: 0 0 10px rgba(0,0,0,0.95), 3px 3px 0 #000, -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 0 3px 0 #000, 0 -3px 0 #000, 3px 0 0 #000, -3px 0 0 #000; "
        f"letter-spacing: 0.04em;"
        f'">{word}</span>'
    )


def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds via ffprobe."""
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


def render_caption_overlay(
    segments: list[dict],
    video_path: Path,
    output_path: Path,
) -> bool:
    """Render transparent caption overlay via Remotion CLI.

    Outputs ProRes 4444 MOV with alpha channel for compositing.
    """
    duration_secs = _get_video_duration(video_path)
    total_frames = math.ceil(duration_secs * FPS)

    props = {
        "segments": segments,
        "position": {"x": 50, "y": 65},
        "styleToggles": {
            "scrapbook": False,
            "scatter": False,
            "pulse": False,
            "highlightBorderRadius": 8,
            "singleWord": False,
            "lineByLine": False,
            "karaokeHighlight": True,
            "karaokeTextColor": "#FFD500",
            "entranceAnimation": "slideUp",
            "entranceSpeed": "fast",
            "emphasisAnimation": "none",
            "highlightAnimation": "scale",
            "highlightScale": 1.2,
            "highlightColor": "#FFD500",
        },
        "backgroundColor": "transparent",
        "transparentBackground": True,
        "debugMode": False,
        "videoWidth": VIDEO_WIDTH,
        "videoHeight": VIDEO_HEIGHT,
        "videoDuration": duration_secs,
    }

    props_file = output_path.with_suffix(".props.json")
    props_file.write_text(json.dumps(props, indent=2))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"  [{_ts()}] Rendering caption overlay ({total_frames} frames @ {FPS}fps)...")

    env = {**os.environ, "TRANSPARENT_EXPORT": "true"}

    cmd = [
        "npx", "remotion", "render",
        "CaptionsOnly",
        str(output_path),
        f"--props={props_file}",
        "--codec=prores",
        "--prores-profile=4444",
        f"--width={VIDEO_WIDTH}",
        f"--height={VIDEO_HEIGHT}",
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
) -> Path | None:
    """Full captions pipeline: transcribe -> build segments -> render overlay -> composite.

    Returns the path to the captioned video, or None if any step fails.
    """
    print(f"  [{_ts()}] Starting Remotion captions pipeline...")

    words = transcribe_audio(video_path, api_key=openai_api_key)
    if not words:
        print(f"  [{_ts()}] WARNING: No words transcribed — skipping captions")
        return None

    segments = build_remotion_segments(words)

    overlay_path = output_path.with_suffix(".overlay.mov")
    if not render_caption_overlay(segments, video_path, overlay_path):
        print(f"  [{_ts()}] WARNING: Caption overlay render failed — skipping captions")
        return None

    if not composite_captions(video_path, overlay_path, output_path):
        print(f"  [{_ts()}] WARNING: Caption composite failed — skipping captions")
        return None

    overlay_path.unlink(missing_ok=True)
    return output_path
