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

    3-step flow:
      1. Create upload transaction (get presigned URL)
      2. Upload file to S3 via presigned PUT
      3. Complete transaction (get final hosted URL)
    """
    from pathlib import Path
    import hashlib

    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Media file not found: {file_path}")

    file_size = p.stat().st_size
    mime = "video/mp4" if p.suffix.lower() == ".mp4" else "application/octet-stream"
    base_url = settings.metricool_api_url.rstrip("/")
    auth_params = _metricool_auth_query(settings)
    headers_auth = {"X-Mc-Auth": settings.metricool_user_token}

    file_data = p.read_bytes()
    md5_hash = hashlib.md5(file_data).hexdigest()

    LOGGER.info("Creating upload transaction for %s (%d bytes)", p.name, file_size)

    create_resp = requests.put(
        f"{base_url}/v2/media/s3/upload-transactions",
        params=auth_params,
        headers={**headers_auth, "Content-Type": "application/json"},
        json={
            "resourceType": "planner",
            "contentType": mime,
            "parts": [{
                "size": file_size,
                "startByte": 0,
                "endByte": file_size,
                "hash": md5_hash,
            }],
        },
        timeout=60,
    )
    create_resp.raise_for_status()
    upload_info = create_resp.json()

    upload_type = upload_info.get("uploadType", "SIMPLE")
    s3_key = upload_info.get("key", "")

    if upload_type == "SIMPLE":
        presigned_url = upload_info.get("fileUrl", "")
        if not presigned_url:
            raise RuntimeError(f"No presigned URL in upload response: {upload_info}")

        LOGGER.info("Uploading to S3 (simple): %s", presigned_url[:80])
        put_resp = requests.put(
            presigned_url,
            data=file_data,
            headers={"Content-Type": mime},
            timeout=300,
        )
        put_resp.raise_for_status()

        complete_resp = requests.patch(
            f"{base_url}/v2/media/s3/upload-transactions",
            params=auth_params,
            headers={**headers_auth, "Content-Type": "application/json"},
            json={"simple": {"fileUrl": presigned_url.split("?")[0]}},
            timeout=60,
        )
        complete_resp.raise_for_status()
        complete_data = complete_resp.json()
        final_url = complete_data.get("fileUrl") or complete_data.get("url", presigned_url.split("?")[0])

    else:
        parts_info = upload_info.get("parts", [])
        upload_id = upload_info.get("uploadId", "")
        completed_parts = []

        for part in parts_info:
            part_url = part.get("presignedUrl", "")
            part_num = part.get("partNumber", 1)
            start = part.get("startByte", 0)
            end = part.get("endByte", file_size)
            chunk = file_data[start:end]

            LOGGER.info("Uploading part %d (%d bytes)", part_num, len(chunk))
            put_resp = requests.put(
                part_url,
                data=chunk,
                headers={"Content-Type": mime},
                timeout=300,
            )
            put_resp.raise_for_status()
            etag = put_resp.headers.get("ETag", "")
            completed_parts.append({"partNumber": part_num, "etag": etag})

        complete_resp = requests.patch(
            f"{base_url}/v2/media/s3/upload-transactions",
            params=auth_params,
            headers={**headers_auth, "Content-Type": "application/json"},
            json={
                "multipart": {
                    "uploadId": upload_id,
                    "key": s3_key,
                    "parts": completed_parts,
                }
            },
            timeout=60,
        )
        complete_resp.raise_for_status()
        complete_data = complete_resp.json()
        final_url = complete_data.get("fileUrl") or complete_data.get("url", "")

    LOGGER.info("Upload complete: %s", final_url[:80] if final_url else "(no URL)")
    return final_url


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
        "saveExternalMediaFiles": False,
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
                "category": "27",
                "privacyStatus": "public",
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
