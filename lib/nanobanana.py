"""NanoBanana Pro image generation with async task polling and reference image support."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import requests

NANOBANANA_API_URL = "https://nanobananapro.cloud/api/v1/image/nano-banana"
NANOBANANA_RESULT_URL = f"{NANOBANANA_API_URL}/result"
POLL_INTERVAL = 5
MAX_POLL_ATTEMPTS = 120


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _mime_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix, "image/png")


def submit_image_task(
    api_key: str,
    model: str,
    prompt: str,
    reference_paths: list[Path] | None = None,
    aspect_ratio: str = "9:16",
    image_size: str = "2K",
) -> str:
    """Submit an image generation task to NanoBanana Pro. Returns the task ID."""
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {
        "prompt": prompt,
        "model": model,
        "aspectRatio": aspect_ratio,
        "imageSize": image_size,
        "outputFormat": "png",
        "isPublic": "false",
    }

    files_list: list[tuple[str, tuple[str, bytes, str]]] = []
    if reference_paths:
        data["mode"] = "image-to-image"
        for ref_path in reference_paths:
            if ref_path.exists():
                mime = _mime_for_path(ref_path)
                files_list.append(("imageFile", (ref_path.name, ref_path.read_bytes(), mime)))
    else:
        data["mode"] = "text-to-image"

    resp = requests.post(
        NANOBANANA_API_URL,
        headers=headers,
        data=data,
        files=files_list or None,
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 0:
        raise RuntimeError(f"NanoBanana submit error: {result.get('message', result)}")

    task_id = result["data"]["id"]
    return task_id


def poll_for_result(api_key: str, task_id: str) -> str:
    """Poll NanoBanana for task completion. Returns the image URL."""
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
            raise RuntimeError(f"Image generation failed: {reason}")

        if attempt % 4 == 3:
            print(f"  [{_ts()}] Generating... {progress}% ({(attempt + 1) * POLL_INTERVAL}s)")

    raise RuntimeError(f"Task timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s")


def download_image(url: str, output_path: Path) -> None:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(resp.content)


def generate_image(
    api_key: str,
    model: str,
    prompt: str,
    output_path: Path,
    reference_paths: list[Path] | None = None,
    aspect_ratio: str = "9:16",
    image_size: str = "2K",
    has_character: bool = False,
) -> bool:
    """Generate a single image via NanoBanana Pro.

    If has_character is True and reference_paths are provided, a character
    consistency prefix is prepended to the prompt.
    """
    if has_character and reference_paths:
        prefix = (
            "The attached reference image shows a humanoid figure with translucent, "
            "ghostly pale skin through which a complete skeleton is visible. Keep the "
            "figure's appearance visually consistent with the reference — same translucent "
            "skin quality, same skeletal visibility, same pale orb eyes.\n\n"
        )
        prompt = prefix + prompt

    print(f"  [{_ts()}] Generating image: {output_path.name} "
          f"(refs={len(reference_paths) if reference_paths else 0}, "
          f"char={'yes' if has_character else 'no'})")

    try:
        task_id = submit_image_task(
            api_key, model, prompt, reference_paths,
            aspect_ratio=aspect_ratio, image_size=image_size,
        )
        print(f"  [{_ts()}] Task submitted: {task_id}")

        image_url = poll_for_result(api_key, task_id)
        download_image(image_url, output_path)

        size_kb = output_path.stat().st_size / 1024
        print(f"  [{_ts()}] Saved: {output_path} ({size_kb:.0f} KB)")
        return True

    except Exception as e:
        print(f"  [{_ts()}] ERROR: {e}")
        return False
