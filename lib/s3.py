"""S3 storage utilities for episode output artifacts."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from lib.config import load_settings, _env

_client_cache: dict[str, object] = {}

SYNC_SUBDIRS = [
    "output/images",
    "output/audio",
    "output/videos",
    "output/mixed_clips",
    "output/normalized",
    "output/mixed",
    "output/captioned",
]

METADATA_FILES = [
    "episode.json",
    "01_storyboard.md",
    "00_draft_script.txt",
    "00_critique.md",
    "04_dialogue_script.txt",
]


def _get_credentials() -> tuple[str, str]:
    key_id = os.environ.get("AWS_ACCESS_KEY_ID") or _env("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY") or _env("AWS_SECRET_ACCESS_KEY")
    return key_id, secret


def get_s3_client():
    settings = load_settings()
    cache_key = f"{settings.s3_bucket}:{settings.s3_region}"
    if cache_key in _client_cache:
        return _client_cache[cache_key]

    key_id, secret = _get_credentials()
    client = boto3.client(
        "s3",
        region_name=settings.s3_region,
        aws_access_key_id=key_id if key_id else None,
        aws_secret_access_key=secret if secret else None,
    )
    _client_cache[cache_key] = client
    return client


def is_s3_enabled() -> bool:
    settings = load_settings()
    if not settings.s3_enabled:
        return False
    if not settings.s3_bucket:
        return False
    key_id, secret = _get_credentials()
    return bool(key_id and secret)


def _content_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def upload_file(local_path: Path, s3_key: str) -> str:
    """Upload a single file to S3. Returns the public URL."""
    settings = load_settings()
    client = get_s3_client()
    client.upload_file(
        str(local_path),
        settings.s3_bucket,
        s3_key,
        ExtraArgs={"ContentType": _content_type(local_path)},
    )
    return get_public_url(s3_key)


def upload_directory(local_dir: Path, s3_prefix: str) -> int:
    """Recursively upload a local directory to S3. Returns file count."""
    if not local_dir.is_dir():
        return 0
    count = 0
    for file_path in sorted(local_dir.rglob("*")):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(local_dir)
        s3_key = f"{s3_prefix}/{relative}"
        upload_file(file_path, s3_key)
        count += 1
    return count


def download_file(s3_key: str, local_path: Path) -> bool:
    """Download a file from S3. Returns True on success."""
    settings = load_settings()
    client = get_s3_client()
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        client.download_file(settings.s3_bucket, s3_key, str(local_path))
        return True
    except ClientError:
        return False


def get_public_url(s3_key: str) -> str:
    """Return the public URL for an S3 object."""
    settings = load_settings()
    return f"https://{settings.s3_bucket}.s3.{settings.s3_region}.amazonaws.com/{s3_key}"


def get_final_video_url(slug: str) -> str | None:
    """Return the public URL for a final video if it exists in S3.

    Checks captioned variant first, then uncaptioned.
    """
    settings = load_settings()
    if not is_s3_enabled():
        return None

    prefix = settings.s3_prefix
    client = get_s3_client()
    bucket = settings.s3_bucket

    for suffix in [f"_captioned.mp4", ".mp4"]:
        key = f"{prefix}/{slug}/output/mixed/final_{slug}{suffix}"
        try:
            client.head_object(Bucket=bucket, Key=key)
            return get_public_url(key)
        except ClientError:
            continue

    captioned_key = f"{prefix}/{slug}/output/captioned/final_{slug}_captioned.mp4"
    try:
        client.head_object(Bucket=bucket, Key=captioned_key)
        return get_public_url(captioned_key)
    except ClientError:
        pass

    return None


def sync_episode_outputs(ep_dir: Path, slug: str) -> int:
    """Sync all output subdirectories and metadata for an episode to S3.

    Returns total number of files uploaded.
    """
    if not is_s3_enabled():
        return 0

    settings = load_settings()
    prefix = f"{settings.s3_prefix}/{slug}"
    total = 0

    for subdir in SYNC_SUBDIRS:
        local = ep_dir / subdir
        if local.is_dir():
            s3_sub = f"{prefix}/{subdir}"
            count = upload_directory(local, s3_sub)
            if count:
                total += count

    for meta_file in METADATA_FILES:
        local = ep_dir / meta_file
        if local.is_file():
            s3_key = f"{prefix}/{meta_file}"
            upload_file(local, s3_key)
            total += 1

    for txt_dir_name in ["02_image_prompts", "03_veo_video_prompts"]:
        txt_dir = ep_dir / txt_dir_name
        if txt_dir.is_dir():
            count = upload_directory(txt_dir, f"{prefix}/{txt_dir_name}")
            total += count

    return total


def sync_directory(ep_dir: Path, slug: str, subdir: str) -> int:
    """Sync a single output subdirectory for an episode to S3.

    Args:
        ep_dir: Local episode directory.
        slug: Episode slug.
        subdir: Relative path under ep_dir, e.g. "output/images".

    Returns number of files uploaded.
    """
    if not is_s3_enabled():
        return 0

    settings = load_settings()
    local = ep_dir / subdir
    if not local.is_dir():
        return 0

    s3_prefix = f"{settings.s3_prefix}/{slug}/{subdir}"
    return upload_directory(local, s3_prefix)
