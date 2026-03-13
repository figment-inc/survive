"""Gemini-based image generation fallback when NanoBanana Pro is unavailable."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types


IMAGE_MODEL = "gemini-3-pro-image-preview"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def generate_image(
    api_key: str,
    prompt: str,
    output_path: Path,
    reference_paths: list[Path] | None = None,
    has_character: bool = False,
    aspect_ratio: str = "9:16",
) -> bool:
    """Generate a single image via Gemini's multimodal image output.

    Uses reference images for character consistency when provided.
    """
    client = genai.Client(api_key=api_key)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if has_character and reference_paths:
        prefix = (
            "The attached reference image shows a humanoid figure with translucent, "
            "ghostly pale skin through which a complete skeleton is visible. Keep the "
            "figure's appearance visually consistent with the reference — same translucent "
            "skin quality, same skeletal visibility, same pale orb eyes.\n\n"
        )
        prompt = prefix + prompt

    contents: list = []
    ref_count = 0

    if reference_paths:
        for ref_path in reference_paths:
            if ref_path.exists():
                ref_bytes = ref_path.read_bytes()
                mime = "image/jpeg" if ref_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                contents.append(types.Part.from_bytes(data=ref_bytes, mime_type=mime))
                ref_count += 1

    contents.append(f"Generate a single high-quality image. {prompt}")

    print(f"  [{_ts()}] Generating image: {output_path.name} "
          f"(refs={ref_count}, char={'yes' if has_character else 'no'}, model={IMAGE_MODEL})")

    try:
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                output_path.write_bytes(part.inline_data.data)
                size_kb = output_path.stat().st_size / 1024
                print(f"  [{_ts()}] Saved: {output_path} ({size_kb:.0f} KB)")
                return True

        print(f"  [{_ts()}] ERROR: No image in Gemini response")
        if response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.text:
                    print(f"  Text response: {part.text[:200]}")
        return False

    except Exception as e:
        print(f"  [{_ts()}] ERROR: {e}")
        return False
