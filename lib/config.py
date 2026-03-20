"""Centralized configuration and environment loading."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".channel").is_dir() or (current / ".git").is_dir():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent


REPO_DIR = _find_repo_root()
CHANNEL_DIR = REPO_DIR / ".channel"


def _load_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip("'\"")
    return values


def _env(name: str, default: str = "") -> str:
    if os.environ.get(name):
        return os.environ[name]
    env_values = _load_env_file(REPO_DIR / ".env")
    return env_values.get(name, default)


@dataclass
class Settings:
    # AI Services
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-6"
    nanobanana_api_key: str = ""
    nanobanana_model: str = "nano-banana-pro"

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""

    # Metricool
    metricool_publish_enabled: bool = False
    metricool_user_token: str = ""
    metricool_api_url: str = "https://app.metricool.com/api"
    metricool_user_id: str = ""
    metricool_blog_id: str = ""
    metricool_target_platforms: list[str] = field(default_factory=lambda: ["instagram", "tiktok", "youtube"])
    metricool_required_networks: str = "instagram"
    metricool_schedule_timezone: str = "UTC"
    metricool_analytics_enabled: bool = False

    # Publishing
    publish_enabled: bool = False
    publish_platforms: str = "metricool"
    publish_enforce_compliance: bool = True
    request_timeout_seconds: int = 20

    # S3 Storage
    s3_enabled: bool = False
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_prefix: str = "episodes"

    # Paths
    repo_dir: Path = field(default_factory=lambda: REPO_DIR)
    channel_dir: Path = field(default_factory=lambda: CHANNEL_DIR)


def load_settings() -> Settings:
    platforms_raw = _env("METRICOOL_TARGET_PLATFORMS", "instagram,tiktok,youtube")
    target_platforms = [p.strip() for p in platforms_raw.split(",") if p.strip()]

    return Settings(
        gemini_api_key=_env("GEMINI_API_KEY"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-opus-4-6"),
        nanobanana_api_key=_env("NANOBANANA_API_KEY"),
        nanobanana_model=_env("NANOBANANA_MODEL", "nano-banana-pro"),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_env("ELEVENLABS_VOICE_ID"),
        metricool_publish_enabled=_env("METRICOOL_PUBLISH_ENABLED", "false").lower() == "true",
        metricool_user_token=_env("METRICOOL_USER_TOKEN"),
        metricool_api_url=_env("METRICOOL_API_URL", "https://app.metricool.com/api"),
        metricool_user_id=_env("METRICOOL_USER_ID"),
        metricool_blog_id=_env("METRICOOL_BLOG_ID"),
        metricool_target_platforms=target_platforms,
        metricool_required_networks=_env("METRICOOL_REQUIRED_NETWORKS", "instagram"),
        metricool_schedule_timezone=_env("METRICOOL_SCHEDULE_TIMEZONE", "UTC"),
        metricool_analytics_enabled=_env("METRICOOL_ANALYTICS_ENABLED", "false").lower() == "true",
        publish_enabled=_env("PUBLISH_ENABLED", "false").lower() == "true",
        publish_platforms=_env("PUBLISH_PLATFORMS", "metricool"),
        publish_enforce_compliance=_env("PUBLISH_ENFORCE_COMPLIANCE", "true").lower() == "true",
        request_timeout_seconds=int(_env("REQUEST_TIMEOUT_SECONDS", "20")),
        s3_enabled=_env("S3_ENABLED", "false").lower() == "true",
        s3_bucket=_env("S3_BUCKET"),
        s3_region=_env("S3_REGION", "us-east-1"),
        s3_prefix=_env("S3_PREFIX", "episodes"),
    )


def load_channel_file(name: str) -> str:
    path = CHANNEL_DIR / name
    if path.exists():
        return path.read_text()
    return ""
