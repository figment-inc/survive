"""Claude-powered AI writing service for storyboards, prompts, and narration scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import anthropic

from lib.config import load_channel_file, load_settings


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        settings = load_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not found. Set it in .env.")
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _build_series_context() -> str:
    channel = load_channel_file("channel.md")
    characters = load_channel_file("characters.md")
    production = load_channel_file("production.md")
    cinematography = load_channel_file("cinematography.md")

    return (
        "You are the head writer for 'You Wouldn't Wanna Be', an AI-generated short-form video series. "
        "You MUST follow the series bible, character sheet, production standards, and cinematography rules exactly. "
        "The main character is a skeleton with translucent skin — refer to it as 'the figure' or 'the translucent character' in prompts.\n\n"
        f"--- SERIES BIBLE ---\n{channel}\n\n"
        f"--- CHARACTER SHEET ---\n{characters}\n\n"
        f"--- PRODUCTION STANDARDS ---\n{production}\n\n"
        f"--- CINEMATOGRAPHY BIBLE ---\n{cinematography}"
    )


def _call_claude(system: str, user_prompt: str, max_tokens: int = 8192) -> str:
    settings = load_settings()
    client = get_client()
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def generate_storyboard(topic: str, year: str, editor_notes: Optional[str] = None) -> str:
    """Generate a full 01_storyboard.md for a new episode."""
    system = _build_series_context()

    user_prompt = (
        f"Write a complete storyboard for a You Wouldn't Wanna Be episode about: {topic} ({year}).\n\n"
        "Follow this EXACT structure:\n"
        "1. Header with title, total clips, runtime (target 60-75 seconds), format\n"
        "2. 9-12 clips organized into 5 narrative beats (The Hook, The Immersion, The Attempt, The Catastrophe, The Cliffhanger)\n"
        "3. Clip 01 is a HOOK clip (4s, 720p) — narration starts IMMEDIATELY with a 'What happens if...' question\n"
        "4. Remaining clips are SCENE clips (mix of 4s and 8s, 1080p, skeleton character on camera)\n"
        "5. Each clip must have ALL production fields: Duration, Type, Camera, Shot motivation, Movement, "
        "Lighting setup, Composition, Depth layers, Atmosphere, Period texture, Background activity, "
        "Visual transition, Visual action, Narration\n"
        "6. Total narration must be 200-230 words\n\n"
        "SCRIPT WRITING RULES (critical for viral engagement):\n"
        "- Open with 'What happens if...' hook question over the first clip — voice on frame 1, ZERO silence\n"
        "- Second person PRESENT TENSE throughout: 'You wake up', 'You run', 'You feel'\n"
        "- Short punchy sentences: average 5-8 words, with 3-4 word punches for impact\n"
        "- AGENCY AND FAILURE LOOPS: the viewer tries things and fails every 10-15 seconds\n"
        "  Example: 'You warn the officers. They laugh.' / 'You run for the gate. It is already jammed.'\n"
        "- One philosophical beat per episode: a moment of insight amid chaos\n"
        "- End on a CLIFFHANGER — an open, haunting image, never a clean resolution\n"
        "- Weave in recognizable anchors the viewer already knows (famous people, artifacts, pop culture)\n"
        "- The skeleton character NEVER speaks — all audio is narrator voiceover\n"
        "- Every episode MUST end terribly for the skeleton\n"
        "- All historical facts must be accurate — real dates, real numbers, real consequences\n"
        "- Dark humor through understatement, not mockery of real victims\n"
        "- Use 'the figure' or 'the translucent character' in prompt descriptions\n"
        "- All camera angles must come from the cinematography bible\n"
        "- All lighting setups must be named from the playbook\n"
        "- Every frame needs three depth layers\n"
        "- Air is never perfectly clear — always specify atmosphere\n"
        "- Mix 4s and 8s clips for visual rhythm — 4s for quick beats, 8s for continuous motion\n\n"
    )

    if editor_notes:
        user_prompt += f"Additional direction from the editor:\n{editor_notes}\n\n"

    user_prompt += "Output ONLY the storyboard markdown. No preamble, no commentary."

    return _call_claude(system, user_prompt, max_tokens=16384)


def generate_image_prompt(
    storyboard_excerpt: str,
    clip_id: str,
    episode_slug: str,
    editor_notes: Optional[str] = None,
) -> str:
    """Generate a NanoBanana Pro image prompt for a single clip."""
    system = _build_series_context()
    template = load_channel_file("templates/image_prompt.txt")

    user_prompt = (
        f"Write an image prompt for clip {clip_id} of episode '{episode_slug}'.\n\n"
        f"Here is the storyboard excerpt for this clip:\n\n{storyboard_excerpt}\n\n"
        f"Here is the image prompt template — fill in ALL placeholders with rich, specific detail:\n\n{template}\n\n"
        "RULES:\n"
        "- Output ONLY the final image prompt text, no template markers or placeholders\n"
        "- Include ALL required elements: format line, depth layers, atmosphere, period texture, "
        "background activity, character description (if scene clip), camera/composition, lighting\n"
        "- End with: NO text, NO watermarks, NO logos, NO captions, NO overlays.\n"
        "- Use 'the figure' or 'the translucent character' — NEVER 'skeleton' in the prompt\n"
        "- The figure has NO clothing, NO hair — the translucent body IS the visual identity\n"
        "- Use specific, concrete details — not generic descriptions\n"
    )

    if editor_notes:
        user_prompt += f"\nAdditional direction from the editor:\n{editor_notes}\n"

    user_prompt += "\nOutput ONLY the image prompt text. No preamble, no commentary."

    return _call_claude(system, user_prompt, max_tokens=4096)


def generate_video_prompt(
    storyboard_excerpt: str,
    clip_id: str,
    episode_slug: str,
    image_prompt: Optional[str] = None,
    prev_video_prompt: Optional[str] = None,
    prev_storyboard_excerpt: Optional[str] = None,
    clip_index: int = 1,
    total_clips: int = 1,
    chain_mode: bool = False,
    editor_notes: Optional[str] = None,
) -> str:
    """Generate a Veo 3.1 video prompt for a single clip.

    When chain_mode=True, adds extension-chain continuity directives that tell Veo
    to maintain seamless visual flow from the previous segment.
    """
    system = _build_series_context()
    template = load_channel_file("templates/video_prompt.txt")

    user_prompt = (
        f"Write a Veo 3.1 video prompt for clip {clip_id} of episode '{episode_slug}' "
        f"(clip {clip_index}/{total_clips}).\n\n"
        f"Storyboard excerpt:\n\n{storyboard_excerpt}\n\n"
        f"Video prompt template — fill in ALL placeholders:\n\n{template}\n\n"
    )

    if image_prompt:
        user_prompt += f"The image prompt for this clip (for visual consistency):\n\n{image_prompt}\n\n"

    if prev_video_prompt:
        user_prompt += f"The previous clip's video prompt (for transition continuity):\n\n{prev_video_prompt}\n\n"

    if prev_storyboard_excerpt:
        user_prompt += f"Previous clip's storyboard (for action continuity):\n\n{prev_storyboard_excerpt}\n\n"

    user_prompt += (
        "RULES:\n"
        "- Output ONLY the final video prompt text\n"
        "- Include ALL required elements from the template\n"
        "- ALWAYS include 'No dialogue. No speech.' directive\n"
        "- ALWAYS end with Audio direction (SFX + Ambience only — no dialogue, no music)\n"
        "- Use 'the figure' or 'the translucent character' — NEVER 'skeleton'\n"
        "- The figure reacts through PHYSICAL GESTURES only — panicking, flinching, running, crouching\n"
        "- Match the visual style and detail level of the image prompt\n"
        "- Veo generates native ambient audio — describe the sound environment\n"
    )

    if chain_mode and clip_index > 1:
        user_prompt += (
            "\nEXTENSION CHAIN CONTINUITY (critical — this clip extends the previous one):\n"
            "- This clip is generated by EXTENDING the previous clip's video. Veo will use the last "
            "frames of the previous clip as seed frames, so visual continuity is built-in.\n"
            "- Start your prompt by describing the scene AS IF continuing seamlessly from the previous clip. "
            "Do NOT re-establish the setting from scratch.\n"
            "- Add this continuity directive near the top of your prompt: "
            "'Continuity: continue seamlessly from the previous clip. Maintain the same character appearance, "
            "wardrobe, lighting, and environmental composition.'\n"
            "- Add a 'Character lock' line: 'Character lock: translucent figure with visible skeleton, "
            "pale orb eyes, no hair, no clothing — same appearance throughout.'\n"
            "- Reference the previous clip's ending action to ensure the transition flows naturally.\n"
            "- Maintain consistent atmosphere, color grade, and environmental details.\n"
        )

    if editor_notes:
        user_prompt += f"\nAdditional direction from the editor:\n{editor_notes}\n"

    user_prompt += "\nOutput ONLY the video prompt text. No preamble, no commentary."

    return _call_claude(system, user_prompt, max_tokens=4096)


def generate_narration_script(storyboard_raw: str, editor_notes: Optional[str] = None) -> str:
    """Generate the narrator voiceover script from the full storyboard."""
    system = _build_series_context()

    user_prompt = (
        "Extract ALL narration from the following storyboard into a clean narration script.\n\n"
        f"--- STORYBOARD ---\n{storyboard_raw}\n\n"
        "FORMAT:\n"
        "- Organize by narrative beat (The Hook, The Immersion, The Attempt, The Catastrophe, The Cliffhanger)\n"
        "- For each clip: show clip number, beat label, then narrator text in quotes\n"
        "- EVERY clip has narration — no silent clips\n"
        "- Keep the exact narration from the storyboard — do NOT rewrite lines\n"
        "- Second person PRESENT TENSE throughout: 'you wake up', 'you run', 'you feel'\n"
        "- Total script should be 200-230 words\n"
        "- Short sentences: average 5-8 words, 3-4 word punches for impact\n"
    )

    if editor_notes:
        user_prompt += f"\nAdditional direction:\n{editor_notes}\n"

    user_prompt += "\nOutput ONLY the narration script. No preamble."

    return _call_claude(system, user_prompt, max_tokens=4096)


def generate_all_prompts(episode_dir: Path, chain_mode: bool = False, progress_callback=None) -> dict:
    """Batch-generate all image prompts, video prompts, and narration for an episode.

    When chain_mode=True, video prompts include extension-chain continuity directives
    and previous storyboard context for seamless clip transitions.
    """
    storyboard_path = episode_dir / "01_storyboard.md"
    if not storyboard_path.exists():
        raise RuntimeError(f"No storyboard found at {storyboard_path}")

    storyboard_raw = storyboard_path.read_text()
    episode_slug = episode_dir.name

    clips = _parse_storyboard_clips(storyboard_raw)
    if not clips:
        raise RuntimeError("No clips found in storyboard")

    img_dir = episode_dir / "02_image_prompts"
    vid_dir = episode_dir / "03_veo_video_prompts"
    img_dir.mkdir(parents=True, exist_ok=True)
    vid_dir.mkdir(parents=True, exist_ok=True)

    prev_video_prompt = None
    prev_excerpt = None
    generated = {"image_prompts": 0, "video_prompts": 0, "narration": False}

    for i, clip in enumerate(clips):
        clip_id = clip["id"]
        excerpt = clip["storyboard_excerpt"]

        if progress_callback:
            progress_callback(f"Writing image prompt for clip {clip_id} ({i+1}/{len(clips)})")

        img_prompt = generate_image_prompt(excerpt, clip_id, episode_slug)
        img_path = img_dir / f"clip_{clip_id}_frame.txt"
        img_path.write_text(img_prompt.strip() + "\n")
        generated["image_prompts"] += 1

        if progress_callback:
            progress_callback(f"Writing video prompt for clip {clip_id} ({i+1}/{len(clips)})")

        vid_prompt = generate_video_prompt(
            excerpt, clip_id, episode_slug,
            image_prompt=img_prompt,
            prev_video_prompt=prev_video_prompt,
            prev_storyboard_excerpt=prev_excerpt,
            clip_index=i + 1,
            total_clips=len(clips),
            chain_mode=chain_mode,
        )
        vid_path = vid_dir / f"clip_{clip_id}.txt"
        vid_path.write_text(vid_prompt.strip() + "\n")
        generated["video_prompts"] += 1
        prev_video_prompt = vid_prompt
        prev_excerpt = excerpt

    if progress_callback:
        progress_callback("Writing narration script...")

    narration = generate_narration_script(storyboard_raw)
    narr_path = episode_dir / "04_narration_script.txt"
    narr_path.write_text(narration.strip() + "\n")
    generated["narration"] = True

    return generated


def _parse_storyboard_clips(storyboard_raw: str) -> list[dict]:
    """Parse clip sections from a storyboard markdown file."""
    import re

    clips: list[dict] = []
    clip_pattern = re.compile(r"###?\s*Clip\s+(\d+)", re.IGNORECASE)
    lines = storyboard_raw.split("\n")
    current_clip_id = None
    current_lines: list[str] = []

    for line in lines:
        match = clip_pattern.match(line)
        if match:
            if current_clip_id is not None:
                clips.append({
                    "id": current_clip_id,
                    "storyboard_excerpt": "\n".join(current_lines),
                })
            current_clip_id = match.group(1).zfill(2)
            current_lines = [line]
        elif current_clip_id is not None:
            current_lines.append(line)

    if current_clip_id is not None:
        clips.append({
            "id": current_clip_id,
            "storyboard_excerpt": "\n".join(current_lines),
        })

    return clips
