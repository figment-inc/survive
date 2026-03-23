"""Polaroid-style image framing for Instagram carousel posts.

Takes episode images and narration sentences, composites each into a
polaroid-framed 1080x1350 (4:5) slide with white border, square image,
black borders, and caption text underneath.
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

BORDER_SIDE = 50
BORDER_TOP = 50
BORDER_BOTTOM = 280
IMAGE_SIZE = CANVAS_W - 2 * BORDER_SIDE  # 980x980 square image area

TEXT_MARGIN_X = 65
TEXT_MARGIN_TOP = 24
TEXT_COLOR = (0, 0, 0)
TEXT_AREA_W = CANVAS_W - 2 * TEXT_MARGIN_X

FRAME_COLOR = (0, 0, 0)
FRAME_WIDTH = 2
OUTER_FRAME_WIDTH = 3

MAX_CAROUSEL_IMAGES = 10

FONT_SIZES = [32, 28, 24, 20]


def _sanitize_text(text: str) -> str:
    """Normalize unicode punctuation to ASCII equivalents for font compatibility."""
    return (
        text
        .replace("\u2014", " -- ")   # em dash
        .replace("\u2013", " - ")    # en dash
        .replace("\u2018", "'")      # left single quote
        .replace("\u2019", "'")      # right single quote
        .replace("\u201c", '"')      # left double quote
        .replace("\u201d", '"')      # right double quote
        .replace("\u2026", "...")     # ellipsis
    )


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    preferred_fonts = [
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/NewYork.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    ]
    for font_path in preferred_fonts:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int) -> tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    """Find the largest font size that fits the text within max_width and available height."""
    available_h = BORDER_BOTTOM - TEXT_MARGIN_TOP - 40

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


def _center_crop_square(img: Image.Image) -> Image.Image:
    """Center-crop an image to 1:1 square aspect ratio."""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def create_polaroid_image(
    image_path: Path,
    caption_text: str,
    output_path: Path,
) -> Path:
    """Composite a source image into a polaroid frame with caption text.

    Returns the output path on success.
    """
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    src = Image.open(image_path).convert("RGB")
    cropped = _center_crop_square(src)
    resized = cropped.resize((IMAGE_SIZE, IMAGE_SIZE), Image.LANCZOS)

    img_x = BORDER_SIDE
    img_y = BORDER_TOP
    canvas.paste(resized, (img_x, img_y))

    # Black border around the image
    draw.rectangle(
        [img_x - FRAME_WIDTH, img_y - FRAME_WIDTH,
         img_x + IMAGE_SIZE + FRAME_WIDTH - 1, img_y + IMAGE_SIZE + FRAME_WIDTH - 1],
        outline=FRAME_COLOR, width=FRAME_WIDTH,
    )

    # Black border around the outer polaroid edge
    draw.rectangle(
        [0, 0, CANVAS_W - 1, CANVAS_H - 1],
        outline=FRAME_COLOR, width=OUTER_FRAME_WIDTH,
    )

    caption_text = _sanitize_text(caption_text)
    if caption_text.strip():
        wrapped_text, font = _fit_text(draw, caption_text, TEXT_AREA_W)
        text_y = BORDER_TOP + IMAGE_SIZE + TEXT_MARGIN_TOP
        draw.multiline_text(
            (TEXT_MARGIN_X, text_y),
            wrapped_text,
            fill=TEXT_COLOR,
            font=font,
            spacing=6,
        )

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
        caption = si.get("narration_text", "") or si.get("text", "")
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
        caption = si.get("narration_text", "") or si.get("text", "")
        fname = f"sentence_{s_idx:02d}_img_01.png"
        src_path = images_dir / fname
        if src_path.exists():
            slides.append((src_path, caption))
        if len(slides) >= MAX_CAROUSEL_IMAGES:
            break
    return slides
