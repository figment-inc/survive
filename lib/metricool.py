"""Metricool multi-platform publishing (adapted from news/pipeline/publish.py)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from lib.config import Settings

LOGGER = logging.getLogger(__name__)

BLOCKED_PROVIDERS = {"twitter", "x"}

PROVIDER_MAP = {
    "instagram": "instagram",
    "tiktok": "tiktok",
    "youtube": "youtube",
    "facebook": "facebook",
    "twitter": "twitter",
    "x": "twitter",
}


@dataclass
class PublishResult:
    status: str
    external_post_id: Optional[str]
    error_message: Optional[str]
    http_status: Optional[int]
    response_payload: dict


def _metricool_headers(settings: Settings) -> dict[str, str]:
    return {
        "X-Mc-Auth": settings.metricool_user_token,
        "Content-Type": "application/json",
    }


def _metricool_auth_query(settings: Settings) -> dict[str, str]:
    return {
        "userId": settings.metricool_user_id,
        "blogId": settings.metricool_blog_id,
    }


def _metricool_provider(platform: str) -> str:
    return PROVIDER_MAP.get(platform.lower(), platform.lower())


def _metricool_publication_datetime(desired: str = "") -> str:
    """Return ISO datetime for Metricool. Defaults to 2 minutes from now."""
    if desired and desired.lower() not in ("", "none", "now"):
        return desired
    publish_at = datetime.now(timezone.utc) + timedelta(minutes=2)
    return publish_at.strftime("%Y-%m-%dT%H:%M:%S")


def _metricool_normalize_media_url(settings: Settings, media_url: str) -> str:
    """Normalize a media URL via Metricool's normalize endpoint."""
    if not media_url:
        return media_url
    endpoint = f"{settings.metricool_api_url.rstrip('/')}/actions/normalize/image/url"
    resp = requests.post(
        endpoint,
        params=_metricool_auth_query(settings=settings),
        json={"url": media_url},
        headers=_metricool_headers(settings=settings),
        timeout=settings.request_timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("url", media_url)


def upload_media_file(settings: Settings, file_path: str) -> str:
    """Upload a local video file to Metricool via S3 presigned upload and return the hosted URL.

    Uses the same pattern as excellenthistory: sha256 hash, fileExtension field.
    """
    from pathlib import Path
    import hashlib
    import base64

    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Media file not found: {file_path}")

    file_size = p.stat().st_size
    base_url = settings.metricool_api_url.rstrip("/")
    auth_params = _metricool_auth_query(settings)
    headers = {
        "X-Mc-Auth": settings.metricool_user_token,
        "Content-Type": "application/json",
    }

    LOGGER.info("Uploading %s (%d bytes) to Metricool S3...", p.name, file_size)

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    sha256_hash = base64.b64encode(hashlib.sha256(file_bytes).digest()).decode()

    tx_body = {
        "resourceType": "planner",
        "contentType": "video/mp4",
        "fileExtension": "mp4",
        "parts": [{
            "size": file_size,
            "startByte": 0,
            "endByte": file_size,
            "hash": sha256_hash,
        }],
    }

    tx_resp = requests.put(
        f"{base_url}/v2/media/s3/upload-transactions",
        params=auth_params,
        headers=headers,
        json=tx_body,
        timeout=30,
    )
    LOGGER.info("Create transaction status: %d", tx_resp.status_code)

    if tx_resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create upload transaction: {tx_resp.status_code} {tx_resp.text[:300]}")

    tx_data = tx_resp.json()
    file_url = tx_data.get("fileUrl")

    presigned_url = tx_data.get("presignedUrl")
    if not presigned_url and tx_data.get("parts"):
        presigned_url = tx_data["parts"][0].get("presignedUrl")

    if not presigned_url:
        raise RuntimeError(f"No presigned URL in response: {tx_data}")

    LOGGER.info("Uploading to S3 presigned URL...")
    upload_resp = requests.put(
        presigned_url,
        data=file_bytes,
        headers={"Content-Type": "video/mp4"},
        timeout=600,
    )

    if upload_resp.status_code not in (200, 201):
        raise RuntimeError(f"S3 upload failed: {upload_resp.status_code} {upload_resp.text[:200]}")

    if file_url:
        LOGGER.info("Metricool S3 file URL: %s", file_url[:80])
        return file_url

    s3_key = tx_data.get("key")
    s3_bucket = tx_data.get("bucket")
    if s3_key and s3_bucket:
        constructed_url = f"https://{s3_bucket}.s3.eu-west-1.amazonaws.com/{s3_key}"
        LOGGER.info("Constructed S3 URL: %s", constructed_url[:80])
        return constructed_url

    raise RuntimeError("No file URL available after upload")


def upload_image_file(settings: Settings, file_path: str) -> str:
    """Upload a local image file to Metricool via S3 presigned upload and return the hosted URL."""
    import hashlib
    import base64

    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Image file not found: {file_path}")

    ext = p.suffix.lstrip(".").lower()
    content_type_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
    content_type = content_type_map.get(ext, "image/png")

    file_size = p.stat().st_size
    base_url = settings.metricool_api_url.rstrip("/")
    auth_params = _metricool_auth_query(settings)
    headers = {
        "X-Mc-Auth": settings.metricool_user_token,
        "Content-Type": "application/json",
    }

    LOGGER.info("Uploading image %s (%d bytes) to Metricool S3...", p.name, file_size)

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    sha256_hash = base64.b64encode(hashlib.sha256(file_bytes).digest()).decode()

    tx_body = {
        "resourceType": "planner",
        "contentType": content_type,
        "fileExtension": ext if ext != "jpeg" else "jpg",
        "parts": [{
            "size": file_size,
            "startByte": 0,
            "endByte": file_size,
            "hash": sha256_hash,
        }],
    }

    tx_resp = requests.put(
        f"{base_url}/v2/media/s3/upload-transactions",
        params=auth_params,
        headers=headers,
        json=tx_body,
        timeout=30,
    )
    LOGGER.info("Create image upload transaction status: %d", tx_resp.status_code)

    if tx_resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create image upload transaction: {tx_resp.status_code} {tx_resp.text[:300]}")

    tx_data = tx_resp.json()
    file_url = tx_data.get("fileUrl")

    presigned_url = tx_data.get("presignedUrl")
    if not presigned_url and tx_data.get("parts"):
        presigned_url = tx_data["parts"][0].get("presignedUrl")

    if not presigned_url:
        raise RuntimeError(f"No presigned URL in image upload response: {tx_data}")

    LOGGER.info("Uploading image to S3 presigned URL...")
    upload_resp = requests.put(
        presigned_url,
        data=file_bytes,
        headers={"Content-Type": content_type},
        timeout=120,
    )

    if upload_resp.status_code not in (200, 201):
        raise RuntimeError(f"S3 image upload failed: {upload_resp.status_code} {upload_resp.text[:200]}")

    if file_url:
        LOGGER.info("Metricool S3 image URL: %s", file_url[:80])
        return file_url

    s3_key = tx_data.get("key")
    s3_bucket = tx_data.get("bucket")
    if s3_key and s3_bucket:
        constructed_url = f"https://{s3_bucket}.s3.eu-west-1.amazonaws.com/{s3_key}"
        LOGGER.info("Constructed image S3 URL: %s", constructed_url[:80])
        return constructed_url

    raise RuntimeError("No file URL available after image upload")


def _extract_post_id(response_payload: dict) -> Optional[str]:
    """Extract external post ID from Metricool response."""
    if isinstance(response_payload, dict):
        for key in ("id", "postId", "post_id"):
            if key in response_payload:
                return str(response_payload[key])
        data = response_payload.get("data", {})
        if isinstance(data, dict):
            for key in ("id", "postId", "post_id"):
                if key in data:
                    return str(data[key])
    return None


def publish_to_metricool(
    settings: Settings,
    media_url: str = "",
    media_file_path: str = "",
    title: str = "",
    caption: str = "",
    caption_instagram: str = "",
    caption_tiktok: str = "",
    caption_youtube: str = "",
    desired_publish_at: str = "",
    first_comment: str = "",
) -> PublishResult:
    """Publish a video to multiple platforms via Metricool.

    Args:
        settings: App settings with Metricool credentials.
        media_url: Public URL of the video file.
        media_file_path: Local file path to upload directly (used if media_url is empty).
        title: Video title (used for YouTube).
        caption: Default caption (used for TikTok base text).
        caption_instagram: Override caption for Instagram.
        caption_tiktok: Override caption for TikTok.
        caption_youtube: Override caption for YouTube.
        desired_publish_at: ISO datetime string, or empty for "now + 2min".
        first_comment: First comment text (e.g., a link).
    """
    if not settings.metricool_publish_enabled:
        return PublishResult(
            status="skipped",
            external_post_id=None,
            error_message="Metricool publish is disabled",
            http_status=None,
            response_payload={},
        )

    if not settings.metricool_user_token:
        return PublishResult(
            status="failed",
            external_post_id=None,
            error_message="METRICOOL_USER_TOKEN not configured",
            http_status=None,
            response_payload={},
        )

    endpoint = f"{settings.metricool_api_url.rstrip('/')}/v2/scheduler/posts"

    if not media_url and media_file_path:
        try:
            LOGGER.info("No media_url provided, uploading file directly: %s", media_file_path)
            media_url = upload_media_file(settings, media_file_path)
        except Exception as exc:
            return PublishResult(
                status="failed",
                external_post_id=None,
                error_message=f"File upload failed: {exc}",
                http_status=None,
                response_payload={},
            )

    try:
        normalized_media_url = _metricool_normalize_media_url(settings=settings, media_url=media_url)
    except requests.RequestException as exc:
        LOGGER.warning("Metricool media URL normalization failed, using original: %s", str(exc))
        normalized_media_url = media_url

    publication_date = {
        "dateTime": _metricool_publication_datetime(desired_publish_at),
        "timezone": settings.metricool_schedule_timezone,
    }

    providers: list[dict[str, str]] = []
    request_payload: dict[str, Any] = {
        "text": caption_tiktok or caption,
        "firstCommentText": first_comment,
        "providers": providers,
        "autoPublish": True,
        "saveExternalMediaFiles": True,
        "shortener": False,
        "draft": False,
        "media": [normalized_media_url] if normalized_media_url else [],
        "publicationDate": publication_date,
    }

    for platform in settings.metricool_target_platforms:
        provider_name = _metricool_provider(platform)
        if provider_name in BLOCKED_PROVIDERS:
            LOGGER.info("Skipping blocked provider: %s", provider_name)
            continue
        providers.append({"network": provider_name})

        if provider_name == "instagram":
            request_payload["instagramData"] = {
                "autoPublish": True,
                "type": "REEL",
                "showReelOnFeed": True,
            }
        if provider_name == "youtube":
            video_title = (title or caption[:100] or "You Wouldn't Wanna Be").strip()[:100]
            request_payload["youtubeData"] = {
                "title": video_title,
                "type": "SHORT",
                "category": "EDUCATION",
                "privacy": "public",
                "madeForKids": False,
            }
        if provider_name == "tiktok":
            request_payload["tiktokData"] = {
                "privacyOption": "PUBLIC_TO_EVERYONE",
                "disableComment": False,
                "disableDuet": False,
                "disableStitch": False,
            }

    if not providers:
        return PublishResult(
            status="failed",
            external_post_id=None,
            error_message="No eligible Metricool providers after filtering",
            http_status=None,
            response_payload={},
        )

    provider_names = [p["network"] for p in providers]
    LOGGER.info("Publishing to Metricool: providers=%s", provider_names)

    try:
        response = requests.post(
            endpoint,
            params=_metricool_auth_query(settings=settings),
            json=request_payload,
            headers=_metricool_headers(settings=settings),
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        response_payload = response.json() if response.content else {}
        external_post_id = _extract_post_id(response_payload)

        return PublishResult(
            status="published",
            external_post_id=external_post_id,
            error_message=None,
            http_status=response.status_code,
            response_payload=response_payload,
        )

    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        body = exc.response.text[:500] if exc.response is not None else ""
        return PublishResult(
            status="failed",
            external_post_id=None,
            error_message=f"HTTP {status_code}: {body}",
            http_status=status_code,
            response_payload={},
        )

    except requests.RequestException as exc:
        return PublishResult(
            status="failed",
            external_post_id=None,
            error_message=f"Request error: {exc}",
            http_status=None,
            response_payload={},
        )


def publish_carousel_to_metricool(
    settings: Settings,
    image_paths: list[Path] | None = None,
    media_urls: list[str] | None = None,
    caption: str = "",
    desired_publish_at: str = "",
    first_comment: str = "",
) -> PublishResult:
    """Publish an Instagram carousel post with multiple images via Metricool.

    Uploads each image to Metricool S3 (or uses pre-resolved media_urls as
    fallback), then schedules a single POST-type Instagram post with all images
    in the media array. Instagram only.
    """
    if not settings.metricool_publish_enabled:
        return PublishResult(
            status="skipped",
            external_post_id=None,
            error_message="Metricool publish is disabled",
            http_status=None,
            response_payload={},
        )

    if not settings.metricool_user_token:
        return PublishResult(
            status="failed",
            external_post_id=None,
            error_message="METRICOOL_USER_TOKEN not configured",
            http_status=None,
            response_payload={},
        )

    if not image_paths and not media_urls:
        return PublishResult(
            status="failed",
            external_post_id=None,
            error_message="No carousel images or URLs provided",
            http_status=None,
            response_payload={},
        )

    resolved_urls: list[str] = list(media_urls or [])

    if image_paths and not resolved_urls:
        for img_path in image_paths:
            try:
                url = upload_image_file(settings, str(img_path))
                normalized = _metricool_normalize_media_url(settings, url)
                resolved_urls.append(normalized)
                LOGGER.info("Carousel image uploaded: %s -> %s", img_path.name, normalized[:60])
            except Exception as exc:
                LOGGER.warning("Failed to upload carousel image %s: %s", img_path.name, exc)

    resolved_urls = [u for u in resolved_urls if u]
    if not resolved_urls:
        return PublishResult(
            status="failed",
            external_post_id=None,
            error_message="All carousel image uploads failed",
            http_status=None,
            response_payload={},
        )

    endpoint = f"{settings.metricool_api_url.rstrip('/')}/v2/scheduler/posts"

    publication_date = {
        "dateTime": _metricool_publication_datetime(desired_publish_at),
        "timezone": settings.metricool_schedule_timezone,
    }

    request_payload: dict[str, Any] = {
        "text": caption,
        "firstCommentText": first_comment,
        "providers": [{"network": "instagram"}],
        "autoPublish": True,
        "saveExternalMediaFiles": True,
        "shortener": False,
        "draft": False,
        "media": resolved_urls,
        "publicationDate": publication_date,
        "instagramData": {
            "autoPublish": True,
            "type": "POST",
        },
    }

    LOGGER.info(
        "Publishing Instagram carousel: %d images, schedule=%s",
        len(resolved_urls), publication_date["dateTime"],
    )

    try:
        response = requests.post(
            endpoint,
            params=_metricool_auth_query(settings=settings),
            json=request_payload,
            headers=_metricool_headers(settings=settings),
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        response_payload = response.json() if response.content else {}
        external_post_id = _extract_post_id(response_payload)

        return PublishResult(
            status="published",
            external_post_id=external_post_id,
            error_message=None,
            http_status=response.status_code,
            response_payload=response_payload,
        )

    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        body = exc.response.text[:500] if exc.response is not None else ""
        return PublishResult(
            status="failed",
            external_post_id=None,
            error_message=f"HTTP {status_code}: {body}",
            http_status=status_code,
            response_payload={},
        )

    except requests.RequestException as exc:
        return PublishResult(
            status="failed",
            external_post_id=None,
            error_message=f"Request error: {exc}",
            http_status=None,
            response_payload={},
        )
