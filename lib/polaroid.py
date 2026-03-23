"""Polaroid-style image framing for Instagram carousel posts.

Takes episode images and narration sentences, composites each into a
polaroid-framed 1080x1350 (4:5) slide with white border and caption text.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LOGGER = logging.getLogger(__name__)

CANVAS_W = 1080
CANVAS_H = 1350
BG_COLOR = (255, 255, 255)

BORDER_SIDE = 40
BORDER_TOP = 40
BORDER_BOTTOM = 260
IMAGE_AREA_W = CANVAS_W - 2 * BORDER_SIDE
IMAGE_AREA_H = CANVAS_H - BORDER_TOP - BORDER_BOTTOM

TEXT_MARGIN_X = 60
TEXT_MARGIN_TOP = 20
TEXT_COLOR = (30, 30, 30)
TEXT_AREA_W = CANVAS_W - 2 * TEXT_MARGIN_X

MAX_CAROUSEL_IMAGES = 10

FONT_SIZES = [32, 28, 24, 20]
MAX_CHARS_PER_LINE = 38


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    preferred_fonts = [
        "/System/Library/Fonts/NewYork.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    ]
    for font_path in preferred_fonts:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int) -> tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    """Find the largest font size that fits the text within max_width and available height."""
    available_h = BORDER_BOTTOM - TEXT_MARGIN_TOP - 30

    for size in FONT_SIZES:
        font = _load_font(size)
        chars_per_line = max(20, int(max_width / (size * 0.55)))
        wrapped = textwrap.fill(text, width=chars_per_line)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        text_h = bbox[3] - bbox[1]
        if text_h <= available_h:
            return wrapped, font

    font = _load_font(FONT_SIZES[-1])
    chars_per_line = max(20, int(max_width / (FONT_SIZES[-1] * 0.55)))
    wrapped = textwrap.fill(text, width=chars_per_line)
    lines = wrapped.split("\n")
    max_lines = max(1, available_h // (FONT_SIZES[-1] + 4))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "..."
        wrapped = "\n".join(lines)
    return wrapped, font


def create_polaroid_image(
    image_path: Path,
    caption_text: str,
    output_path: Path,
) -> Path:
    """Composite a source image into a polaroid frame with caption text.

    Returns the output path on success.
    """
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)

    src = Image.open(image_path).convert("RGB")
    src_w, src_h = src.size

    scale = min(IMAGE_AREA_W / src_w, IMAGE_AREA_H / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    resized = src.resize((new_w, new_h), Image.LANCZOS)

    x_offset = BORDER_SIDE + (IMAGE_AREA_W - new_w) // 2
    y_offset = BORDER_TOP + (IMAGE_AREA_H - new_h) // 2
    canvas.paste(resized, (x_offset, y_offset))

    if caption_text.strip():
        draw = ImageDraw.Draw(canvas)
        wrapped_text, font = _fit_text(draw, caption_text, TEXT_AREA_W)
        text_y = CANVAS_H - BORDER_BOTTOM + TEXT_MARGIN_TOP
        draw.multiline_text(
            (TEXT_MARGIN_X, text_y),
            wrapped_text,
            fill=TEXT_COLOR,
            font=font,
            spacing=6,
        )

    # Subtle drop shadow on the image area
    draw = ImageDraw.Draw(canvas)
    shadow_rect = [
        BORDER_SIDE - 1,
        BORDER_TOP - 1,
        BORDER_SIDE + IMAGE_AREA_W + 1,
        BORDER_TOP + IMAGE_AREA_H + 1,
    ]
    draw.rectangle(shadow_rect, outline=(220, 220, 220), width=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG", optimize=True)
    LOGGER.info("Polaroid image saved: %s", output_path.name)
    return output_path


def create_carousel_images(
    episode_dir: Path,
    sentence_data: list[dict],
) -> list[Path]:
    """Generate polaroid-framed carousel images for an episode.

    Args:
        episode_dir: Root episode directory (e.g., great-plague-of-marseille-1720/).
        sentence_data: List of sentence dicts from episode["sentence_images"],
            each with keys: sentence_index, text, image_prompts.

    Returns:
        Ordered list of polaroid image paths (max 10).
    """
    images_dir = episode_dir / "output" / "images"
    carousel_dir = episode_dir / "output" / "carousel"
    carousel_dir.mkdir(parents=True, exist_ok=True)

    slides: list[tuple[Path, str]] = []

    for si in sentence_data:
        s_idx = si["sentence_index"]
        caption = si.get("text", "")
        num_images = len(si.get("image_prompts", []))

        for p_idx in range(num_images):
            fname = f"sentence_{s_idx:02d}_img_{p_idx + 1:02d}.png"
            src_path = images_dir / fname
            if not src_path.exists():
                LOGGER.warning("Missing image for carousel: %s", fname)
                continue
            slide_caption = caption if p_idx == 0 else ""
            slides.append((src_path, slide_caption))

    if len(slides) > MAX_CAROUSEL_IMAGES:
        LOGGER.info(
            "Episode has %d images, selecting 1 per sentence (max %d)",
            len(slides), MAX_CAROUSEL_IMAGES,
        )
        slides = _select_one_per_sentence(sentence_data, images_dir)

    output_paths: list[Path] = []
    for i, (src_path, caption) in enumerate(slides):
        out_path = carousel_dir / f"carousel_{i + 1:02d}.png"
        create_polaroid_image(src_path, caption, out_path)
        output_paths.append(out_path)

    LOGGER.info("Created %d carousel images in %s", len(output_paths), carousel_dir)
    return output_paths


def _select_one_per_sentence(
    sentence_data: list[dict],
    images_dir: Path,
) -> list[tuple[Path, str]]:
    """Pick one image per sentence to stay within the carousel limit."""
    slides: list[tuple[Path, str]] = []
    for si in sentence_data:
        s_idx = si["sentence_index"]
        caption = si.get("text", "")
        fname = f"sentence_{s_idx:02d}_img_01.png"
        src_path = images_dir / fname
        if src_path.exists():
            slides.append((src_path, caption))
        if len(slides) >= MAX_CAROUSEL_IMAGES:
            break
    return slides
