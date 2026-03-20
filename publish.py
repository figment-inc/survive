#!/usr/bin/env python3
"""
You Wouldn't Wanna Be — Metricool Publishing CLI

Publish a finished episode video to Instagram, TikTok, and YouTube via Metricool.

Usage:
  python publish.py --episode pompeii-79 --media-url https://example.com/video.mp4
  python publish.py --episode pompeii-79 --media-url https://... --schedule "2026-03-10T14:00:00"
  python publish.py --episode pompeii-79 --media-url https://... --title "Custom Title"
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.config import load_settings, REPO_DIR
from lib.metricool import publish_to_metricool
from lib.sources import format_sources_comment


def main():
    parser = argparse.ArgumentParser(
        description="Publish episode video to social platforms via Metricool"
    )
    parser.add_argument("--episode", required=True, help="Episode slug (directory name)")
    parser.add_argument("--media-url", required=True, help="Public URL of the video file")
    parser.add_argument("--title", default="", help="Video title (defaults to episode-based title)")
    parser.add_argument("--caption", default="", help="Default caption text")
    parser.add_argument("--caption-instagram", default="", help="Instagram-specific caption")
    parser.add_argument("--caption-tiktok", default="", help="TikTok-specific caption")
    parser.add_argument("--caption-youtube", default="", help="YouTube-specific caption/description")
    parser.add_argument("--schedule", default="", help="ISO datetime to schedule (default: now + 2min)")
    parser.add_argument("--first-comment", default="", help="First comment text (e.g., a link)")
    parser.add_argument("--dry-run", action="store_true", help="Print config without publishing")
    args = parser.parse_args()

    settings = load_settings()

    episode_dir = REPO_DIR / args.episode
    if not episode_dir.is_dir():
        print(f"ERROR: Episode directory not found: {episode_dir}")
        sys.exit(1)

    first_comment = args.first_comment
    if not first_comment:
        sources_path = episode_dir / "05_sources.json"
        if sources_path.exists():
            try:
                sources = json.loads(sources_path.read_text())
                first_comment = format_sources_comment(sources)
                if first_comment:
                    print(f"  Auto-loaded sources from {sources_path.name} ({len(sources)} entries)")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  WARNING: Failed to parse {sources_path.name}: {e}")

    title = args.title
    if not title:
        slug_parts = args.episode.replace("-", " ").replace("_", " ").split()
        title = f"You Wouldn't Wanna Be — {' '.join(w.capitalize() for w in slug_parts)}"

    caption = args.caption or f"{title} #history #education #shorts"

    print(f"{'=' * 60}")
    print(f"  METRICOOL PUBLISH")
    print(f"{'=' * 60}")
    print(f"  Episode:      {args.episode}")
    print(f"  Title:        {title}")
    print(f"  Media URL:    {args.media_url}")
    print(f"  Schedule:     {args.schedule or 'now + 2min'}")
    print(f"  Platforms:    {', '.join(settings.metricool_target_platforms)}")
    print(f"  Publish on:   {'ENABLED' if settings.metricool_publish_enabled else 'DISABLED'}")
    if first_comment:
        print(f"  1st comment:  {first_comment[:60]}{'...' if len(first_comment) > 60 else ''}")
    print(f"{'=' * 60}")

    if args.dry_run:
        print("\n  DRY RUN — no publish action taken.")
        return

    result = publish_to_metricool(
        settings=settings,
        media_url=args.media_url,
        title=title,
        caption=caption,
        caption_instagram=args.caption_instagram,
        caption_tiktok=args.caption_tiktok,
        caption_youtube=args.caption_youtube,
        desired_publish_at=args.schedule,
        first_comment=first_comment,
    )

    print(f"\n  Status:          {result.status}")
    if result.external_post_id:
        print(f"  Post ID:         {result.external_post_id}")
    if result.http_status:
        print(f"  HTTP Status:     {result.http_status}")
    if result.error_message:
        print(f"  Error:           {result.error_message}")

    if result.status == "published":
        print(f"\n  Published successfully!")
    elif result.status == "skipped":
        print(f"\n  Publishing skipped. Check METRICOOL_PUBLISH_ENABLED in .env.")
    else:
        print(f"\n  Publishing failed. Check credentials and configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main()
