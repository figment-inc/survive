#!/usr/bin/env python3
"""
Generate canonical reference images for the skeleton character.

Creates front-facing neutral pose, headshot, and side shot
that serve as character conditioning for all Veo 8s scene clips
and NanoBanana Pro image generation.

Usage:
  python generate_reference_images.py              # generate all missing refs
  python generate_reference_images.py --force      # regenerate all
"""

import argparse
import os
import re
import time
from pathlib import Path

import requests

CHANNEL_DIR = Path(__file__).parent
REPO_DIR = CHANNEL_DIR.parent
REF_DIR = CHANNEL_DIR / "reference_images"

NANOBANANA_API_URL = "https://nanobananapro.cloud/api/v1/image/nano-banana"
NANOBANANA_RESULT_URL = f"{NANOBANANA_API_URL}/result"
POLL_INTERVAL = 5
MAX_POLL_ATTEMPTS = 120

SOURCE_IMAGE = REF_DIR / "skeleton_front_neutral.jpg"

HEADSHOT_PROMPT = (
    "A close-up headshot portrait of a humanoid figure with translucent, ghostly pale "
    "skin through which a skull is clearly visible — eye sockets with pale orb-like eyes, "
    "cheekbones, jaw, and cranium all defined beneath the semi-transparent surface. No hair. "
    "The figure looks directly at the camera with a neutral expression. Head and shoulders "
    "framing against a plain neutral grey background. Photorealistic, high detail, soft "
    "studio lighting. Vertical 9:16 frame. The figure must match the attached reference "
    "image exactly — same translucent skin quality, same skeletal visibility, same pale eyes."
)

SIDE_PROMPT = (
    "A 3/4 side-angle portrait of a humanoid figure with translucent, ghostly pale skin "
    "through which a skeleton is clearly visible — skull, ribcage, spine, shoulder bones "
    "all defined beneath the semi-transparent surface. No hair, no clothing. The figure is "
    "turned roughly 45 degrees to show both front and side profile. Head and shoulders "
    "framing against a plain neutral grey background. Photorealistic, high detail, soft "
    "studio lighting. Vertical 9:16 frame. The figure must match the attached reference "
    "image exactly — same translucent skin quality, same skeletal visibility."
)

THREE_QUARTER_PROMPT = (
    "A full-body three-quarter view of a humanoid figure with translucent, ghostly pale "
    "skin through which a complete skeleton is clearly visible — skull, ribcage, spine, "
    "pelvis, arm and leg bones all defined beneath the semi-transparent surface. Medium "
    "build, no hair, no clothing. The figure stands in a relaxed neutral pose, turned "
    "roughly 30 degrees from front-facing. Visible from knees up. Plain neutral grey "
    "background. Photorealistic, high detail, soft studio lighting. Vertical 9:16 frame. "
    "The figure must match the attached reference image exactly."
)


def load_api_key():
    if os.environ.get("NANOBANANA_API_KEY"):
        return os.environ["NANOBANANA_API_KEY"]
    for env_path in [REPO_DIR / ".env", CHANNEL_DIR / ".env"]:
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("NANOBANANA_API_KEY="):
                val = line.split("=", 1)[1].strip().strip("'\"")
                if val:
                    return val
    raise RuntimeError("NANOBANANA_API_KEY not found in environment or .env files.")


def load_model():
    if os.environ.get("NANOBANANA_MODEL"):
        return os.environ["NANOBANANA_MODEL"]
    for env_path in [REPO_DIR / ".env", CHANNEL_DIR / ".env"]:
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("NANOBANANA_MODEL="):
                val = line.split("=", 1)[1].strip().strip("'\"")
                if val:
                    return val
    return "nano-banana-pro"


def submit_image_task(api_key, model, prompt, reference_path=None):
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {
        "prompt": prompt,
        "model": model,
        "aspectRatio": "9:16",
        "imageSize": "1K",
        "outputFormat": "png",
        "isPublic": "false",
    }

    files = {}
    if reference_path and reference_path.exists():
        data["mode"] = "image-to-image"
        mime = "image/jpeg" if reference_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        files["imageFile"] = (reference_path.name, reference_path.read_bytes(), mime)
    else:
        data["mode"] = "text-to-image"

    resp = requests.post(NANOBANANA_API_URL, headers=headers, data=data, files=files or None, timeout=60)
    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 0:
        raise RuntimeError(f"NanoBanana submit error: {result.get('message', result)}")

    task_id = result["data"]["id"]
    print(f"  Task submitted: {task_id}")
    return task_id


def poll_for_result(api_key, task_id):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    for attempt in range(MAX_POLL_ATTEMPTS):
        time.sleep(POLL_INTERVAL)
        resp = requests.post(
            NANOBANANA_RESULT_URL,
            headers=headers,
            json={"taskId": task_id},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        data = result.get("data", {})
        status = data.get("status", "unknown")
        progress = data.get("progress", 0)

        if status == "succeeded":
            results = data.get("results", [])
            if results:
                return results[0]["url"]
            raise RuntimeError("Task succeeded but no results returned")

        if status == "failed":
            reason = data.get("failure_reason") or data.get("error") or "unknown"
            raise RuntimeError(f"Task failed: {reason}")

        print(f"  Polling... {progress}% ({(attempt + 1) * POLL_INTERVAL}s)")

    raise RuntimeError(f"Task timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s")


def download_image(url, output_path):
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    output_path.write_bytes(resp.content)
    size_kb = output_path.stat().st_size / 1024
    print(f"  Saved: {output_path} ({size_kb:.0f} KB)")


def generate_image(api_key, model, prompt, output_path, reference_path=None):
    print(f"  Generating: {output_path.name}")
    try:
        task_id = submit_image_task(api_key, model, prompt, reference_path)
        image_url = poll_for_result(api_key, task_id)
        download_image(image_url, output_path)
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate canonical skeleton reference images")
    parser.add_argument("--force", action="store_true", help="Regenerate existing files")
    args = parser.parse_args()

    api_key = load_api_key()
    model = load_model()
    REF_DIR.mkdir(parents=True, exist_ok=True)

    if not SOURCE_IMAGE.exists():
        print(f"FATAL: Source image not found: {SOURCE_IMAGE}")
        print("Place the skeleton reference image at .channel/reference_images/skeleton_front_neutral.jpg")
        return

    print(f"Source image: {SOURCE_IMAGE.name} ({SOURCE_IMAGE.stat().st_size / 1024:.0f} KB)")
    print(f"Model: {model}")
    print()

    targets = [
        ("skeleton_headshot.png", HEADSHOT_PROMPT),
        ("skeleton_side.png", SIDE_PROMPT),
        ("skeleton_three_quarter.png", THREE_QUARTER_PROMPT),
    ]

    generated = 0
    for filename, prompt in targets:
        output_path = REF_DIR / filename
        if output_path.exists() and not args.force:
            print(f"  Skipping (exists): {filename}")
            continue
        if generate_image(api_key, model, prompt, output_path, reference_path=SOURCE_IMAGE):
            generated += 1
        print()

    print(f"Done. Generated {generated} reference images.")
    print(f"All reference images: {REF_DIR}")
    print("\nNext: visually verify the new refs, then generate episode content.")


if __name__ == "__main__":
    main()
