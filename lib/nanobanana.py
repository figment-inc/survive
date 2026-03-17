"""NanoBanana Pro (Gemini 3 Pro Image) generation via the Google GenAI SDK."""

from __future__ import annotations

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


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _mime_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix, "image/png")


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

    Uses the official Google GenAI SDK with the Gemini API key.
    If has_character is True and reference_paths are provided, a character
    consistency prefix is prepended to the prompt.
    style_ref_path is the global style guide image (e.g. Family Guy frame) —
    always passed as the first visual input to ground the art style.
    style_anchor_path adds a previously generated frame as a style reference.
    episode_style injects the episode's unified visual identity text.
    """
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
        print(f"  [{_ts()}] ERROR: {e}")
        return False

    if not response.candidates or not response.candidates[0].content.parts:
        print(f"  [{_ts()}] ERROR: Empty response for {output_path.name}")
        return False

    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.mime_type.startswith("image/"):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(part.inline_data.data)
            size_kb = output_path.stat().st_size / 1024
            print(f"  [{_ts()}] Saved: {output_path} ({size_kb:.0f} KB)")
            return True

    print(f"  [{_ts()}] ERROR: No image in response for {output_path.name}")
    return False
