"""ElevenLabs TTS narration + music generation (no SFX — Veo handles that natively)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import requests

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
ELEVENLABS_TTS_MODEL = "eleven_multilingual_v2"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def generate_narration(
    api_key: str,
    voice_id: str,
    text: str,
    output_path: Path,
    force: bool = False,
) -> bool:
    """Generate narrator voiceover for a single clip via ElevenLabs TTS."""
    if output_path.exists() and not force:
        print(f"  [{_ts()}] Skipping (exists): {output_path.name}")
        return True

    word_count = len(text.split())
    print(f"  [{_ts()}] Generating narration: {output_path.name} ({word_count} words)")

    url = f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_TTS_MODEL,
        "voice_settings": {
            "stability": 0.85,
            "similarity_boost": 0.75,
            "style": 0.15,
            "use_speaker_boost": True,
        },
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.content)
        size_kb = len(resp.content) / 1024
        print(f"  [{_ts()}] Narration saved: {output_path.name} ({size_kb:.0f} KB)")
        return True
    except Exception as e:
        print(f"  ERROR generating narration: {e}")
        return False


def generate_full_narration(
    api_key: str,
    voice_id: str,
    full_script: str,
    output_path: Path,
    force: bool = False,
) -> bool:
    """Generate ONE continuous narration audio file from the full episode script.

    Strips clip markers and NARRATOR: prefixes, concatenates all narration text
    into a single block, and sends it as one TTS request for natural prosody.
    """
    if output_path.exists() and not force:
        print(f"  [{_ts()}] Skipping (exists): {output_path.name}")
        return True

    narration_text = extract_continuous_narration(full_script)
    if not narration_text:
        print(f"  [{_ts()}] ERROR: No narration text extracted from script")
        return False

    word_count = len(narration_text.split())
    print(f"  [{_ts()}] Generating full narration: {output_path.name} ({word_count} words)")

    url = f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": narration_text,
        "model_id": ELEVENLABS_TTS_MODEL,
        "voice_settings": {
            "stability": 0.85,
            "similarity_boost": 0.75,
            "style": 0.15,
            "use_speaker_boost": True,
        },
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.content)
        size_kb = len(resp.content) / 1024
        print(f"  [{_ts()}] Full narration saved: {output_path.name} ({size_kb:.0f} KB)")
        return True
    except Exception as e:
        print(f"  ERROR generating full narration: {e}")
        return False


def extract_continuous_narration(dialogue_script: str) -> str:
    """Extract all NARRATOR lines from a dialogue script into one continuous text.

    Handles mid-sentence continuations marked with em dashes (—) at clip
    boundaries by joining them without extra whitespace.
    """
    import re

    lines: list[str] = []
    for line in dialogue_script.splitlines():
        narr_match = re.match(r"NARRATOR:\s*[\"']?(.+?)[\"']?\s*$", line)
        if not narr_match:
            continue
        text = narr_match.group(1).strip()
        if not text:
            continue

        if lines and text.startswith("—"):
            lines[-1] = lines[-1].rstrip()
            text = " " + text.lstrip("—").strip()
            lines[-1] += text
        elif lines and lines[-1].endswith("—"):
            text = text.lstrip("—").strip()
            lines[-1] += " " + text
        else:
            lines.append(text)

    return " ".join(lines).strip()


def generate_music(
    api_key: str,
    prompt: str,
    output_path: Path,
    duration_ms: int = 60000,
    force: bool = False,
) -> bool:
    """Generate background music via ElevenLabs Music API."""
    if output_path.exists() and not force:
        print(f"  [{_ts()}] Skipping (exists): {output_path.name}")
        return True

    print(f"  [{_ts()}] Generating background music ({duration_ms // 1000}s instrumental)...")

    url = f"{ELEVENLABS_BASE_URL}/music"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "prompt": prompt,
        "duration_ms": duration_ms,
        "instrumental": True,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.content)
        size_kb = len(resp.content) / 1024
        print(f"  [{_ts()}] Music saved: {output_path.name} ({size_kb:.0f} KB)")
        return True
    except Exception as e:
        print(f"  ERROR generating music: {e}")
        return False
