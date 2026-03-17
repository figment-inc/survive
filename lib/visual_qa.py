"""Visual consistency QA — uses Gemini vision to flag clips with style drift."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types


VISION_MODEL = "gemini-2.5-flash"

QA_PROMPT_PAIRWISE = (
    "You are a visual QA inspector for an animated video series. "
    "The series uses a consistent flat 2D cel-shaded animation style with thick black outlines, "
    "flat colors (zero gradients), and no photorealistic elements.\n\n"
    "The FIRST image below is the GROUND TRUTH — clip 01 — which defines the correct art style, "
    "line weight, color rendering, and character design for this episode. Every subsequent clip "
    "must visually match this ground truth.\n\n"
    "For each clip after clip 01, you will see multiple frames (sampled at 25%, 50%, 75% of the clip). "
    "Compare ALL frames against the ground truth and analyze:\n"
    "1. ART STYLE: Does it match the ground truth's flat 2D cel-shaded rendering? Flag drift "
    "toward photorealism, 3D rendering, gradients, or mixed styles.\n"
    "2. COLOR PALETTE: Is it consistent with the ground truth's color family? Flag clips that "
    "introduce completely different color families (narrative-appropriate shifts like darker "
    "catastrophe palettes are fine).\n"
    "3. CHARACTER DESIGN: Does the translucent figure match the ground truth's proportions, "
    "transparency level, outline weight, and overall appearance?\n"
    "4. LINE WEIGHT: Are black outlines the same thickness as the ground truth?\n"
    "5. RENDERING QUALITY: Flag obvious AI artifacts — morphing, extra limbs, text artifacts, "
    "double images, or incoherent geometry.\n"
    "6. INTRA-CLIP DRIFT: Do the multiple frames from the SAME clip stay consistent with each "
    "other? Flag if style changes within a single clip.\n\n"
    "Respond with a JSON array. Clip 01 always passes (it IS the ground truth). "
    "For each issue, include a severity rating from 1-5:\n"
    "  1 = Barely noticeable, acceptable\n"
    "  2 = Minor but visible inconsistency\n"
    "  3 = Clear style deviation, should be regenerated\n"
    "  4 = Major drift, clip looks wrong\n"
    "  5 = Completely different art style\n\n"
    "Example:\n[\n"
    '  {"clip": "01", "pass": true, "issues": [], "max_severity": 0},\n'
    '  {"clip": "02", "pass": false, "issues": ["ART STYLE: 3D shading on buildings (severity 3)"], '
    '"max_severity": 3}\n'
    "]\n\n"
    "Only flag genuine deviations from the ground truth. Minor palette darkening for "
    "catastrophe beats is expected and should NOT be flagged."
)

QA_PROMPT_LEGACY = (
    "You are a visual QA inspector for an animated video series. "
    "The series uses a consistent flat 2D cel-shaded animation style with thick black outlines, "
    "flat colors (zero gradients), and no photorealistic elements.\n\n"
    "Below are keyframes extracted from consecutive clips of a single episode. "
    "Multiple frames per clip (sampled at 25%, 50%, 75%) are provided when available. "
    "Analyze them for visual consistency across ALL of these dimensions:\n"
    "1. ART STYLE: Are all frames flat 2D cel-shaded animation? Flag any that drift toward "
    "photorealism, 3D rendering, gradients, or mixed styles.\n"
    "2. COLOR PALETTE: Do all frames share a coherent color palette? Flag any that introduce "
    "completely different color families.\n"
    "3. CHARACTER DESIGN: Does the translucent skeleton character look consistent across frames? "
    "Flag changes in proportions, transparency, outline weight, or overall appearance.\n"
    "4. LINE WEIGHT: Are black outlines consistent in thickness across frames?\n"
    "5. RENDERING QUALITY: Flag any frames with obvious AI artifacts — morphing, extra limbs, "
    "text artifacts, double images, or incoherent geometry.\n"
    "6. INTRA-CLIP DRIFT: Do multiple frames from the SAME clip stay consistent?\n\n"
    "For each clip, respond with a JSON array of objects. Include a severity rating (1-5) "
    "for each issue:\n"
    "  1 = Barely noticeable  |  3 = Should regenerate  |  5 = Completely wrong style\n\n"
    "[\n"
    '  {"clip": "01", "pass": true, "issues": [], "max_severity": 0},\n'
    '  {"clip": "02", "pass": false, "issues": ["photorealistic drift — 3D shading (severity 4)"], '
    '"max_severity": 4}\n'
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
    max_severity: int = 0


def _extract_qa_frame(video_path: Path) -> Path | None:
    """Extract a single representative frame from the middle of a clip."""
    frames = _extract_qa_frames(video_path)
    return frames[0] if frames else None


def _extract_qa_frames(video_path: Path, count: int = 3) -> list[Path]:
    """Extract multiple representative frames from a clip for thorough QA.

    Samples at 25%, 50%, and 75% of clip duration to detect intra-clip drift.
    """
    from lib.mixer import probe_audio_duration

    duration = probe_audio_duration(video_path)
    if duration <= 0:
        duration = 4.0

    percentiles = [0.25, 0.50, 0.75][:count]
    frames: list[Path] = []
    for pct in percentiles:
        seek_time = max(0, duration * pct)
        label = f"{int(pct * 100)}"
        out = video_path.with_suffix(f".qa_frame_{label}.png")
        if out.exists():
            frames.append(out)
            continue
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-ss", f"{seek_time:.3f}",
                "-i", str(video_path),
                "-vframes", "1", "-q:v", "1", str(out),
            ],
            capture_output=True,
        )
        if result.returncode == 0 and out.exists():
            frames.append(out)
        else:
            print(f"  [{_ts()}] WARNING: Could not extract QA frame ({label}%) from {video_path.name}")

    return frames


def _parse_gemini_json(raw_text: str) -> list[dict] | None:
    """Strip markdown fences and parse JSON from Gemini response."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"  [{_ts()}] QA: Could not parse Gemini response as JSON.")
        print(f"  [{_ts()}] QA: Raw response: {text[:500]}")
        return None


