#!/usr/bin/env python3
"""
Regenerate an existing episode from its on-disk files.

Reconstructs the episode dict from storyboard + dialogue script + prompts,
then runs: audio -> mix -> stitch -> captions -> publish.

Keeps existing images and video clips intact (only regenerates audio-dependent artifacts).

Usage:
  python _regenerate_episode.py mount-pelee-martinique-1902
  python _regenerate_episode.py mount-pelee-martinique-1902 --publish
  python _regenerate_episode.py mount-pelee-martinique-1902 --publish --skip-captions
"""

import argparse
import re
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_DIR))

from n8n.run_pipeline import (
    run_audio_phase,
    run_mix_phase,
    run_post_phase,
    run_captions_phase,
    create_github_release,
    publish_to_metricool_with_upload,
    validate_word_counts,
    phase_banner,
    ts,
)


def load_episode_from_disk(ep_dir: Path) -> dict:
    slug = ep_dir.name

    storyboard = (ep_dir / "01_storyboard.md").read_text()
    dialogue = (ep_dir / "04_dialogue_script.txt").read_text()

    title_match = re.search(r"^#\s+(.+)$", storyboard, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else slug

    setting_match = re.search(r"\*\*Setting\*\*:\s*(.+)", storyboard)
    setting = setting_match.group(1).strip() if setting_match else ""

    hook_match = re.search(r"\*\*Hook\*\*:\s*(.+)", storyboard)
    hook = hook_match.group(1).strip() if hook_match else ""

    clips = []
    for m in re.finditer(
        r"### Clip (\d+)\n"
        r"- \*\*Duration\*\*: (\d+)s\n"
        r"- \*\*Type\*\*: (\w+)\n"
        r"- \*\*Character\*\*: (Yes|No)\n"
        r"- \*\*Resolution\*\*: (\w+)",
        storyboard,
    ):
        clips.append({
            "id": m.group(1).zfill(2),
            "duration": int(m.group(2)),
            "type": m.group(3),
            "has_character": m.group(4) == "Yes",
            "resolution": m.group(5),
        })

    img_dir = ep_dir / "02_image_prompts"
    vid_dir = ep_dir / "03_veo_video_prompts"
    image_prompts = []
    video_prompts = []
    for clip in clips:
        cid = clip["id"]
        img_file = img_dir / f"clip_{cid}_frame.txt"
        vid_file = vid_dir / f"clip_{cid}.txt"
        image_prompts.append(img_file.read_text().strip() if img_file.exists() else "")
        video_prompts.append(vid_file.read_text().strip() if vid_file.exists() else "")

    return {
        "episode_slug": slug,
        "title": title,
        "setting": setting,
        "hook": hook,
        "clips": clips,
        "dialogue_script": dialogue,
        "image_prompts": image_prompts,
        "video_prompts": video_prompts,
    }


def clear_stale_artifacts(ep_dir: Path):
    phase_banner("CLEARING STALE ARTIFACTS")

    dirs_to_clear = [
        ("output/audio/narration", "*.mp3"),
        ("output/mixed_clips", "*.mp4"),
        ("output/mixed", "final_*.mp4"),
    ]

    for rel_dir, pattern in dirs_to_clear:
        d = ep_dir / rel_dir
        if not d.exists():
            continue
        for f in d.glob(pattern):
            print(f"  [{ts()}] Removing: {f.relative_to(ep_dir)}")
            f.unlink()


def main():
    parser = argparse.ArgumentParser(description="Regenerate existing episode from disk files")
    parser.add_argument("slug", help="Episode slug (directory name)")
    parser.add_argument("--publish", action="store_true", help="Publish via Metricool after generation")
    parser.add_argument("--skip-captions", action="store_true", help="Skip Remotion captions phase")
    parser.add_argument("--skip-audio", action="store_true", help="Skip audio regeneration (reuse existing narration)")
    args = parser.parse_args()

    ep_dir = REPO_DIR / args.slug
    if not ep_dir.is_dir():
        print(f"ERROR: Episode directory not found: {ep_dir}")
        sys.exit(1)

    if not (ep_dir / "01_storyboard.md").exists():
        print(f"ERROR: No storyboard found at {ep_dir / '01_storyboard.md'}")
        sys.exit(1)

    episode = load_episode_from_disk(ep_dir)

    phase_banner(f"REGENERATING: {episode['title']}")
    print(f"  Slug:   {episode['episode_slug']}")
    print(f"  Clips:  {len(episode['clips'])}")
    print(f"  Publish: {'YES' if args.publish else 'no'}")

    validate_word_counts(episode)

    clear_stale_artifacts(ep_dir)

    if not args.skip_audio:
        run_audio_phase(episode, ep_dir)

    run_mix_phase(episode, ep_dir)

    final_path = run_post_phase(episode, ep_dir)

    if final_path is None:
        final_path = ep_dir / "output" / "mixed" / f"final_{args.slug}.mp4"

    if final_path.exists() and not args.skip_captions:
        final_path = run_captions_phase(final_path, ep_dir)

    phase_banner("REGENERATION COMPLETE")
    if final_path and final_path.exists():
        size_mb = final_path.stat().st_size / (1024 * 1024)
        print(f"  Final video: {final_path}")
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print(f"  WARNING: Final video not found at {final_path}")
        if args.publish:
            sys.exit(1)

    if args.publish and final_path and final_path.exists():
        asset_url = create_github_release(args.slug, episode["title"], final_path)
        publish_to_metricool_with_upload(episode, final_path, asset_url)

    phase_banner("ALL DONE")


if __name__ == "__main__":
    main()
