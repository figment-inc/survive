"""NanoBanana Pro (Gemini 3 Pro Image) generation via the Google GenAI SDK.

Includes retry with exponential backoff and basic image validation.
"""

from __future__ import annotations

import re
import struct
import time
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

GEMINI_IMAGE_MODEL = "gemini-3-pro-image-preview"

SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_ONLY_HIGH"),
]

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]
MIN_IMAGE_SIZE_KB = 10
MIN_IMAGE_DIMENSION = 256


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _mime_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix, "image/png")


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    """Extract width and height from PNG header (IHDR chunk)."""
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    w, h = struct.unpack('>II', data[16:24])
    return w, h


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """Extract width and height from JPEG SOF markers."""
    if len(data) < 4 or data[0:2] != b'\xff\xd8':
        return None
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack('>HH', data[i + 5:i + 9])
            return w, h
        length = struct.unpack('>H', data[i + 2:i + 4])[0]
        i += 2 + length
    return None


def _validate_image(data: bytes, filename: str) -> str | None:
    """Return an error string if the image data fails basic quality checks."""
    size_kb = len(data) / 1024
    if size_kb < MIN_IMAGE_SIZE_KB:
        return f"too small ({size_kb:.0f} KB < {MIN_IMAGE_SIZE_KB} KB)"

    dims = _png_dimensions(data) or _jpeg_dimensions(data)
    if dims:
        w, h = dims
        if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
            return f"dimensions too small ({w}x{h}, min {MIN_IMAGE_DIMENSION}px)"

    return None


_TEXT_SANITIZE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'reading a [^.]*?newspaper', re.IGNORECASE), 'holding a folded newspaper'),
    (re.compile(r'reading a [^.]*?Tribune[^.]*', re.IGNORECASE), 'holding a folded newspaper'),
    (re.compile(r'(?:sign|placard|banner|board)\s+(?:reading|that says|saying)\s+"[^"]*"', re.IGNORECASE), 'a weathered wooden placard'),
    (re.compile(r'"(?:CLOSED|OPEN|NOW SERVING|KEEP OUT|DANGER|WARNING|NO [A-Z]+)[^"]*"', re.IGNORECASE), ''),
    (re.compile(r'[Aa]\s+"[^"]{3,}"\s+sign', re.IGNORECASE), 'a wooden placard'),
    (re.compile(r'(?:letterhead|headed paper)\s+(?:visible|reading|showing)[^.]*', re.IGNORECASE), 'a stack of papers'),
    (re.compile(r'"[^"]{2,}"\s+letterhead', re.IGNORECASE), 'a stack of official papers'),
    (re.compile(r'(?:number display|scoreboard|ticker|digital readout|readout)\s+(?:showing|displaying|reading)[^.]*', re.IGNORECASE), ''),
    (re.compile(r'[Aa] "Now Serving"[^.]*', re.IGNORECASE), ''),
    (re.compile(r'(?:painted|stenciled|hand-lettered|handwritten)\s+(?:number|letter|text|word|sign|label)[^.]*', re.IGNORECASE), ''),
    (re.compile(r'[Aa] painted number on[^.]*', re.IGNORECASE), ''),
    (re.compile(r'[Cc]ity of [A-Z][a-z]+.{0,20}letterhead[^.]*', re.IGNORECASE), 'official papers'),
    (re.compile(r'(?:license plate|number plate|registration plate)[^.]*', re.IGNORECASE), ''),
    (re.compile(r'(?:name tag|badge|ID card)\s+(?:reading|showing|displaying)[^.]*', re.IGNORECASE), ''),
]


def _sanitize_text_references(prompt: str) -> str:
    """Strip or replace phrases that would cause Gemini to render garbled text."""
    for pattern, replacement in _TEXT_SANITIZE_PATTERNS:
        prompt = pattern.sub(replacement, prompt)
    prompt = re.sub(r'\.\s*\.', '.', prompt)
    prompt = re.sub(r'\s{2,}', ' ', prompt)
    return prompt.strip()