def _save_qa_results(results: list[ClipQAResult], output_dir: Path) -> Path:
    """Write QA results to a JSON sidecar file for debugging."""
    qa_path = output_dir / "qa_results.json"
    data = [
        {
            "clip": r.clip_id,
            "pass": r.passed,
            "issues": r.issues,
            "max_severity": r.max_severity,
        }
        for r in results
    ]
    qa_path.write_text(json.dumps(data, indent=2))
    print(f"  [{_ts()}] QA: Results saved to {qa_path}")
    return qa_path


def check_clip_consistency(
    clip_paths: list[Path],
    api_key: str,
    ground_truth_frame: Path | None = None,
) -> list[ClipQAResult]:
    """Check visual consistency across all episode clips using Gemini vision.

    If ground_truth_frame is provided (clip 01's keyframe image), each clip is
    compared against it as the style reference. Otherwise falls back to the
    legacy all-vs-all comparison.

    Extracts a representative frame from each clip and sends them to Gemini
    for multi-image analysis. Returns per-clip pass/fail results and saves
    results to a qa_results.json sidecar file.
    """
    client = genai.Client(api_key=api_key)

    clip_frames: list[tuple[str, list[Path]]] = []
    for clip_path in clip_paths:
        clip_id = clip_path.stem.replace("clip_", "")
        frames = _extract_qa_frames(clip_path)
        if frames:
            clip_frames.append((clip_id, frames))

    if len(clip_frames) < 2:
        print(f"  [{_ts()}] QA: Need at least 2 clips, got {len(clip_frames)} — skipping.")
        return []

    total_frames = sum(len(fs) for _, fs in clip_frames)
    use_ground_truth = ground_truth_frame and ground_truth_frame.exists()
    mode_label = "ground-truth comparison" if use_ground_truth else "cross-clip comparison"
    print(f"  [{_ts()}] QA: Analyzing {len(clip_frames)} clips ({total_frames} frames, {mode_label})...")

    content_parts: list[types.Part | str] = []

    if use_ground_truth:
        content_parts.append(QA_PROMPT_PAIRWISE)
        gt_bytes = ground_truth_frame.read_bytes()
        content_parts.append("\n\nGROUND TRUTH — Clip 01 (reference style):")
        content_parts.append(types.Part.from_bytes(data=gt_bytes, mime_type="image/png"))
        for clip_id, frames in clip_frames:
            if clip_id == "01":
                continue
            content_parts.append(f"\n\nClip {clip_id} ({len(frames)} frames):")
            for frame_path in frames:
                frame_bytes = frame_path.read_bytes()
                content_parts.append(types.Part.from_bytes(data=frame_bytes, mime_type="image/png"))
    else:
        content_parts.append(QA_PROMPT_LEGACY)
        for clip_id, frames in clip_frames:
            content_parts.append(f"\n\nClip {clip_id} ({len(frames)} frames):")
            for frame_path in frames:
                frame_bytes = frame_path.read_bytes()
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

    results_json = _parse_gemini_json(raw_text)
    if results_json is None:
        return []

    results: list[ClipQAResult] = []

    if use_ground_truth:
        results.append(ClipQAResult(clip_id="01", passed=True, issues=[], max_severity=0))

    for item in results_json:
        clip_id = str(item.get("clip", "??"))
        passed = bool(item.get("pass", True))
        issues = item.get("issues", [])
        max_severity = int(item.get("max_severity", 0))
        if not passed and max_severity == 0 and issues:
            max_severity = 3
        if use_ground_truth and clip_id == "01":
            continue
        results.append(ClipQAResult(
            clip_id=clip_id, passed=passed, issues=issues, max_severity=max_severity,
        ))

    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count
    print(f"  [{_ts()}] QA: {passed_count} passed, {failed_count} flagged")

    for r in results:
        if not r.passed:
            issue_str = "; ".join(r.issues)
            print(f"  [{_ts()}] QA ISSUE clip {r.clip_id} (severity {r.max_severity}/5): {issue_str}")

    if clip_paths:
        _save_qa_results(results, clip_paths[0].parent)

    return results
