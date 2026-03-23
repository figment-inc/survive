#!/usr/bin/env python3
"""
You Wouldn't Wanna Be — Metricool Publishing CLI

Publish a finished episode video to Instagram, TikTok, and YouTube via Metricool.
Optionally publish an Instagram carousel of polaroid-framed story slides.

Usage:
  python publish.py --episode pompeii-79 --media-url https://example.com/video.mp4
  python publish.py --episode pompeii-79 --media-url https://... --schedule "2026-03-10T14:00:00"
  python publish.py --episode pompeii-79 --carousel
  python publish.py --episode pompeii-79 --media-url https://... --carousel
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lib.config import load_settings, REPO_DIR
from lib.metricool import publish_to_metricool
from lib.sources import format_sources_comment


def _build_sentence_data(episode_dir: Path) -> list[dict]:
    """Reconstruct sentence_images data from on-disk files."""
    from lib.slideshow import parse_narration_sentences, assign_image_counts

    script_path = episode_dir / "04_dialogue_script.txt"
    if not script_path.exists():
        return []

    sentences = parse_narration_sentences(script_path.read_text())
    sentences = assign_image_counts(sentences)

    images_dir = episode_dir / "output" / "images"
    result: list[dict] = []

    for s in sentences:
        s_idx = s.index
        image_prompts = []
        for p_idx in range(1, s.image_count + 1):
            fname = f"sentence_{s_idx:02d}_img_{p_idx:02d}.png"
            if (images_dir / fname).exists():
                image_prompts.append(fname)
        if image_prompts:
            result.append({
                "sentence_index": s_idx,
                "text": s.text,
                "image_prompts": image_prompts,
            })

    return result


def _publish_carousel(args, settings, episode_dir, title, first_comment):
    """Generate polaroid images and publish as Instagram carousel."""
    from lib.metricool import publish_carousel_to_metricool
    from lib.polaroid import create_carousel_images

    sentence_data = _build_sentence_data(episode_dir)
    if not sentence_data:
        print("  ERROR: No sentence data found. Need 04_dialogue_script.txt and output/images/")
        sys.exit(1)

    print(f"  Generating polaroid carousel from {len(sentence_data)} sentences...")
    carousel_paths = create_carousel_images(episode_dir, sentence_data)

    if not carousel_paths:
        print("  ERROR: No carousel images generated.")
        sys.exit(1)

    print(f"  Generated {len(carousel_paths)} polaroid slides")

    hook_line = ""
    script_path = episode_dir / "04_dialogue_script.txt"
    if script_path.exists():
        from lib.slideshow import parse_narration_sentences
        sents = parse_narration_sentences(script_path.read_text())
        if sents:
            hook_line = sents[0].text

    caption = (
        f"{title}\n\n"
        f"{hook_line}\n\n"
        f"Swipe through the full story \u2192\n\n"
        f"#YouWouldntWannaBe #History #HistoryFacts "
        f"#DarkHistory #Education"
    )

    carousel_schedule = ""
    if args.schedule:
        from datetime import datetime, timedelta
        try:
            base_dt = datetime.fromisoformat(args.schedule)
            carousel_dt = base_dt + timedelta(minutes=3)
            carousel_schedule = carousel_dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            carousel_schedule = args.schedule

    if args.dry_run:
        print(f"\n  DRY RUN — carousel has {len(carousel_paths)} images, would publish to Instagram.")
        for p in carousel_paths:
            print(f"    {p.name}")
        return

    # Try S3 first; fall back to GitHub Release if S3 is disabled
    from lib.metricool import upload_image_file
    media_urls = None
    try:
        upload_image_file(settings, str(carousel_paths[0]))
        print("  S3 upload available — using direct upload")
    except Exception:
        print("  Metricool S3 disabled — uploading carousel to GitHub Release...")
        media_urls = _upload_carousel_to_github(args.episode, carousel_paths)
        if not media_urls:
            print("  ERROR: GitHub Release upload failed.")
            sys.exit(1)
        print(f"  Uploaded {len(media_urls)} images to GitHub Release")

    result = publish_carousel_to_metricool(
        settings=settings,
        image_paths=carousel_paths if media_urls is None else None,
        media_urls=media_urls,
        caption=caption,
        desired_publish_at=carousel_schedule,
        first_comment=first_comment,
    )

    print(f"\n  Carousel Status:     {result.status}")
    if result.external_post_id:
        print(f"  Carousel Post ID:    {result.external_post_id}")
    if result.http_status:
        print(f"  HTTP Status:         {result.http_status}")
    if result.error_message:
        print(f"  Error:               {result.error_message}")

    if result.status == "published":
        print(f"\n  Carousel published successfully!")
    elif result.status == "skipped":
        print(f"\n  Carousel skipped. Check METRICOOL_PUBLISH_ENABLED in .env.")
    else:
        print(f"\n  Carousel publishing failed.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Publish episode video to social platforms via Metricool"
    )
    parser.add_argument("--episode", required=True, help="Episode slug (directory name)")
    parser.add_argument("--media-url", default="", help="Public URL of the video file")
    parser.add_argument("--title", default="", help="Video title (defaults to episode-based title)")
    parser.add_argument("--caption", default="", help="Default caption text")
    parser.add_argument("--caption-instagram", default="", help="Instagram-specific caption")
    parser.add_argument("--caption-tiktok", default="", help="TikTok-specific caption")
    parser.add_argument("--caption-youtube", default="", help="YouTube-specific caption/description")
    parser.add_argument("--schedule", default="", help="ISO datetime to schedule (default: now + 2min)")
    parser.add_argument("--first-comment", default="", help="First comment text (e.g., a link)")
    parser.add_argument("--carousel", action="store_true", help="Publish Instagram carousel of polaroid story slides")
    parser.add_argument("--dry-run", action="store_true", help="Print config without publishing")
    args = parser.parse_args()

    if not args.media_url and not args.carousel:
        parser.error("--media-url is required unless using --carousel")

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
        title = f"You Wouldn't Wanna Be \u2014 {' '.join(w.capitalize() for w in slug_parts)}"

    caption = args.caption or f"{title} #history #education #shorts"

    if args.media_url:
        print(f"{'=' * 60}")
        print(f"  METRICOOL PUBLISH — REEL")
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

        if not args.dry_run:
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
                print(f"\n  Reel published successfully!")
            elif result.status == "skipped":
                print(f"\n  Publishing skipped. Check METRICOOL_PUBLISH_ENABLED in .env.")
            else:
                print(f"\n  Publishing failed. Check credentials and configuration.")
                sys.exit(1)
        else:
            print("\n  DRY RUN — reel publish skipped.")

    if args.carousel:
        print(f"\n{'=' * 60}")
        print(f"  METRICOOL PUBLISH — INSTAGRAM CAROUSEL")
        print(f"{'=' * 60}")
        print(f"  Episode:      {args.episode}")
        print(f"  Title:        {title}")
        print(f"  Publish on:   {'ENABLED' if settings.metricool_publish_enabled else 'DISABLED'}")
        print(f"{'=' * 60}")

        _publish_carousel(args, settings, episode_dir, title, first_comment)


def _upload_carousel_to_github(episode_slug, carousel_paths):
    """Upload carousel PNGs to the episode's GitHub Release and return direct URLs."""
    import subprocess
    import requests as _requests

    tag = f"episode-{episode_slug}"

    for img_path in carousel_paths:
        result = subprocess.run(
            ["gh", "release", "upload", tag, str(img_path), "--clobber"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  Failed to upload {img_path.name}: {result.stderr.strip()}")
            return None

    view_result = subprocess.run(
        ["gh", "release", "view", tag, "--json", "assets"],
        capture_output=True, text=True,
    )
    if view_result.returncode != 0:
        return None

    assets = json.loads(view_result.stdout).get("assets", [])
    asset_map = {a["name"]: a["url"] for a in assets}

    urls = []
    for img_path in carousel_paths:
        gh_url = asset_map.get(img_path.name)
        if not gh_url:
            continue
        try:
            resp = _requests.head(gh_url, allow_redirects=False, timeout=10)
            if resp.status_code in (301, 302) and "location" in resp.headers:
                urls.append(resp.headers["location"])
            else:
                urls.append(gh_url)
        except _requests.RequestException:
            urls.append(gh_url)

    return urls if urls else None


if __name__ == "__main__":
    main()
