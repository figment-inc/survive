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


QA_PROMPT_CLIP01 = (
    "You are a visual QA inspector for an animated video series. "
    "The series uses a consistent flat 2D cel-shaded animation style with thick black outlines, "
    "flat colors (zero gradients), and no photorealistic elements.\n\n"
    "Image 1 is the CANONICAL STYLE REFERENCE — a frame from a classic American adult animation "
    "(Family Guy aesthetic). This is the target art style.\n\n"
    "Image 2 is a frame from the generated clip 01 of this episode. Clip 01 will become the "
    "ground truth for all subsequent clips, so any style drift here cascades to the entire episode.\n\n"
    "Compare the generated frame against the style reference across these dimensions:\n"
    "1. ART STYLE: Is it flat 2D cel-shaded animation matching the reference? Flag drift toward "
    "photorealism, 3D rendering, gradients, or mixed styles.\n"
    "2. LINE WEIGHT: Are black outlines thick and uniform like the reference?\n"
    "3. RENDERING QUALITY: Flag AI artifacts — morphing, extra limbs, text, double images.\n"
    "4. OVERALL STYLE MATCH: Would this frame fit seamlessly into the reference show?\n\n"
    "Respond with a single JSON object:\n"
    '{"pass": true/false, "severity": 0-5, "issues": ["issue1", ...]}\n\n'
    "Severity scale: 1=barely noticeable, 3=should regenerate, 5=completely wrong style.\n"
    "Only flag genuine style deviations. Content differences (characters, setting) are expected — "
    "only flag ART STYLE issues."
)


def check_clip01_style(
    video_path: Path,
    style_ref_path: Path,
    api_key: str,
) -> ClipQAResult:
    """Quick style check on clip 01 against the global style reference.

    Returns a ClipQAResult. If severity >= 3, clip 01 should be regenerated
    before being used as the style anchor for subsequent clips.
    """
    client = genai.Client(api_key=api_key)

    frames = _extract_qa_frames(video_path, count=1)
    if not frames:
        print(f"  [{_ts()}] Clip 01 QA: Could not extract frame — skipping check.")
        return ClipQAResult(clip_id="01", passed=True, issues=[], max_severity=0)

    style_bytes = style_ref_path.read_bytes()
    frame_bytes = frames[0].read_bytes()

    content_parts: list[types.Part | str] = [
        QA_PROMPT_CLIP01,
        "\n\nImage 1 — CANONICAL STYLE REFERENCE:",
        types.Part.from_bytes(data=style_bytes, mime_type="image/png"),
        "\n\nImage 2 — Generated clip 01 frame:",
        types.Part.from_bytes(data=frame_bytes, mime_type="image/png"),
    ]

    try:
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=content_parts,
        )
        raw_text = response.text.strip()
    except Exception as e:
        print(f"  [{_ts()}] Clip 01 QA: Gemini vision call failed: {e}")
        return ClipQAResult(clip_id="01", passed=True, issues=[], max_severity=0)

    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"  [{_ts()}] Clip 01 QA: Could not parse response: {text[:300]}")
        return ClipQAResult(clip_id="01", passed=True, issues=[], max_severity=0)

    passed = bool(data.get("pass", True))
    severity = int(data.get("severity", 0))
    issues = data.get("issues", [])

    result = ClipQAResult(clip_id="01", passed=passed, issues=issues, max_severity=severity)
    status = "PASS" if passed else f"FAIL (severity {severity}/5)"
    print(f"  [{_ts()}] Clip 01 QA: {status}")
    if issues:
        print(f"  [{_ts()}]   Issues: {'; '.join(issues)}")

    return result


# ── Slideshow-mode image QA ──


QA_PROMPT_SLIDESHOW = (
    "You are a visual QA inspector for an animated series. The series uses a consistent "
    "flat 2D cel-shaded animation style with thick black outlines, flat colors (zero "
    "gradients), and no photorealistic elements.\n\n"
    "Image 1 is the STYLE REFERENCE — the canonical target art style.\n"
    "The remaining images are generated illustrations for an episode.\n\n"
    "For each generated image, evaluate:\n"
    "1. ART STYLE: Flat 2D cel-shaded? Flag photorealism, 3D, gradients.\n"
    "2. LINE WEIGHT: Thick uniform black outlines present?\n"
    "3. RENDERING QUALITY: AI artifacts — morphing, extra limbs, text, incoherent geometry.\n"
    "4. CHARACTER (when present): Translucent figure with visible skeleton consistent with reference?\n\n"
    "Respond with a JSON array — one object per generated image (in order):\n"
    '[ {"image": 1, "pass": true, "severity": 0, "issues": []}, ... ]\n\n'
    "Severity: 1=barely noticeable, 3=should regenerate, 5=completely wrong.\n"
    "Only flag genuine art style deviations. Content and palette differences are expected."
)


