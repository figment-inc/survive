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
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.4,
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
