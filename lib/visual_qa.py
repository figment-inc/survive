"""Visual consistency QA — uses Gemini vision to flag clips with style drift."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types


VISION_MODEL = "gemini-2.5-flash"

QA_PROMPT = (
    "You are a visual QA inspector for an animated video series. "
    "The series uses a consistent flat 2D cel-shaded animation style with thick black outlines, "
    "flat colors (zero gradients), and no photorealistic elements.\n\n"
    "Below are keyframes extracted from consecutive clips of a single episode. "
    "Analyze them for visual consistency across ALL of these dimensions:\n"
    "1. ART STYLE: Are all frames flat 2D cel-shaded animation? Flag any that drift toward "
    "photorealism, 3D rendering, gradients, or mixed styles.\n"
    "2. COLOR PALETTE: Do all frames share a coherent color palette? Flag any that introduce "
    "completely different color families.\n"
    "3. CHARACTER DESIGN: Does the translucent skeleton character look consistent across frames? "
    "Flag changes in proportions, transparency, outline weight, or overall appearance.\n"
    "4. LINE WEIGHT: Are black outlines consistent in thickness across frames?\n"
    "5. RENDERING QUALITY: Flag any frames with obvious AI artifacts — morphing, extra limbs, "
    "text artifacts, double images, or incoherent geometry.\n\n"
    "For each frame, respond with a JSON array of objects:\n"
    "[\n"
    '  {"clip": "01", "pass": true, "issues": []},\n'
    '  {"clip": "02", "pass": false, "issues": ["photorealistic drift — 3D shading on buildings", '
    '"character outline weight inconsistent"]}\n'
    "]\n\n"
    "Only flag genuine issues. Minor palette variations appropriate to the narrative "
    "(e.g., darker palette during catastrophe) are expected and should NOT be flagged."
)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


@dataclass
class ClipQAResult:
    clip_id: str
    passed: bool
    issues: list[str]


def _extract_qa_frame(video_path: Path) -> Path | None:
    """Extract a single representative frame from the middle of a clip."""
    from lib.mixer import probe_audio_duration

    duration = probe_audio_duration(video_path)
    seek_time = max(0, duration / 2.0) if duration > 0 else 0

    out = video_path.with_suffix(".qa_frame.png")
    if out.exists():
        return out

    result = subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{seek_time:.3f}",
            "-i", str(video_path),
            "-vframes", "1", "-q:v", "1", str(out),
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not out.exists():
        print(f"  [{_ts()}] WARNING: Could not extract QA frame from {video_path.name}")
        return None
    return out


def check_clip_consistency(
    clip_paths: list[Path],
    api_key: str,
) -> list[ClipQAResult]:
    """Check visual consistency across all episode clips using Gemini vision.

    Extracts a representative frame from each clip and sends them to Gemini
    for multi-image analysis. Returns per-clip pass/fail results.
    """
    import json

    client = genai.Client(api_key=api_key)

    frame_paths: list[tuple[str, Path]] = []
    for clip_path in clip_paths:
        clip_id = clip_path.stem.replace("clip_", "")
        frame = _extract_qa_frame(clip_path)
        if frame:
            frame_paths.append((clip_id, frame))

    if len(frame_paths) < 2:
        print(f"  [{_ts()}] QA: Need at least 2 frames, got {len(frame_paths)} — skipping.")
        return []

    print(f"  [{_ts()}] QA: Analyzing {len(frame_paths)} clip frames for visual consistency...")

    content_parts: list[types.Part | str] = [QA_PROMPT]
    for clip_id, frame_path in frame_paths:
        frame_bytes = frame_path.read_bytes()
        content_parts.append(f"\n\nClip {clip_id}:")
        content_parts.append(types.Part.from_bytes(data=frame_bytes, mime_type="image/png"))

    try:
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=content_parts,
        )
        raw_text = response.text.strip()
    except Exception as e:
        print(f"  [{_ts()}] QA: Gemini vision call failed: {e}")
        return []

    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

    try:
        results_json = json.loads(raw_text)
    except json.JSONDecodeError:
        print(f"  [{_ts()}] QA: Could not parse Gemini response as JSON.")
        print(f"  [{_ts()}] QA: Raw response: {raw_text[:500]}")
        return []

    results: list[ClipQAResult] = []
    for item in results_json:
        clip_id = str(item.get("clip", "??"))
        passed = bool(item.get("pass", True))
        issues = item.get("issues", [])
        results.append(ClipQAResult(clip_id=clip_id, passed=passed, issues=issues))

    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count
    print(f"  [{_ts()}] QA: {passed_count} passed, {failed_count} flagged")

    for r in results:
        if not r.passed:
            issue_str = "; ".join(r.issues)
            print(f"  [{_ts()}] QA ISSUE clip {r.clip_id}: {issue_str}")

    return results