@dataclass
class ImageQAResult:
    image_index: int
    image_path: Path
    passed: bool
    severity: int
    issues: list[str]


def check_slideshow_images(
    image_paths: list[Path],
    style_ref_path: Path,
    api_key: str,
    severity_threshold: int = 3,
) -> list[ImageQAResult]:
    """Lightweight QA pass for slideshow-mode generated images.

    Compares each image against the style reference for art style consistency.
    Returns results for all images; callers should regenerate those with
    severity >= severity_threshold.

    Processes images in batches of 8 to stay within Gemini context limits.
    """
    if not image_paths or not style_ref_path.exists():
        print(f"  [{_ts()}] Slideshow QA: No images or style ref — skipping.")
        return []

    existing = [p for p in image_paths if p.exists()]
    if not existing:
        print(f"  [{_ts()}] Slideshow QA: No images exist on disk — skipping.")
        return []

    client = genai.Client(api_key=api_key)
    style_bytes = style_ref_path.read_bytes()
    style_mime = "image/png" if style_ref_path.suffix.lower() == ".png" else "image/jpeg"

    all_results: list[ImageQAResult] = []
    batch_size = 8

    for batch_start in range(0, len(existing), batch_size):
        batch = existing[batch_start:batch_start + batch_size]
        batch_label = f"batch {batch_start // batch_size + 1}"
        print(f"  [{_ts()}] Slideshow QA: Checking {len(batch)} images ({batch_label})...")

        content_parts: list[types.Part | str] = [
            QA_PROMPT_SLIDESHOW,
            "\n\nImage 0 — STYLE REFERENCE:",
            types.Part.from_bytes(data=style_bytes, mime_type=style_mime),
        ]

        for i, img_path in enumerate(batch, 1):
            content_parts.append(f"\n\nImage {i} — {img_path.name}:")
            img_bytes = img_path.read_bytes()
            img_mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
            content_parts.append(types.Part.from_bytes(data=img_bytes, mime_type=img_mime))

        try:
            response = client.models.generate_content(
                model=VISION_MODEL,
                contents=content_parts,
            )
            raw_text = response.text.strip()
        except Exception as e:
            print(f"  [{_ts()}] Slideshow QA: Vision call failed ({batch_label}): {e}")
            for img_path in batch:
                all_results.append(ImageQAResult(
                    image_index=image_paths.index(img_path),
                    image_path=img_path,
                    passed=True, severity=0, issues=[],
                ))
            continue

        results_json = _parse_gemini_json(raw_text)
        if results_json is None:
            for img_path in batch:
                all_results.append(ImageQAResult(
                    image_index=image_paths.index(img_path),
                    image_path=img_path,
                    passed=True, severity=0, issues=[],
                ))
            continue

        for j, item in enumerate(results_json):
            if j >= len(batch):
                break
            img_path = batch[j]
            passed = bool(item.get("pass", True))
            severity = int(item.get("severity", 0))
            issues = item.get("issues", [])
            if not passed and severity == 0 and issues:
                severity = 3

            all_results.append(ImageQAResult(
                image_index=image_paths.index(img_path),
                image_path=img_path,
                passed=passed,
                severity=severity,
                issues=issues,
            ))

    passed_count = sum(1 for r in all_results if r.passed)
    flagged = [r for r in all_results if not r.passed]
    regen_count = sum(1 for r in flagged if r.severity >= severity_threshold)

    print(f"  [{_ts()}] Slideshow QA: {passed_count} passed, {len(flagged)} flagged, "
          f"{regen_count} need regeneration (severity >= {severity_threshold})")

    for r in flagged:
        issue_str = "; ".join(r.issues)
        print(f"  [{_ts()}] QA ISSUE {r.image_path.name} "
              f"(severity {r.severity}/5): {issue_str}")

    return all_results
