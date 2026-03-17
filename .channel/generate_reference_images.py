#!/usr/bin/env python3
"""
Generate canonical reference images for the skeleton character in Family Guy animation style.

Creates character reference sheets at multiple angles for angle-aware Veo conditioning:
  - skeleton_familyguy_front.png    (full-body front-facing)
  - skeleton_familyguy_side.png     (full-body side profile)
  - skeleton_familyguy_threequarter.png  (full-body 3/4 view)
  - skeleton_familyguy_back.png     (full-body rear view)

Uses the same Gemini SDK approach as lib/nanobanana.py for image generation.

Usage:
  python generate_reference_images.py              # generate all missing refs
  python generate_reference_images.py --force      # regenerate all
"""

import argparse
import os
import sys
from pathlib import Path

CHANNEL_DIR = Path(__file__).parent
REPO_DIR = CHANNEL_DIR.parent
REF_DIR = CHANNEL_DIR / "reference_images"
SOURCE_IMAGE = REF_DIR / "skeleton_front_neutral.jpg"

sys.path.insert(0, str(REPO_DIR))

STYLE_PREFIX = (
    "MANDATORY STYLE — AMERICAN ADULT ANIMATION: Classic American adult animation "
    "style. Flat cel-shaded coloring with ZERO gradients. Thick uniform black outlines on "
    "ALL elements. Simplified features. Clean flat colors, no shading variation, no lighting "
    "effects, no 3D rendering, no photorealistic elements.\n\n"
)

CHARACTER_DESC = (
    "A humanoid figure with translucent, ghostly pale skin through which a complete skeleton "
    "is clearly visible — skull with pale orb-like eyes in the sockets, ribcage, spine, pelvis, "
    "and limb bones all defined beneath the semi-transparent surface. Medium build, no hair, "
    "no clothing. Thick black outlines. Rendered as a flat 2D cartoon character with cel-shaded "
    "flat coloring."
)

FRONT_PROMPT = (
    f"{STYLE_PREFIX}"
    f"Character reference sheet. Full-body front-facing view of {CHARACTER_DESC} "
    "The figure stands in a relaxed neutral T-pose, arms slightly away from body, "
    "facing directly at the camera. Plain flat light grey background. "
    "Full body visible from head to feet. Vertical 9:16 frame. "
    "The figure must match the attached reference image's character design but rendered "
    "in flat 2D animation style with thick black outlines and zero gradients. "
    "No text, no labels, no watermarks."
)

SIDE_PROMPT = (
    f"{STYLE_PREFIX}"
    f"Character reference sheet. Full-body side profile view of {CHARACTER_DESC} "
    "The figure stands in a relaxed neutral pose, turned 90 degrees to show a clean "
    "side profile (facing screen-right). Arms relaxed at sides. "
    "Plain flat light grey background. Full body visible from head to feet. "
    "Vertical 9:16 frame. "
    "The figure must match the attached reference image's character design but rendered "
    "in flat 2D animation style with thick black outlines and zero gradients. "
    "No text, no labels, no watermarks."
)

THREE_QUARTER_PROMPT = (
    f"{STYLE_PREFIX}"
    f"Character reference sheet. Full-body three-quarter view of {CHARACTER_DESC} "
    "The figure stands in a relaxed neutral pose, turned roughly 30-45 degrees from "
    "front-facing to show both front and side. Arms relaxed. "
    "Plain flat light grey background. Full body visible from head to feet. "
    "Vertical 9:16 frame. "
    "The figure must match the attached reference image's character design but rendered "
    "in flat 2D animation style with thick black outlines and zero gradients. "
    "No text, no labels, no watermarks."
)

BACK_PROMPT = (
    f"{STYLE_PREFIX}"
    f"Character reference sheet. Full-body rear view of {CHARACTER_DESC} "
    "The figure stands in a relaxed neutral pose, facing directly away from the camera "
    "to show the back of the skull, spine, ribcage from behind, pelvis, and leg bones. "
    "Arms relaxed at sides. "
    "Plain flat light grey background. Full body visible from head to feet. "
    "Vertical 9:16 frame. "
    "The figure must match the attached reference image's character design but rendered "
    "in flat 2D animation style with thick black outlines and zero gradients. "
    "No text, no labels, no watermarks."
)


def load_env_key(name):
    if os.environ.get(name):
        return os.environ[name]
    for env_path in [REPO_DIR / ".env", CHANNEL_DIR / ".env"]:
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def main():
    parser = argparse.ArgumentParser(description="Generate Family Guy-style skeleton reference images")
    parser.add_argument("--force", action="store_true", help="Regenerate existing files")
    args = parser.parse_args()

    api_key = load_env_key("NANOBANANA_API_KEY") or load_env_key("GEMINI_API_KEY")
    if not api_key:
        print("FATAL: NANOBANANA_API_KEY or GEMINI_API_KEY not found.")
        sys.exit(1)

    from lib.nanobanana import generate_image

    REF_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_IMAGE.exists():
        print(f"FATAL: Source image not found: {SOURCE_IMAGE}")
        print("Place the skeleton reference image at .channel/reference_images/skeleton_front_neutral.jpg")
        sys.exit(1)

    print(f"Source image: {SOURCE_IMAGE.name} ({SOURCE_IMAGE.stat().st_size / 1024:.0f} KB)")
    print(f"Style: Family Guy / American adult animation (flat cel-shaded, thick outlines)")
    print()

    targets = [
        ("skeleton_familyguy_front.png", FRONT_PROMPT),
        ("skeleton_familyguy_side.png", SIDE_PROMPT),
        ("skeleton_familyguy_threequarter.png", THREE_QUARTER_PROMPT),
        ("skeleton_familyguy_back.png", BACK_PROMPT),
    ]

    generated = 0
    for filename, prompt in targets:
        output_path = REF_DIR / filename
        if output_path.exists() and not args.force:
            print(f"  Skipping (exists): {filename}")
            continue

        print(f"  Generating: {filename}")
        success = generate_image(
            api_key=api_key,
            model="gemini-3-pro-image-preview",
            prompt=prompt,
            output_path=output_path,
            reference_paths=[SOURCE_IMAGE],
            has_character=True,
        )
        if success:
            generated += 1
        print()

    print(f"Done. Generated {generated} Family Guy-style reference images.")
    print(f"All reference images: {REF_DIR}")
    print("\nAngles generated:")
    for filename, _ in targets:
        path = REF_DIR / filename
        status = f"{path.stat().st_size / 1024:.0f} KB" if path.exists() else "MISSING"
        print(f"  {filename}: {status}")


if __name__ == "__main__":
    main()
