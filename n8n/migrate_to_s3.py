#!/usr/bin/env python3
"""One-time migration: upload all existing episode outputs to S3.

Usage:
  python -u n8n/migrate_to_s3.py                    # upload everything
  python -u n8n/migrate_to_s3.py --dry-run           # preview only
  python -u n8n/migrate_to_s3.py --episode pompeii-79 # single episode
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))


def ts():
    return datetime.now().strftime("%H:%M:%S")


def find_episode_dirs(repo: Path, single: str | None = None) -> list[Path]:
    """Discover episode directories that have an output/ subdirectory."""
    skip = {"lib", "n8n", "output", "__pycache__", "node_modules"}
    dirs = []
    for d in sorted(repo.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith((".", "_")):
            continue
        if d.name in skip:
            continue
        if single and d.name != single:
            continue
        if (d / "output").is_dir():
            dirs.append(d)
    return dirs


def count_files(directory: Path) -> tuple[int, int]:
    """Return (file_count, total_bytes) for a directory tree."""
    total_files = 0
    total_bytes = 0
    for f in directory.rglob("*"):
        if f.is_file():
            total_files += 1
            total_bytes += f.stat().st_size
    return total_files, total_bytes


def format_size(nbytes: int) -> str:
    if nbytes >= 1 << 30:
        return f"{nbytes / (1 << 30):.1f} GB"
    if nbytes >= 1 << 20:
        return f"{nbytes / (1 << 20):.1f} MB"
    return f"{nbytes / (1 << 10):.1f} KB"


def main():
    parser = argparse.ArgumentParser(description="Migrate episode outputs to S3")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be uploaded without uploading")
    parser.add_argument("--episode", type=str, help="Upload a single episode by slug")
    args = parser.parse_args()

    from lib.s3 import is_s3_enabled, sync_episode_outputs

    if not is_s3_enabled():
        print("ERROR: S3 is not enabled. Set S3_ENABLED=true in .env with valid credentials.")
        sys.exit(1)

    from lib.config import load_settings
    settings = load_settings()
    print(f"S3 bucket: {settings.s3_bucket}")
    print(f"S3 prefix: {settings.s3_prefix}")
    print(f"S3 region: {settings.s3_region}")

    episodes = find_episode_dirs(REPO_DIR, single=args.episode)

    if not episodes:
        if args.episode:
            print(f"No episode found with slug '{args.episode}' that has an output/ directory.")
        else:
            print("No episode directories with output/ found.")
        sys.exit(1)

    print(f"\nFound {len(episodes)} episode(s) to migrate.\n")

    grand_files = 0
    grand_bytes = 0

    for i, ep_dir in enumerate(episodes, 1):
        slug = ep_dir.name
        file_count, byte_count = count_files(ep_dir / "output")

        meta_count = 0
        meta_bytes = 0
        for name in ["episode.json", "01_storyboard.md", "00_draft_script.txt",
                      "00_critique.md", "04_dialogue_script.txt"]:
            p = ep_dir / name
            if p.is_file():
                meta_count += 1
                meta_bytes += p.stat().st_size
        for txt_dir_name in ["02_image_prompts", "03_veo_video_prompts"]:
            txt_dir = ep_dir / txt_dir_name
            if txt_dir.is_dir():
                fc, fb = count_files(txt_dir)
                meta_count += fc
                meta_bytes += fb

        total_files = file_count + meta_count
        total_bytes = byte_count + meta_bytes
        grand_files += total_files
        grand_bytes += total_bytes

        status = f"[{i}/{len(episodes)}] {slug}: {total_files} files ({format_size(total_bytes)})"

        if args.dry_run:
            print(f"  DRY RUN  {status}")
            continue

        print(f"  [{ts()}] {status} ... ", end="", flush=True)
        uploaded = sync_episode_outputs(ep_dir, slug)
        print(f"done ({uploaded} uploaded)")

    print(f"\n{'=' * 60}")
    action = "Would upload" if args.dry_run else "Uploaded"
    print(f"  {action}: {grand_files} files ({format_size(grand_bytes)}) across {len(episodes)} episodes")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