def generate_image(
    api_key: str,
    model: str,
    prompt: str,
    output_path: Path,
    reference_paths: list[Path] | None = None,
    aspect_ratio: str = "9:16",
    image_size: str = "2K",
    has_character: bool = False,
    style_anchor_path: Path | None = None,
    episode_style: str | None = None,
    style_ref_path: Path | None = None,
) -> bool:
    """Generate a single image via Nano Banana Pro (Gemini 3 Pro Image).

    Retries up to 3 times with exponential backoff on transient failures.
    Validates output image dimensions and file size before accepting.
    """
    prompt = _sanitize_text_references(prompt)

    if has_character and reference_paths:
        prefix = (
            "The attached reference image shows a humanoid figure with translucent, "
            "ghostly pale skin through which a complete skeleton is visible. Keep the "
            "figure's appearance visually consistent with the reference — same translucent "
            "skin quality, same skeletal visibility, same pale orb eyes.\n\n"
        )
        prompt = prefix + prompt

    if style_ref_path and style_ref_path.exists():
        prompt = (
            "GLOBAL STYLE REFERENCE: The attached style guide image defines the EXACT "
            "visual style for this generation — flat cel-shaded 2D animation with thick "
            "black outlines, clean flat colors, no gradients, no 3D. Match this art style "
            "precisely in every element: characters, backgrounds, objects, lighting. This "
            "is the canonical style target.\n\n"
        ) + prompt

    if style_anchor_path and style_anchor_path.exists():
        prompt = (
            "STYLE ANCHOR: Match the exact color palette, line weight, cel-shading style, "
            "and rendering quality of the attached style reference frame. Maintain visual "
            "continuity with that frame's art style.\n\n"
        ) + prompt

    if episode_style:
        prompt = f"EPISODE VISUAL IDENTITY: {episode_style}\n\n" + prompt

    ref_count = len(reference_paths) if reference_paths else 0
    has_anchor = style_anchor_path and style_anchor_path.exists()
    has_style_ref = style_ref_path and style_ref_path.exists()
    print(f"  [{_ts()}] Generating image: {output_path.name} "
          f"(refs={ref_count}, char={'yes' if has_character else 'no'}"
          f"{', style_ref' if has_style_ref else ''}"
          f"{', style_anchor' if has_anchor else ''})")

    client = genai.Client(api_key=api_key)

    contents = []
    if style_ref_path and style_ref_path.exists():
        mime = _mime_for_path(style_ref_path)
        contents.append(types.Part.from_bytes(data=style_ref_path.read_bytes(), mime_type=mime))
    if style_anchor_path and style_anchor_path.exists():
        mime = _mime_for_path(style_anchor_path)
        contents.append(types.Part.from_bytes(data=style_anchor_path.read_bytes(), mime_type=mime))
    if reference_paths:
        for ref_path in reference_paths:
            if ref_path.exists():
                mime = _mime_for_path(ref_path)
                contents.append(types.Part.from_bytes(data=ref_path.read_bytes(), mime_type=mime))

    contents.append(prompt)

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=GEMINI_IMAGE_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                    safety_settings=SAFETY_SETTINGS,
                ),
            )
        except Exception as e:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            print(f"  [{_ts()}] Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"  [{_ts()}] Retrying in {delay}s...")
                time.sleep(delay)
                continue
            print(f"  [{_ts()}] ERROR: All {MAX_RETRIES} attempts failed for {output_path.name}")
            return False

        if not response.candidates or not response.candidates[0].content.parts:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            print(f"  [{_ts()}] Attempt {attempt + 1}/{MAX_RETRIES}: empty response")
            if attempt < MAX_RETRIES - 1:
                print(f"  [{_ts()}] Retrying in {delay}s...")
                time.sleep(delay)
                continue
            print(f"  [{_ts()}] ERROR: All {MAX_RETRIES} attempts returned empty for {output_path.name}")
            return False

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                image_data = part.inline_data.data

                validation_err = _validate_image(image_data, output_path.name)
                if validation_err:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    print(f"  [{_ts()}] Attempt {attempt + 1}/{MAX_RETRIES}: "
                          f"validation failed — {validation_err}")
                    if attempt < MAX_RETRIES - 1:
                        print(f"  [{_ts()}] Retrying in {delay}s...")
                        time.sleep(delay)
                        break
                    print(f"  [{_ts()}] WARNING: Accepting image despite validation "
                          f"failure after {MAX_RETRIES} attempts")

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(image_data)
                size_kb = output_path.stat().st_size / 1024
                attempt_label = f" (attempt {attempt + 1})" if attempt > 0 else ""
                print(f"  [{_ts()}] Saved: {output_path}{attempt_label} ({size_kb:.0f} KB)")
                return True
        else:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            print(f"  [{_ts()}] Attempt {attempt + 1}/{MAX_RETRIES}: no image in response")
            if attempt < MAX_RETRIES - 1:
                print(f"  [{_ts()}] Retrying in {delay}s...")
                time.sleep(delay)
                continue
            print(f"  [{_ts()}] ERROR: No image after {MAX_RETRIES} attempts for {output_path.name}")
            return False

    return False
