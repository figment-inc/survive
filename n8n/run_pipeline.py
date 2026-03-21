#!/usr/bin/env python3
"""
You Wouldn't Wanna Be — Automated Episode Pipeline

End-to-end from autonomous topic selection to published YouTube Short + Instagram Reel.
Family Guy animation style with image-based slideshow pipeline (default) or Veo video pipeline (--use-veo).

Default pipeline (image-based slideshow):
  0. Topic generation (Claude — picks history's worst moments, avoids duplicates)
  1. Episode content generation (Claude — per-sentence image prompts, dialogue script)
  1b. Write prompts to disk
  2. Image generation (NanoBanana Pro — 1-2 images per sentence, skeleton Family Guy style)
  2b. Audio generation (ElevenLabs — Dan British documentary narrator voice + cinematic underscore music)
  3. Slideshow assembly (ffmpeg — Ken Burns zoom/pan effects with crossfade transitions)
  4. Final mix (ffmpeg — overlay narration + music onto slideshow)
  4b. Remotion karaoke captions
  5. Publish (GitHub Release upload + Metricool API → IG Reel + YT Short + TikTok)

Legacy Veo pipeline (--use-veo):
  0-2b. Same as above (but uses per-clip image/video prompts)
  3. Video generation (Veo 3.1 — silent clips with SFX/ambience only, NO speech)
  3b. Per-clip audio mixing (ffmpeg)
  4. Stitch + LUFS normalize (ffmpeg)
  5. Publish

Usage:
  python n8n/run_pipeline.py                          # autonomous topic + image-based
  python n8n/run_pipeline.py "The Great Fire of London, 1666"  # manual topic
  python n8n/run_pipeline.py --publish                # autonomous + publish
  python n8n/run_pipeline.py --use-veo                # use Veo video generation
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
CHANNEL_DIR = REPO_DIR / ".channel"
SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "system-prompts" / "generate-episode-legacy.txt"
SCRIPT_PROMPT_PATH = Path(__file__).resolve().parent / "system-prompts" / "generate-script.txt"
PROMPTS_PROMPT_PATH = Path(__file__).resolve().parent / "system-prompts" / "generate-prompts.txt"
WRITER_PROMPT_PATH = Path(__file__).resolve().parent / "system-prompts" / "writer.txt"
CRITIC_PROMPT_PATH = Path(__file__).resolve().parent / "system-prompts" / "critic.txt"
REWRITER_PROMPT_PATH = Path(__file__).resolve().parent / "system-prompts" / "rewriter.txt"
SOURCES_PROMPT_PATH = Path(__file__).resolve().parent / "system-prompts" / "sources.txt"

sys.path.insert(0, str(REPO_DIR))

from lib.sources import format_sources_comment


def ts():
    return datetime.now().strftime("%H:%M:%S")


def phase_banner(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def load_env_key(name):
    if os.environ.get(name):
        return os.environ[name]
    env_path = REPO_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def _create_bedrock_client():
    from anthropic import AnthropicBedrock
    return AnthropicBedrock(
        aws_access_key=load_env_key("AWS_ACCESS_KEY_ID_BEDROCK"),
        aws_secret_key=load_env_key("AWS_SECRET_ACCESS_KEY_BEDROCK"),
        aws_region=load_env_key("AWS_BEDROCK_REGION") or "us-east-1",
    )


def get_existing_slugs():
    """Return set of episode slugs already in the repo root."""
    return {
        d.name for d in REPO_DIR.iterdir()
        if d.is_dir()
        and not d.name.startswith((".", "_"))
        and d.name not in ("lib", "n8n", "output", "__pycache__")
        and (d / "01_storyboard.md").exists()
    }


# ── Phase 0: Autonomous topic generation ──


def generate_topic():
    phase_banner("PHASE 0: TOPIC GENERATION (Claude)")

    client = _create_bedrock_client()

    existing = sorted(get_existing_slugs())
    existing_list = "\n".join(f"- {s}" for s in existing) if existing else "(none yet)"

    system = (
        "You generate episode topics for 'You Wouldn't Wanna Be', a dark-comedy short-form "
        "video series where a hapless skeleton gets teleported into history's worst moments.\n\n"
        "Pick ONE specific historical disaster or catastrophe. Prioritize events that:\n"
        "- Most people have HEARD OF but don't know the full story\n"
        "- Are taught in schools or referenced in popular culture (movies, TV, books)\n"
        "- Have high search interest on YouTube and TikTok\n"
        "- Have a specific, dramatic moment that can anchor a 35-second video\n\n"
        "Good examples: the Titanic sinking, Pompeii, Chernobyl, the Black Death, "
        "the Hindenburg, the Great Fire of London, the sinking of the Lusitania, "
        "the Triangle Shirtwaist fire, the Challenger disaster, Hiroshima, the San "
        "Francisco earthquake, the Halifax explosion, the Donner Party, the "
        "Spanish Flu, the Dust Bowl, the eruption of Mount St. Helens.\n\n"
        "The event must be:\n"
        "- A real, well-documented historical event with a specific date/year\n"
        "- Visually spectacular and cinematically compelling\n"
        "- NOT primarily about explicit torture or sexual content\n"
        "- Safe for AI image/video generation (avoid content filter triggers)\n"
        "- Different from all previously produced episodes listed below\n\n"
        "Return ONLY the topic as a single line, like: "
        "'The eruption of Mount Vesuvius, Pompeii, 79 AD'\n\n"
        f"## ALREADY PRODUCED (do NOT repeat):\n{existing_list}"
    )

    model = load_env_key("ANTHROPIC_MODEL") or "us.anthropic.claude-opus-4-6-v1"

    print(f"  [{ts()}] Asking Claude for a new topic...")
    print(f"  [{ts()}] Existing episodes: {len(existing)}")

    response = client.messages.create(
        model=model,
        max_tokens=200,
        temperature=1.0,
        system=system,
        messages=[{"role": "user", "content": "Pick a new episode topic."}],
    )

    topic = response.content[0].text.strip().strip('"').strip("'")
    print(f"  [{ts()}] Selected topic: {topic}")
    return topic


# ── Phase 1: Generate episode content ──


def load_example_prompts():
    """Load working image + video prompts as few-shot examples for Claude.

    Loads two clips per episode (hook + catastrophe) to demonstrate both calm
    and high-intensity beats in flat 2D animation style.
    """
    examples = ""
    clip_pairs = [("01", "The Hook — calm opening"), ("06", "Catastrophe — peak intensity")]

    for ep_slug in ["hiroshima-1945", "wall-street-crash-1929", "tunguska-event-1908"]:
        ep_dir = REPO_DIR / ep_slug
        found_any = False
        for clip_id, beat_label in clip_pairs:
            img_example = ep_dir / "02_image_prompts" / f"clip_{clip_id}_frame.txt"
            vid_example = ep_dir / "03_veo_video_prompts" / f"clip_{clip_id}.txt"
            if img_example.exists():
                examples += f"\n\n--- EXAMPLE IMAGE PROMPT (clip {clip_id} — {beat_label}) ---\n"
                examples += img_example.read_text().strip()
                found_any = True
            if vid_example.exists():
                examples += f"\n\n--- EXAMPLE VIDEO PROMPT (clip {clip_id} — {beat_label}) ---\n"
                examples += vid_example.read_text().strip()
                found_any = True
        if found_any:
            break
    return examples


def generate_episode_content(topic):
    phase_banner("PHASE 1: GENERATE EPISODE CONTENT (Claude)")

    client = _create_bedrock_client()
    system_prompt = SYSTEM_PROMPT_PATH.read_text()

    examples = load_example_prompts()
    if examples:
        system_prompt += "\n\n## FEW-SHOT EXAMPLES FROM WORKING EPISODES\n"
        system_prompt += (
            "Below are examples from two beats of a working episode — a calm hook "
            "and a high-intensity catastrophe clip. Your prompts MUST match this level "
            "of detail, length, and flat 2D animation style. "
            "Short/generic prompts will be blocked by safety filters or produce poor results. "
            "Every image prompt must be 15-25 lines with explicit scene composition, "
            "character blocking, foreground/midground/background layers, "
            "atmospheric details, period textures, and exclusion lines. "
            "Every video prompt must be 25-35 lines with camera behavior, depth layers, "
            "ambient audio direction, and physical performance descriptions. "
            "ALL prompts must use flat 2D animation vocabulary — never photorealistic terms."
        )
        system_prompt += examples

    model = load_env_key("ANTHROPIC_MODEL") or "us.anthropic.claude-opus-4-6-v1"

    print(f"  [{ts()}] Sending topic to Claude: {topic}")
    print(f"  [{ts()}] Model: {model}")

    max_retries = 2
    api_max_retries = 5
    for attempt in range(max_retries + 1):
        collected = []
        for api_attempt in range(api_max_retries):
            try:
                with client.messages.stream(
                    model=model,
                    max_tokens=32000,
                    temperature=1.0,
                    system=system_prompt,
                    messages=[{"role": "user", "content": topic}],
                ) as stream:
                    for text in stream.text_stream:
                        collected.append(text)
                response = stream.get_final_message()
                break
            except Exception as e:
                import anthropic as _anth
                if isinstance(e, (_anth.APIStatusError, _anth.APIConnectionError)):
                    wait = 30 * (api_attempt + 1)
                    print(f"  [{ts()}] API error ({e}). Retry {api_attempt+1}/{api_max_retries} in {wait}s...")
                    import time; time.sleep(wait)
                    collected = []
                else:
                    raise
        else:
            raise RuntimeError("Claude API unavailable after retries — try again later")

        stop_reason = response.stop_reason
        raw = "".join(collected).strip()

        if stop_reason == "max_tokens":
            print(f"  [{ts()}] WARNING: Response truncated (max_tokens). "
                  f"Attempt {attempt + 1}/{max_retries + 1}.")
            if attempt < max_retries:
                print(f"  [{ts()}] Retrying with shorter prompt expectations...")
                continue
            print(f"  [{ts()}] Attempting to salvage truncated JSON...")

        break

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()

    try:
        episode = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [{ts()}] JSON parse error: {e}")
        print(f"  [{ts()}] Attempting truncated JSON repair...")
        episode = _repair_truncated_json(raw)

    print(f"  [{ts()}] Generated episode: {episode['title']}")
    print(f"  [{ts()}] Slug: {episode['episode_slug']}")
    print(f"  [{ts()}] Image prompts: {len(episode['image_prompts'])}")
    print(f"  [{ts()}] Video prompts: {len(episode['video_prompts'])}")
    return episode


# ── Phase 1 (two-phase): Script-only generation + prompt generation ──


def _call_claude_streaming(client, model, system_prompt, user_message, max_tokens=32000, temperature=1.0):
    """Call Claude with streaming and API-level retries. Returns raw text."""
    api_max_retries = 5
    collected = []
    for api_attempt in range(api_max_retries):
        try:
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    collected.append(text)
            response = stream.get_final_message()
            return "".join(collected).strip(), response.stop_reason
        except Exception as e:
            import anthropic as _anth
            if isinstance(e, (_anth.APIStatusError, _anth.APIConnectionError)):
                wait = 30 * (api_attempt + 1)
                print(f"  [{ts()}] API error ({e}). Retry {api_attempt+1}/{api_max_retries} in {wait}s...")
                import time; time.sleep(wait)
                collected = []
            else:
                raise
    raise RuntimeError("Claude API unavailable after retries — try again later")


def _count_script_words(script_text):
    """Count narration words in a script, ignoring clip headers and annotations."""
    import re
    words = []
    for line in script_text.strip().splitlines():
        line = line.strip()
        if line.startswith("##") or not line:
            continue
        narr_match = re.match(r"NARRATOR:\s*(.+)", line)
        if narr_match:
            words.extend(narr_match.group(1).split())
    return len(words)


def generate_script(topic):
    """Phase 1a: Generate script-only narration using the focused script prompt."""
    phase_banner("PHASE 1a: GENERATE SCRIPT (Claude — script-only)")

    client = _create_bedrock_client()
    system_prompt = SCRIPT_PROMPT_PATH.read_text()
    model = load_env_key("ANTHROPIC_MODEL") or "us.anthropic.claude-opus-4-6-v1"

    print(f"  [{ts()}] Generating script for: {topic}")
    print(f"  [{ts()}] Model: {model}")

    raw, stop_reason = _call_claude_streaming(client, model, system_prompt, topic, max_tokens=2000)

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()

    word_count = _count_script_words(raw)
    print(f"  [{ts()}] Script complete: {word_count} words")

    return raw


def _strip_code_fences(text):
    """Remove leading/trailing markdown code fences from LLM output."""
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def generate_script_v2(topic):
    """Phase 1a: Writer-Critic-Rewriter pipeline for script generation.
    
    Returns (final_script, artifacts_dict) where artifacts_dict has
    'draft' and 'critique' keys for saving to disk later.
    """
    phase_banner("PHASE 1a: GENERATE SCRIPT (Writer → Critic → Rewriter)")

    client = _create_bedrock_client()
    model = load_env_key("ANTHROPIC_MODEL") or "us.anthropic.claude-opus-4-6-v1"

    print(f"  [{ts()}] Model: {model}")
    print(f"  [{ts()}] Topic: {topic}")

    # Step 1: Writer drafts
    print(f"\n  [{ts()}] Step 1/3: Writer drafting...")
    writer_prompt = WRITER_PROMPT_PATH.read_text()
    draft, _ = _call_claude_streaming(client, model, writer_prompt, topic, max_tokens=2000)
    draft = _strip_code_fences(draft)
    draft_words = _count_script_words(draft)
    print(f"  [{ts()}] Draft complete ({draft_words} words)")

    # Step 2: Critic scores and tears apart
    print(f"\n  [{ts()}] Step 2/3: Critic reviewing...")
    critic_prompt = CRITIC_PROMPT_PATH.read_text()
    critique, _ = _call_claude_streaming(client, model, critic_prompt, draft, max_tokens=4000)
    critique = critique.strip()
    print(f"  [{ts()}] Critique complete")

    import re
    avg_match = re.search(r"\*\*AVERAGE\*\*.*?\*\*(\d+\.?\d*)/10\*\*", critique)
    avg_score = float(avg_match.group(1)) if avg_match else 0.0
    verdict_match = re.search(r"VERDICT:\s*(PUBLISH|REWRITE REQUIRED)", critique)
    verdict = verdict_match.group(1) if verdict_match else "REWRITE REQUIRED"
    print(f"  [{ts()}] Critic verdict: {verdict} (avg {avg_score}/10)")

    if verdict == "PUBLISH" and avg_score >= 7.0:
        print(f"  [{ts()}] Draft passed critique — using as final")
        final = draft
    else:
        # Step 3: Rewriter fixes based on critique
        print(f"\n  [{ts()}] Step 3/3: Rewriter revising...")
        rewriter_prompt = REWRITER_PROMPT_PATH.read_text()
        rewriter_input = f"## ORIGINAL DRAFT\n\n{draft}\n\n## CRITIQUE\n\n{critique}"
        final, _ = _call_claude_streaming(
            client, model, rewriter_prompt, rewriter_input, max_tokens=2000, temperature=0.7
        )
        final = _strip_code_fences(final)
        final_words = _count_script_words(final)
        print(f"  [{ts()}] Rewrite complete ({final_words} words)")

    word_count = _count_script_words(final)

    if word_count > 150:
        print(f"\n  [{ts()}] WARNING: Script at {word_count} words — exceeds Shorts ceiling "
              f"(~150 words / ~58s). May need manual trimming.")

    print(f"\n  [{ts()}] Final script: {word_count} words")
    artifacts = {"draft": draft, "critique": critique}
    return final, artifacts


def generate_sources(topic, script):
    """Extract key factual claims and their historical sources from a finished script.

    Returns a list of {fact, source} dicts, or an empty list on failure.
    """
    phase_banner("PHASE 1a+: EXTRACT SOURCES (Claude)")

    client = _create_bedrock_client()
    system_prompt = SOURCES_PROMPT_PATH.read_text()
    model = load_env_key("ANTHROPIC_MODEL") or "us.anthropic.claude-opus-4-6-v1"

    user_message = f"TOPIC: {topic}\n\nSCRIPT:\n{script}"
    print(f"  [{ts()}] Extracting sources for: {topic}")

    raw, _ = _call_claude_streaming(client, model, system_prompt, user_message, max_tokens=2000, temperature=0.3)
    raw = _strip_code_fences(raw)

    try:
        sources = json.loads(raw)
        if not isinstance(sources, list):
            print(f"  [{ts()}] WARNING: Sources response is not a list, wrapping")
            sources = [sources] if isinstance(sources, dict) else []
    except json.JSONDecodeError as e:
        print(f"  [{ts()}] WARNING: Failed to parse sources JSON: {e}")
        print(f"  [{ts()}] Raw response: {raw[:300]}")
        sources = []

    print(f"  [{ts()}] Extracted {len(sources)} source entries")
    return sources


def generate_episode_from_script(topic, script):
    """Phase 1b: Generate full episode JSON (image/video prompts + metadata) from a finished script."""
    phase_banner("PHASE 1b: GENERATE PROMPTS FROM SCRIPT (Claude)")

    client = _create_bedrock_client()
    system_prompt = PROMPTS_PROMPT_PATH.read_text()

    examples = load_example_prompts()
    if examples:
        system_prompt += "\n\n## FEW-SHOT EXAMPLES FROM WORKING EPISODES\n"
        system_prompt += (
            "Below are examples from two beats of a working episode — a calm hook "
            "and a high-intensity catastrophe clip. Your prompts MUST match this level "
            "of detail, length, and flat 2D animation style. "
            "ALL prompts must use flat 2D animation vocabulary — never photorealistic terms."
        )
        system_prompt += examples

    model = load_env_key("ANTHROPIC_MODEL") or "us.anthropic.claude-opus-4-6-v1"
    user_message = f"TOPIC: {topic}\n\nSCRIPT:\n{script}"

    print(f"  [{ts()}] Generating prompts for: {topic}")
    print(f"  [{ts()}] Model: {model}")

    raw, stop_reason = _call_claude_streaming(client, model, system_prompt, user_message)

    if stop_reason == "max_tokens":
        print(f"  [{ts()}] WARNING: Response truncated — attempting repair")

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()

    try:
        episode = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [{ts()}] JSON parse error: {e}")
        print(f"  [{ts()}] Attempting truncated JSON repair...")
        episode = _repair_truncated_json(raw)

    print(f"  [{ts()}] Generated episode: {episode['title']}")
    print(f"  [{ts()}] Slug: {episode['episode_slug']}")

    if "sentence_images" in episode:
        total_imgs = sum(len(si.get("image_prompts", [])) for si in episode["sentence_images"])
        print(f"  [{ts()}] Sentences: {len(episode['sentence_images'])}, total images: {total_imgs}")
    elif "image_prompts" in episode:
        print(f"  [{ts()}] Image prompts: {len(episode['image_prompts'])}")
        if "video_prompts" in episode:
            print(f"  [{ts()}] Video prompts: {len(episode['video_prompts'])}")

    return episode


def _repair_truncated_json(raw):
    """Attempt to repair JSON truncated mid-generation by closing open structures."""
    import re

    if raw.endswith(","):
        raw = raw[:-1]

    open_braces = raw.count("{") - raw.count("}")
    open_brackets = raw.count("[") - raw.count("]")
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string

    if in_string:
        raw += '"'

    if raw.rstrip().endswith(","):
        raw = raw.rstrip()[:-1]

    raw += "]" * max(0, open_brackets)
    raw += "}" * max(0, open_braces)

    return json.loads(raw)


# ── Phase 1b: Write prompts to disk ──


def write_episode_files(episode):
    slug = episode["episode_slug"]
    ep_dir = REPO_DIR / slug
    img_dir = ep_dir / "02_image_prompts"
    out_dirs = [
        ep_dir / "output" / d
        for d in ["images", "audio/narration", "slideshow", "mixed"]
    ]

    dirs_to_create = [img_dir] + out_dirs
    if "video_prompts" in episode:
        vid_dir = ep_dir / "03_veo_video_prompts"
        dirs_to_create.append(vid_dir)

    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    if "sentence_images" in episode:
        for si in episode["sentence_images"]:
            s_idx = si["sentence_index"]
            for p_idx, prompt in enumerate(si.get("image_prompts", [])):
                fname = f"sentence_{s_idx:02d}_img_{p_idx + 1:02d}.txt"
                (img_dir / fname).write_text(prompt)
    elif "image_prompts" in episode:
        for i, prompt in enumerate(episode["image_prompts"]):
            clip_id = f"{i + 1:02d}"
            (img_dir / f"clip_{clip_id}_frame.txt").write_text(prompt)

    if "video_prompts" in episode:
        vid_dir = ep_dir / "03_veo_video_prompts"
        for i, prompt in enumerate(episode["video_prompts"]):
            clip_id = f"{i + 1:02d}"
            (vid_dir / f"clip_{clip_id}.txt").write_text(prompt)

    if episode.get("dialogue_script"):
        (ep_dir / "04_dialogue_script.txt").write_text(episode["dialogue_script"])

    storyboard = (
        f"# {episode['title']}\n\n"
        f"**Slug**: `{slug}`\n"
        f"**Setting**: {episode.get('setting', '')}\n"
        f"**Hook**: {episode.get('hook', '')}\n"
    )

    style_desc = episode.get("style_description", "")
    if style_desc:
        storyboard += f"\n**Style Description**: {style_desc}\n"

    storyboard += f"\n## Clips\n\n"
    if episode.get("sentence_images"):
        storyboard += f"**Mode**: Image-based slideshow (Ken Burns)\n"
        storyboard += f"**Sentences**: {len(episode['sentence_images'])}\n"
        total_imgs = sum(len(si.get('image_prompts', [])) for si in episode['sentence_images'])
        storyboard += f"**Total images**: {total_imgs}\n\n"
        for si in episode["sentence_images"]:
            s_idx = si["sentence_index"]
            storyboard += (
                f"### Sentence {s_idx}\n"
                f"- **Text**: {si.get('narration_text', '')[:80]}...\n"
                f"- **Images**: {len(si.get('image_prompts', []))}\n"
                f"- **Character**: {'Yes' if si.get('has_character', True) else 'No'}\n\n"
            )
    else:
        for clip in episode.get("clips", []):
            storyboard += (
                f"### Clip {clip['id']}\n"
                f"- **Duration**: {clip['duration']}s\n"
                f"- **Type**: {clip['type']}\n"
                f"- **Character**: {'Yes' if clip.get('has_character') else 'No'}\n"
                f"- **Resolution**: {clip.get('resolution', '1080p')}\n\n"
            )
    (ep_dir / "01_storyboard.md").write_text(storyboard)

    print(f"  [{ts()}] Written episode files to: {ep_dir}")
    return ep_dir, slug


def _load_style_description_from_storyboard(ep_dir: Path) -> str | None:
    """Read back style_description from a persisted storyboard file."""
    sb_path = ep_dir / "01_storyboard.md"
    if not sb_path.exists():
        return None
    import re
    for line in sb_path.read_text().splitlines():
        m = re.match(r"\*\*Style Description\*\*:\s*(.+)", line)
        if m:
            return m.group(1).strip()
    return None


# ── Phase 2: Image generation (NanoBanana Pro) ──


def run_images_phase(episode, ep_dir):
    phase_banner("PHASE 2: IMAGE GENERATION (NanoBanana Pro)")

    from lib.nanobanana import generate_image

    api_key = load_env_key("NANOBANANA_API_KEY") or load_env_key("GEMINI_API_KEY")
    model = load_env_key("NANOBANANA_MODEL") or "gemini-3-pro-image-preview"

    if not api_key:
        print(f"  [{ts()}] ERROR: NANOBANANA_API_KEY / GEMINI_API_KEY not found.")
        return False

    ref_dir = CHANNEL_DIR / "reference_images"
    ref_paths = []
    for name in ["skeleton_front_neutral.jpg", "skeleton_front_neutral.png"]:
        path = ref_dir / name
        if path.exists():
            ref_paths.append(path)
            print(f"  [{ts()}] Loaded reference: {name}")
            break

    style_ref_path = ref_dir / "style_reference.png"
    if style_ref_path.exists():
        print(f"  [{ts()}] Loaded global style reference: {style_ref_path.name}")
    else:
        style_ref_path = None
        print(f"  [{ts()}] WARNING: Global style reference not found — style anchoring weakened")

    images_dir = ep_dir / "output" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    episode_style = episode.get("style_description")
    if episode_style:
        print(f"  [{ts()}] Episode style: {episode_style[:80]}...")

    style_anchor_path = None

    if "sentence_images" in episode:
        return _run_images_sentence_mode(
            episode, ep_dir, api_key, model, ref_paths,
            style_ref_path, images_dir, episode_style,
        )

    clips = episode.get("clips", [])
    for i, prompt in enumerate(episode.get("image_prompts", [])):
        clip_id = f"{i + 1:02d}"
        output_path = images_dir / f"clip_{clip_id}_frame.png"

        if output_path.exists():
            print(f"  [{ts()}] Skipping (exists): {output_path.name}")
            if i == 0 and style_anchor_path is None:
                style_anchor_path = output_path
                print(f"  [{ts()}] Using existing clip 01 as style anchor")
            continue

        has_character = clips[i].get("has_character", True) if i < len(clips) else True
        print(f"\n  --- Clip {clip_id} ---")
        generate_image(
            api_key=api_key,
            model=model,
            prompt=prompt,
            output_path=output_path,
            reference_paths=ref_paths if has_character else None,
            has_character=has_character,
            style_anchor_path=style_anchor_path if i > 0 else None,
            episode_style=episode_style,
            style_ref_path=style_ref_path,
        )

        if i == 0 and output_path.exists():
            style_anchor_path = output_path
            print(f"  [{ts()}] Clip 01 set as style anchor for remaining images")

    print(f"  [{ts()}] Images phase complete.")
    return True


def _run_images_sentence_mode(
    episode, ep_dir, api_key, model, ref_paths,
    style_ref_path, images_dir, episode_style,
):
    """Generate images from sentence_images[] — 1-2 images per sentence."""
    from lib.nanobanana import generate_image

    style_anchor_path = None
    img_counter = 0

    for si in episode["sentence_images"]:
        s_idx = si["sentence_index"]
        has_character = si.get("has_character", True)

        for p_idx, prompt in enumerate(si.get("image_prompts", [])):
            img_counter += 1
            fname = f"sentence_{s_idx:02d}_img_{p_idx + 1:02d}.png"
            output_path = images_dir / fname

            if output_path.exists():
                print(f"  [{ts()}] Skipping (exists): {output_path.name}")
                if style_anchor_path is None:
                    style_anchor_path = output_path
                    print(f"  [{ts()}] Using existing image as style anchor")
                continue

            print(f"\n  --- Sentence {s_idx}, Image {p_idx + 1} ---")
            generate_image(
                api_key=api_key,
                model=model,
                prompt=prompt,
                output_path=output_path,
                reference_paths=ref_paths if has_character else None,
                has_character=has_character,
                style_anchor_path=style_anchor_path if style_anchor_path else None,
                episode_style=episode_style,
                style_ref_path=style_ref_path,
            )

            if output_path.exists() and style_anchor_path is None:
                style_anchor_path = output_path
                print(f"  [{ts()}] First image set as style anchor for remaining")

    print(f"  [{ts()}] Images phase complete ({img_counter} images generated).")
    return True


# ── Phase 2b: Audio generation (ElevenLabs narration + music) ──


MUSIC_PROMPT = (
    "National Geographic documentary orchestral underscore. Sweeping strings, "
    "warm French horns, gentle piano, and subtle timpani. Reverent and majestic. "
    "Slow building wonder and tension. Evokes vast landscapes and ancient forces. "
    "No vocals. No sudden jumps. No electronic elements."
)


def _parse_narration_lines(episode):
    """Extract per-clip narration text from the dialogue_script field.

    Supports both old-style isolated per-clip scripts and new continuous
    prose format where sentences may span clip boundaries.
    """
    import re

    script = episode.get("dialogue_script", "")
    clips = episode.get("clips", [])
    lines: dict[str, str] = {}
    current_clip = None

    for line in script.splitlines():
        clip_match = re.match(r"##\s*Clip\s+(\d+)", line)
        if clip_match:
            current_clip = clip_match.group(1).zfill(2)
            lines[current_clip] = ""
            continue
        narr_match = re.match(r"NARRATOR:\s*[\"']?(.+?)[\"']?\s*$", line)
        if narr_match and current_clip:
            existing = lines.get(current_clip, "")
            text = narr_match.group(1)
            lines[current_clip] = f"{existing} {text}".strip() if existing else text

    return lines


def _extract_full_narration_text(episode) -> str:
    """Extract all NARRATOR lines into one continuous text for full-audio generation."""
    from lib.elevenlabs import extract_continuous_narration
    return extract_continuous_narration(episode.get("dialogue_script", ""))


def run_audio_phase(episode, ep_dir):
    phase_banner("PHASE 2b: AUDIO GENERATION (ElevenLabs — continuous narration)")

    from lib.elevenlabs import generate_full_narration, generate_music
    from lib.mixer import whisper_word_timestamps

    el_key = load_env_key("ELEVENLABS_API_KEY")
    voice_id = load_env_key("ELEVENLABS_VOICE_ID")
    openai_key = load_env_key("OPENAI_API_KEY")
    if not el_key or not voice_id:
        print(f"  [{ts()}] ERROR: ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID not found")
        return False

    audio_dir = ep_dir / "output" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    full_narration_path = audio_dir / "narration_full.mp3"
    full_text = _extract_full_narration_text(episode)

    clips = episode.get("clips", [])
    clip_durations: list[tuple[str, float]] = [
        (c["id"], float(c.get("duration", 8))) for c in clips
    ]
    total_duration = sum(d for _, d in clip_durations)

    narration_ok = False

    if not full_text:
        print(f"  [{ts()}] WARNING: No narration text found — falling back to per-clip generation")
        _run_audio_phase_legacy(episode, ep_dir)
    else:
        word_count = len(full_text.split())
        print(f"  [{ts()}] Full narration: {word_count} words")

        generate_full_narration(el_key, voice_id, full_text, full_narration_path)

        if not full_narration_path.exists():
            print(f"  [{ts()}] WARNING: Full narration failed — falling back to per-clip generation")
            _run_audio_phase_legacy(episode, ep_dir)
        elif openai_key:
            narration_ok = True
            timestamps_path = audio_dir / "narration_timestamps.json"
            if timestamps_path.exists():
                import json as _json
                word_timestamps = _json.loads(timestamps_path.read_text())
                print(f"  [{ts()}] Loaded cached timestamps: {len(word_timestamps)} words")
            else:
                word_timestamps = whisper_word_timestamps(full_narration_path, openai_key)
                if word_timestamps:
                    timestamps_path.write_text(
                        json.dumps(word_timestamps, indent=2)
                    )
                    print(f"  [{ts()}] Cached timestamps to {timestamps_path.name}")

            if not word_timestamps:
                print(f"  [{ts()}] WARNING: Whisper returned no timestamps — "
                      f"falling back to per-clip generation")
                _run_audio_phase_legacy(episode, ep_dir)
                narration_ok = False
        else:
            print(f"  [{ts()}] WARNING: No OPENAI_API_KEY — cannot get timestamps. "
                  f"Falling back to per-clip generation.")
            _run_audio_phase_legacy(episode, ep_dir)

    music_duration_ms = int((total_duration + 2) * 1000)
    music_path = audio_dir / "music.mp3"
    generate_music(el_key, MUSIC_PROMPT, music_path, duration_ms=music_duration_ms)

    print(f"  [{ts()}] Audio phase complete (continuous_narration={narration_ok}).")
    return narration_ok


def _run_audio_phase_legacy(episode, ep_dir):
    """Legacy per-clip narration generation (fallback when Whisper is unavailable)."""
    from lib.elevenlabs import generate_narration

    el_key = load_env_key("ELEVENLABS_API_KEY")
    voice_id = load_env_key("ELEVENLABS_VOICE_ID")

    narr_dir = ep_dir / "output" / "audio" / "narration"
    narr_dir.mkdir(parents=True, exist_ok=True)

    narr_lines = _parse_narration_lines(episode)
    clips = episode.get("clips", [])

    for clip_meta in clips:
        clip_id = clip_meta["id"]
        text = narr_lines.get(clip_id, "")
        if not text:
            print(f"  [{ts()}] WARNING: No narration for clip {clip_id}")
            continue
        output_path = narr_dir / f"clip_{clip_id}.mp3"
        generate_narration(el_key, voice_id, text, output_path)


# ── Phase 3 (image-based): Slideshow assembly ──


def run_slideshow_phase(episode, ep_dir):
    """Build a Ken Burns slideshow video from per-sentence images synced to narration.

    Uses Whisper word-level timestamps to time each image to its narration sentence.
    Falls back to even distribution if timestamps are unavailable.
    """
    phase_banner("PHASE 3: SLIDESHOW ASSEMBLY (Ken Burns — ffmpeg)")

    from lib.slideshow import (
        parse_narration_sentences, assign_image_counts,
        sync_images_to_timestamps, build_slideshow_video,
    )

    images_dir = ep_dir / "output" / "images"
    slideshow_dir = ep_dir / "output" / "slideshow"
    slideshow_dir.mkdir(parents=True, exist_ok=True)
    output_path = slideshow_dir / "slideshow.mp4"

    if output_path.exists():
        print(f"  [{ts()}] Skipping (exists): {output_path.name}")
        return output_path

    script = episode.get("dialogue_script", "")
    sentences = parse_narration_sentences(script)
    sentences = assign_image_counts(sentences)

    if "sentence_images" in episode:
        for si in episode["sentence_images"]:
            s_idx = si["sentence_index"] - 1
            if 0 <= s_idx < len(sentences):
                sentences[s_idx].image_count = len(si.get("image_prompts", []))

    print(f"  [{ts()}] Parsed {len(sentences)} sentences, "
          f"{sum(s.image_count for s in sentences)} total images")

    timestamps_path = ep_dir / "output" / "audio" / "narration_timestamps.json"
    word_timestamps = []
    if timestamps_path.exists():
        word_timestamps = json.loads(timestamps_path.read_text())
        print(f"  [{ts()}] Loaded {len(word_timestamps)} word timestamps")
    else:
        print(f"  [{ts()}] No word timestamps — using even distribution")

    timings = sync_images_to_timestamps(sentences, word_timestamps)

    if "sentence_images" in episode:
        img_idx = 0
        for si in episode["sentence_images"]:
            s_idx = si["sentence_index"]
            for p_idx in range(len(si.get("image_prompts", []))):
                fname = f"sentence_{s_idx:02d}_img_{p_idx + 1:02d}.png"
                img_path = images_dir / fname
                if img_idx < len(timings):
                    timings[img_idx].image_path = img_path if img_path.exists() else None
                img_idx += 1
    else:
        img_idx = 0
        for s in sentences:
            for img_i in range(s.image_count):
                clip_id = f"{s.index + 1:02d}"
                img_path = images_dir / f"clip_{clip_id}_frame.png"
                if img_idx < len(timings):
                    timings[img_idx].image_path = img_path if img_path.exists() else None
                img_idx += 1

    valid_count = sum(1 for t in timings if t.image_path and t.image_path.exists())
    print(f"  [{ts()}] Mapped {valid_count}/{len(timings)} images to timestamps")

    if valid_count == 0:
        print(f"  [{ts()}] ERROR: No valid images found — cannot build slideshow")
        return None

    success = build_slideshow_video(timings, output_path)
    if not success:
        print(f"  [{ts()}] ERROR: Slideshow assembly failed")
        return None

    return output_path


# ── Phase 3 (legacy): Video generation (Veo 3.1) ──


def run_videos_chain_phase(episode, ep_dir):
    """Generate all clips as a single extension chain for visual continuity.

    Veo extends each clip from the previous one's last frames, producing a
    seamless continuous video that is then split into per-clip segments.
    Falls back to independent mode on failure.
    """
    phase_banner("PHASE 3: VIDEO GENERATION — EXTENSION CHAIN (Veo 3.1)")

    from lib.veo import (
        get_client, generate_initial, extend_video, save_chain_video,
    )
    from lib.mixer import split_chain_video

    gemini_key = load_env_key("GEMINI_API_KEY")
    if not gemini_key:
        print(f"  [{ts()}] ERROR: GEMINI_API_KEY not found.")
        return False

    client = get_client(gemini_key)

    videos_dir = ep_dir / "output" / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    chain_path = videos_dir / "chain_full.mp4"
    clips = episode.get("clips", [])
    prompts = episode["video_prompts"]
    episode_style = episode.get("style_description")

    if episode_style:
        print(f"  [{ts()}] Episode style: {episode_style[:80]}...")

    all_exist = all(
        (videos_dir / f"clip_{i + 1:02d}.mp4").exists() for i in range(len(prompts))
    )
    if all_exist:
        print(f"  [{ts()}] All {len(prompts)} clip files already exist — skipping chain generation.")
        return True

    clip_durations: list[tuple[str, float]] = []
    for i, clip_meta in enumerate(clips):
        clip_id = clip_meta.get("id", f"{i + 1:02d}")
        duration = clip_meta.get("duration", 8)
        clip_durations.append((clip_id, float(duration)))

    print(f"  [{ts()}] Starting extension chain: {len(prompts)} clips")

    try:
        first_prompt = prompts[0]
        first_duration = int(clip_durations[0][1]) if clip_durations else 8

        images_dir = ep_dir / "output" / "images"
        first_frame = images_dir / "clip_01_frame.png"

        handle = generate_initial(
            client=client,
            prompt=first_prompt,
            duration=first_duration,
            resolution="720p",
            episode_style=episode_style,
            first_frame_path=first_frame if first_frame.exists() else None,
        )
        print(f"  [{ts()}] Chain clip 01 generated ({first_duration}s)")

        for i in range(1, len(prompts)):
            clip_id = f"{i + 1:02d}"
            print(f"\n  --- Chain extension: clip {clip_id} ---")
            handle = extend_video(
                client=client,
                handle=handle,
                prompt=prompts[i],
                resolution="720p",
                episode_style=episode_style,
            )
            print(f"  [{ts()}] Chain clip {clip_id} extended "
                  f"({handle.duration_seconds:.0f}s cumulative)")

        save_chain_video(handle, chain_path)

        split_paths = split_chain_video(chain_path, clip_durations, videos_dir)
        print(f"  [{ts()}] Chain split into {len(split_paths)} clips.")

        clip_01_path = videos_dir / "clip_01.mp4"
        style_ref_path = CHANNEL_DIR / "reference_images" / "style_reference.png"
        if clip_01_path.exists() and style_ref_path.exists():
            from lib.visual_qa import check_clip01_style
            qa = check_clip01_style(clip_01_path, style_ref_path, gemini_key)
            if not qa.passed and qa.max_severity >= 4:
                print(f"  [{ts()}] Chain clip 01 has major style drift (severity {qa.max_severity}) — "
                      f"falling back to independent mode for better reference injection...")
                return run_videos_independent_phase(episode, ep_dir)

    except Exception as e:
        print(f"\n  [{ts()}] CHAIN FAILED: {e}")
        print(f"  [{ts()}] Falling back to independent clip generation...")
        return run_videos_independent_phase(episode, ep_dir)

    print(f"  [{ts()}] Videos chain phase complete.")
    return True


def run_videos_independent_phase(episode, ep_dir):
    """Generate each clip independently (fallback when chain mode fails)."""
    phase_banner("PHASE 3: VIDEO GENERATION — INDEPENDENT (Veo 3.1)")

    from lib.veo import (
        get_client, load_reference_images, load_style_reference,
        select_refs_for_prompt, generate_video, extract_style_anchor_frames,
    )

    gemini_key = load_env_key("GEMINI_API_KEY")
    if not gemini_key:
        print(f"  [{ts()}] ERROR: GEMINI_API_KEY not found.")
        return False

    client = get_client(gemini_key)
    all_refs = load_reference_images(CHANNEL_DIR)
    style_ref_bytes = load_style_reference(CHANNEL_DIR)

    videos_dir = ep_dir / "output" / "videos"
    images_dir = ep_dir / "output" / "images"
    videos_dir.mkdir(parents=True, exist_ok=True)

    episode_style = episode.get("style_description")
    if episode_style:
        print(f"  [{ts()}] Episode style: {episode_style[:80]}...")

    style_anchor_refs = None
    clips = episode.get("clips", [])
    for i, prompt in enumerate(episode["video_prompts"]):
        clip_id = f"{i + 1:02d}"
        output_path = videos_dir / f"clip_{clip_id}.mp4"

        if output_path.exists():
            print(f"  [{ts()}] Skipping (exists): {output_path.name}")
            if i == 0 and style_anchor_refs is None:
                anchor_frames = extract_style_anchor_frames(output_path)
                if anchor_frames:
                    style_anchor_refs = [f.read_bytes() for f in anchor_frames]
                    print(f"  [{ts()}] Using existing clip 01 as style anchor ({len(anchor_frames)} frames)")
            continue

        clip_meta = clips[i] if i < len(clips) else {}
        duration = clip_meta.get("duration", 8)
        resolution = "720p"
        use_reference = clip_meta.get("has_character", True)
        first_frame = images_dir / f"clip_{clip_id}_frame.png"

        ref_images = select_refs_for_prompt(all_refs, prompt) if use_reference else None

        print(f"\n  --- Clip {clip_id} ({duration}s @ {resolution})"
              f"{' +style_anchor' if style_anchor_refs and i > 0 else ''} ---")

        max_safety_retries = 3
        for attempt in range(max_safety_retries):
            success = generate_video(
                client=client,
                prompt=prompt,
                output_path=output_path,
                duration=duration,
                resolution=resolution,
                ref_images=ref_images,
                first_frame_path=first_frame if first_frame.exists() else None,
                use_reference=use_reference,
                style_anchor_refs=style_anchor_refs if i > 0 else None,
                episode_style=episode_style,
                style_ref_bytes=style_ref_bytes,
            )
            if success:
                break
            if attempt < max_safety_retries - 1:
                print(f"  [{ts()}] Safety retry {attempt + 1}/{max_safety_retries}...")

        if i == 0 and output_path.exists() and style_anchor_refs is None:
            style_ref_path = CHANNEL_DIR / "reference_images" / "style_reference.png"
            if style_ref_path.exists():
                from lib.visual_qa import check_clip01_style
                qa = check_clip01_style(output_path, style_ref_path, gemini_key)
                if not qa.passed and qa.max_severity >= 3:
                    print(f"  [{ts()}] Clip 01 drifted from style ref (severity {qa.max_severity}) — regenerating...")
                    output_path.unlink(missing_ok=True)
                    for qf in output_path.parent.glob("clip_01*.qa_frame_*.png"):
                        qf.unlink(missing_ok=True)
                    for af in output_path.parent.glob("clip_01*.anchor_*.png"):
                        af.unlink(missing_ok=True)
                    generate_video(
                        client=client,
                        prompt=prompt,
                        output_path=output_path,
                        duration=duration,
                        resolution=resolution,
                        ref_images=ref_images,
                        first_frame_path=first_frame if first_frame.exists() else None,
                        use_reference=use_reference,
                        episode_style=episode_style,
                        style_ref_bytes=style_ref_bytes,
                    )
            anchor_frames = extract_style_anchor_frames(output_path)
            if anchor_frames:
                style_anchor_refs = [f.read_bytes() for f in anchor_frames]
                print(f"  [{ts()}] Clip 01 set as style anchor ({len(anchor_frames)} frames)")

    print(f"  [{ts()}] Videos independent phase complete.")
    return True


# ── Phase 3c: Visual consistency QA ──


def run_qa_phase(episode, ep_dir, regen: bool = False, max_qa_rounds: int = 2):
    """Check visual consistency across generated clips using Gemini vision.

    Runs up to max_qa_rounds of QA -> regen cycles. After each regen pass,
    re-validates only the regenerated clips. Clips that fail twice at
    severity >= 4 are logged as persistent drift (the publish quality gate
    catches these).

    Returns (all_passed: bool, severe_clip_count: int) where severe means severity >= 4.
    """
    phase_banner("PHASE 3c: VISUAL CONSISTENCY QA (Gemini Vision)")

    from lib.visual_qa import check_clip_consistency

    gemini_key = load_env_key("GEMINI_API_KEY")
    if not gemini_key:
        print(f"  [{ts()}] WARNING: GEMINI_API_KEY not found — skipping QA")
        return True, 0

    videos_dir = ep_dir / "output" / "videos"
    images_dir = ep_dir / "output" / "images"
    clips = episode.get("clips", [])

    clip_paths: list[Path] = []
    for clip_meta in clips:
        clip_id = clip_meta["id"]
        path = videos_dir / f"clip_{clip_id}.mp4"
        if path.exists():
            clip_paths.append(path)

    if len(clip_paths) < 2:
        print(f"  [{ts()}] QA: Not enough clips to compare ({len(clip_paths)}) — skipping.")
        return True, 0

    ground_truth = images_dir / "clip_01_frame.png"
    if ground_truth.exists():
        print(f"  [{ts()}] QA: Using clip 01 keyframe as ground truth for style comparison")
    else:
        ground_truth = None

    veo_resources = None
    persistent_drift_ids: set[str] = set()
    cumulative_severe = 0

    for qa_round in range(1, max_qa_rounds + 1):
        round_label = f"round {qa_round}/{max_qa_rounds}"

        results = check_clip_consistency(
            clip_paths, gemini_key,
            ground_truth_frame=ground_truth,
        )

        failed_clips = [r for r in results if not r.passed]
        regen_clips = [r for r in failed_clips if r.max_severity >= 3]
        minor_clips = [r for r in failed_clips if r.max_severity < 3]

        if minor_clips:
            print(f"  [{ts()}] QA ({round_label}): {len(minor_clips)} clips with minor issues (severity < 3) — logged, not regenerating:")
            for r in minor_clips:
                print(f"    clip {r.clip_id}: severity {r.max_severity}/5 — {'; '.join(r.issues)}")

        if not regen_clips and not minor_clips:
            print(f"  [{ts()}] QA ({round_label}): All clips passed visual consistency check.")
            return True, cumulative_severe

        if not regen_clips:
            print(f"  [{ts()}] QA ({round_label}): No clips above severity threshold (>= 3) — skipping regen.")
            return True, cumulative_severe

        if not regen:
            print(f"\n  [{ts()}] QA ({round_label}): {len(regen_clips)} clips above regen threshold "
                  f"(run with --no-qa-regen to skip auto-fix)")
            cumulative_severe = sum(1 for r in failed_clips if r.max_severity >= 4)
            return len(regen_clips) == 0, cumulative_severe

        if qa_round == max_qa_rounds:
            for r in regen_clips:
                if r.max_severity >= 4:
                    persistent_drift_ids.add(r.clip_id)
            if persistent_drift_ids:
                print(f"  [{ts()}] QA: PERSISTENT DRIFT on clips {sorted(persistent_drift_ids)} after {max_qa_rounds} rounds")
            cumulative_severe = sum(1 for r in failed_clips if r.max_severity >= 4)
            return len(regen_clips) == 0, cumulative_severe

        print(f"\n  [{ts()}] QA ({round_label}): {len(regen_clips)} clips flagged for re-generation (severity >= 3)...")

        if veo_resources is None:
            from lib.veo import (
                get_client, load_reference_images, load_style_reference,
                select_refs_for_prompt, generate_video,
                extract_style_anchor_frames,
            )
            client = get_client(gemini_key)
            all_refs = load_reference_images(CHANNEL_DIR)
            style_ref_bytes = load_style_reference(CHANNEL_DIR)
            episode_style = episode.get("style_description")
            prompts = episode["video_prompts"]

            style_anchor_refs: list[bytes] = []
            clip_01_video = videos_dir / "clip_01.mp4"
            if clip_01_video.exists():
                anchor_frames = extract_style_anchor_frames(clip_01_video)
                style_anchor_refs = [f.read_bytes() for f in anchor_frames]
                print(f"  [{ts()}] QA regen: loaded {len(style_anchor_refs)} style anchor frames from clip 01")

            veo_resources = {
                "client": client, "all_refs": all_refs,
                "style_ref_bytes": style_ref_bytes,
                "episode_style": episode_style, "prompts": prompts,
                "style_anchor_refs": style_anchor_refs,
                "select_refs_for_prompt": select_refs_for_prompt,
                "generate_video": generate_video,
            }

        regen_clip_paths: list[Path] = []
        for qa_result in regen_clips:
            clip_idx = int(qa_result.clip_id) - 1
            if clip_idx < 0 or clip_idx >= len(veo_resources["prompts"]):
                continue

            clip_id = qa_result.clip_id
            clip_meta = clips[clip_idx] if clip_idx < len(clips) else {}
            output_path = videos_dir / f"clip_{clip_id}.mp4"
            duration = clip_meta.get("duration", 8)
            resolution = "720p"
            first_frame = images_dir / f"clip_{clip_id}_frame.png"
            ref_images = veo_resources["select_refs_for_prompt"](
                veo_resources["all_refs"], veo_resources["prompts"][clip_idx],
            )

            output_path.unlink(missing_ok=True)
            for qa_frame in output_path.parent.glob(f"clip_{clip_id}*.qa_frame_*.png"):
                qa_frame.unlink(missing_ok=True)

            print(f"  [{ts()}] QA regen: clip {clip_id} "
                  f"(issues: {'; '.join(qa_result.issues)})")

            veo_resources["generate_video"](
                client=veo_resources["client"],
                prompt=veo_resources["prompts"][clip_idx],
                output_path=output_path,
                duration=duration,
                resolution=resolution,
                ref_images=ref_images,
                first_frame_path=first_frame if first_frame.exists() else None,
                style_anchor_refs=veo_resources["style_anchor_refs"] if veo_resources["style_anchor_refs"] else None,
                episode_style=veo_resources["episode_style"],
                style_ref_bytes=veo_resources["style_ref_bytes"],
            )
            if output_path.exists():
                regen_clip_paths.append(output_path)

        if not regen_clip_paths:
            cumulative_severe = sum(1 for r in failed_clips if r.max_severity >= 4)
            return len(regen_clips) == 0, cumulative_severe

        clip_paths = regen_clip_paths
        print(f"\n  [{ts()}] QA: Re-validating {len(clip_paths)} regenerated clips...")

    cumulative_severe = sum(1 for cid in persistent_drift_ids)
    return len(persistent_drift_ids) == 0, cumulative_severe


# ── Phase 4: Per-clip audio mixing + Stitch + LUFS normalize ──


def run_mix_phase(episode, ep_dir, continuous_narration: bool = True):
    """Prepare per-clip audio: Veo ambient only (narration overlaid after stitch).

    When continuous_narration=True (default), each clip gets only its Veo
    ambient audio at reduced volume. The full narration + music are overlaid
    on the stitched video in run_post_phase via mix_final_audio().

    When continuous_narration=False (legacy fallback), uses the old per-clip
    narration chunking approach.
    """
    from lib.mixer import mix_clip_veo_only, mix_clip_audio, probe_audio_duration

    clips = episode.get("clips", [])
    videos_dir = ep_dir / "output" / "videos"
    mixed_dir = ep_dir / "output" / "mixed_clips"
    mixed_dir.mkdir(parents=True, exist_ok=True)

    if continuous_narration:
        phase_banner("PHASE 3b: PER-CLIP AUDIO (Veo ambient only — narration added after stitch)")

        for clip_meta in clips:
            clip_id = clip_meta["id"]
            duration = clip_meta.get("duration", 8)
            video_path = videos_dir / f"clip_{clip_id}.mp4"
            output_path = mixed_dir / f"clip_{clip_id}.mp4"

            mix_clip_veo_only(
                video_path=video_path,
                output_path=output_path,
                clip_duration=duration,
                veo_audio_volume=0.15,
            )
    else:
        phase_banner("PHASE 3b: PER-CLIP AUDIO MIXING (legacy — Veo SFX + Narration + Music)")

        narr_dir = ep_dir / "output" / "audio" / "narration"
        music_path = ep_dir / "output" / "audio" / "music.mp3"
        music_offset = 0.0

        for clip_meta in clips:
            clip_id = clip_meta["id"]
            duration = clip_meta.get("duration", 8)
            video_path = videos_dir / f"clip_{clip_id}.mp4"
            narration_path = narr_dir / f"clip_{clip_id}.mp3"
            output_path = mixed_dir / f"clip_{clip_id}.mp4"

            narr_dur = probe_audio_duration(narration_path) if narration_path.exists() else 0.0

            mix_clip_audio(
                video_path=video_path,
                output_path=output_path,
                narration_path=narration_path if narration_path.exists() else None,
                music_path=music_path if music_path.exists() else None,
                clip_duration=duration,
                narration_duration=narr_dur,
                music_offset=music_offset,
                music_volume=0.20,
                veo_audio_volume=0.15,
            )
            music_offset += duration

    print(f"  [{ts()}] Mix phase complete.")
    return True


def run_post_phase(episode, ep_dir, use_transitions: bool = True, continuous_narration: bool = True):
    phase_banner("PHASE 4: STITCH + FINAL MIX + LUFS NORMALIZE (ffmpeg)")

    from lib.mixer import (
        stitch_clips, stitch_clips_with_transitions,
        burn_location_title, mix_final_audio,
        validate_narration_timing, validate_clip_narration_alignment,
        probe_audio_duration, estimate_crossfade_loss,
        NARRATION_DELAY, MAX_ATEMPO,
    )

    slug = episode["episode_slug"]
    clips = episode.get("clips", [])

    mixed_clips_dir = ep_dir / "output" / "mixed_clips"
    videos_dir = ep_dir / "output" / "videos"
    final_dir = ep_dir / "output" / "mixed"
    final_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  [{ts()}] Stitching clips...")
    clip_paths = []
    for clip_meta in clips:
        clip_id = clip_meta["id"]
        mixed = mixed_clips_dir / f"clip_{clip_id}.mp4"
        raw = videos_dir / f"clip_{clip_id}.mp4"
        if mixed.exists():
            clip_paths.append(mixed)
        elif raw.exists():
            print(f"  WARNING: No mixed clip_{clip_id}.mp4, using raw video")
            clip_paths.append(raw)
        else:
            print(f"  WARNING: Missing clip_{clip_id}.mp4, skipping")

    normalized_dir = ep_dir / "output" / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    normalized_paths = []
    for cp in clip_paths:
        norm_path = normalized_dir / cp.name
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(cp),
             "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,"
                    "pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,"
                    "setsar=1",
             "-c:v", "libx264", "-preset", "fast", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k",
             str(norm_path)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            normalized_paths.append(norm_path)
        else:
            print(f"  WARNING: Failed to normalize {cp.name}, using original")
            normalized_paths.append(cp)
    if normalized_paths:
        print(f"  [{ts()}] Normalized {len(normalized_paths)} clips to 720x1280")
        clip_paths = normalized_paths

    stitched_path = final_dir / f"stitched_{slug}.mp4"

    narr_overflow = False
    if continuous_narration and use_transitions:
        narration_path = ep_dir / "output" / "audio" / "narration_full.mp3"
        if narration_path.exists():
            narr_dur = probe_audio_duration(narration_path)
            raw_video_dur = sum(float(c.get("duration", 8)) for c in clips)
            xfade_loss = estimate_crossfade_loss(len(clips))
            effective = raw_video_dur - xfade_loss - NARRATION_DELAY
            narr_at_max_tempo = narr_dur / MAX_ATEMPO
            narr_overflow = narr_at_max_tempo > effective + 0.5
            if narr_overflow:
                print(f"  [{ts()}] Narration overflow detected — deferring dip-to-black to final mix")

    if use_transitions:
        stitch_clips_with_transitions(
            clip_paths, stitched_path,
            outro_fade=0.0 if narr_overflow else 1.5,
        )
    else:
        stitch_clips(clip_paths, stitched_path)

    if continuous_narration and stitched_path.exists():
        narration_path = ep_dir / "output" / "audio" / "narration_full.mp3"
        music_path = ep_dir / "output" / "audio" / "music.mp3"

        final_mixed_path = final_dir / f"final_mixed_{slug}.mp4"
        print(f"\n  [{ts()}] Overlaying full narration + music onto stitched video...")

        atempo = 1.0
        post_narr_dur = 0.0
        if narration_path.exists() and stitched_path.exists():
            post_narr_dur = probe_audio_duration(narration_path)
            atempo = validate_narration_timing(narration_path, probe_audio_duration(stitched_path))

        timestamps_path = ep_dir / "output" / "audio" / "narration_timestamps.json"
        if timestamps_path.exists() and narration_path.exists():
            import json as _json
            try:
                word_ts = _json.loads(timestamps_path.read_text())
                clip_durs = [(c["id"], c.get("duration", 4)) for c in clips]
                validate_clip_narration_alignment(
                    word_timestamps=word_ts,
                    clip_durations=clip_durs,
                    narration_atempo=atempo,
                )
            except Exception as e:
                print(f"  [{ts()}] WARNING: alignment check failed: {e}")

        mix_ok = mix_final_audio(
            video_path=stitched_path,
            output_path=final_mixed_path,
            narration_path=narration_path if narration_path.exists() else None,
            music_path=music_path if music_path.exists() else None,
            narration_atempo=atempo,
        )

        if mix_ok and final_mixed_path.exists():
            final_path = final_dir / f"final_{slug}.mp4"
            final_mixed_path.rename(final_path)
            stitched_path.unlink(missing_ok=True)
        else:
            print(f"  [{ts()}] WARNING: Final mix failed — using stitched video without narration")
            final_path = final_dir / f"final_{slug}.mp4"
            stitched_path.rename(final_path)
    else:
        atempo = 1.0
        post_narr_dur = 0.0
        final_path = final_dir / f"final_{slug}.mp4"
        if stitched_path != final_path:
            stitched_path.rename(final_path)

    location = episode.get("location")
    year = episode.get("year")
    if location and year and final_path.exists():
        titled_path = final_dir / f"final_{slug}_titled.mp4"
        if burn_location_title(final_path, titled_path, location, year):
            final_path.unlink(missing_ok=True)
            titled_path.rename(final_path)
            print(f"  [{ts()}] Location title applied: \"{location}, {year}\"")
    elif not (location and year):
        print(f"  [{ts()}] WARNING: No location/year in episode JSON — skipping title overlay")

    return final_path, atempo, post_narr_dur


def run_slideshow_post_phase(episode, ep_dir, slideshow_path):
    """Mix narration + music onto the slideshow video and burn titles.

    Simplified version of run_post_phase — the slideshow is already one
    continuous silent video, so no per-clip stitching or normalization needed.
    """
    phase_banner("PHASE 4: FINAL MIX (Slideshow + Narration + Music)")

    from lib.mixer import (
        burn_location_title, mix_final_audio,
        validate_narration_timing, probe_audio_duration,
    )

    slug = episode["episode_slug"]
    final_dir = ep_dir / "output" / "mixed"
    final_dir.mkdir(parents=True, exist_ok=True)

    narration_path = ep_dir / "output" / "audio" / "narration_full.mp3"
    music_path = ep_dir / "output" / "audio" / "music.mp3"

    final_mixed_path = final_dir / f"final_mixed_{slug}.mp4"

    print(f"\n  [{ts()}] Overlaying narration + music onto slideshow video...")

    atempo = 1.0
    narr_dur = 0.0
    if narration_path.exists() and slideshow_path.exists():
        narr_dur = probe_audio_duration(narration_path)
        atempo = validate_narration_timing(
            narration_path, probe_audio_duration(slideshow_path),
        )

    mix_ok = mix_final_audio(
        video_path=slideshow_path,
        output_path=final_mixed_path,
        narration_path=narration_path if narration_path.exists() else None,
        music_path=music_path if music_path.exists() else None,
        narration_atempo=atempo,
        veo_audio_volume=0.0,
    )

    if mix_ok and final_mixed_path.exists():
        final_path = final_dir / f"final_{slug}.mp4"
        final_mixed_path.rename(final_path)
    else:
        print(f"  [{ts()}] WARNING: Final mix failed — using slideshow without audio")
        final_path = final_dir / f"final_{slug}.mp4"
        import shutil
        shutil.copy2(slideshow_path, final_path)

    location = episode.get("location")
    year = episode.get("year")
    if location and year and final_path.exists():
        titled_path = final_dir / f"final_{slug}_titled.mp4"
        if burn_location_title(final_path, titled_path, location, year):
            final_path.unlink(missing_ok=True)
            titled_path.rename(final_path)
            print(f"  [{ts()}] Location title applied: \"{location}, {year}\"")
    elif not (location and year):
        print(f"  [{ts()}] WARNING: No location/year in episode JSON — skipping title overlay")

    return final_path, atempo, narr_dur


# ── Phase 4b: Remotion captions ──


def run_captions_phase(final_path, ep_dir, narration_atempo=1.0, narration_duration=0.0):
    phase_banner("PHASE 4b: REMOTION KARAOKE CAPTIONS (Script Text + Remotion)")

    from lib.captions import run_captions_pipeline
    from lib.elevenlabs import extract_continuous_narration

    openai_key = load_env_key("OPENAI_API_KEY")

    narration_text = None
    dialogue_path = ep_dir / "04_dialogue_script.txt"
    if dialogue_path.exists():
        raw = dialogue_path.read_text().strip()
        narration_text = extract_continuous_narration(raw)
        if narration_text:
            print(f"  [{ts()}] Using script text for captions ({len(narration_text.split())} words)")

    if not narration_text and not openai_key:
        print(f"  [{ts()}] WARNING: No script text and no OPENAI_API_KEY — skipping captions")
        return final_path

    captioned_path = final_path.with_stem(final_path.stem + "_captioned")
    result = run_captions_pipeline(
        video_path=final_path,
        output_path=captioned_path,
        openai_api_key=openai_key,
        narration_text=narration_text,
        narration_duration=narration_duration if narration_duration > 0 else None,
        narration_atempo=narration_atempo,
    )

    if result and result.exists():
        print(f"  [{ts()}] Captioned video ready: {result}")
        return result

    print(f"  [{ts()}] Captions failed — using uncaptioned video")
    return final_path


# ── Phase 5: Publish ──


def create_github_release(slug, title, final_path):
    """Create a GitHub Release and upload the final MP4. Return the asset download URL."""
    phase_banner("PHASE 5a: GITHUB RELEASE")

    tag = f"episode-{slug}"
    print(f"  [{ts()}] Creating release: {tag}")

    result = subprocess.run(
        [
            "gh", "release", "create", tag,
            str(final_path),
            "--title", title,
            "--notes", f"Automated episode: {title}\nSlug: {slug}",
        ],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(f"  [{ts()}] gh release create failed: {result.stderr}")
        return None

    release_url = result.stdout.strip()
    print(f"  [{ts()}] Release created: {release_url}")

    view_result = subprocess.run(
        ["gh", "release", "view", tag, "--json", "assets"],
        capture_output=True, text=True,
    )

    if view_result.returncode != 0:
        print(f"  [{ts()}] Failed to get asset URL: {view_result.stderr}")
        return None

    assets = json.loads(view_result.stdout).get("assets", [])
    for asset in assets:
        if asset["name"].endswith(".mp4"):
            download_url = asset["url"]
            print(f"  [{ts()}] Asset URL: {download_url}")
            return download_url

    print(f"  [{ts()}] No MP4 asset found in release")
    return None



def publish_to_metricool_with_upload(episode, final_path, asset_url=None, schedule=""):
    """Upload video to Metricool S3 then publish to YouTube Shorts + Instagram Reels + TikTok."""
    phase_banner("PHASE 5b: METRICOOL PUBLISH")

    from lib.config import load_settings
    from lib.metricool import publish_to_metricool, upload_media_file

    settings = load_settings()

    title = episode.get("title", "You Wouldn't Wanna Be")
    hook = episode.get("hook", "")

    caption = (
        f"{title}\n\n"
        f"{hook}\n\n"
        f"#YouWouldntWannaBe #History #Shorts #HistoryFacts "
        f"#LearnOnTikTok #HistoryTok #DarkHistory #Education"
    )

    if schedule:
        print(f"  [{ts()}] Scheduled publish at: {schedule} (UTC)")

    first_comment = format_sources_comment(episode.get("sources", []))
    if first_comment:
        print(f"  [{ts()}] First comment: {len(first_comment)} chars ({len(episode.get('sources', []))} sources)")

    print(f"  [{ts()}] Uploading {final_path.name} ({final_path.stat().st_size / (1024*1024):.1f} MB) to Metricool S3...")
    try:
        media_url = upload_media_file(settings, str(final_path))
        print(f"  [{ts()}] S3 upload complete: {media_url[:80]}")
    except Exception as e:
        print(f"  [{ts()}] S3 upload failed: {e}")
        if asset_url:
            print(f"  [{ts()}] Falling back to GitHub Release URL")
            media_url = asset_url
        else:
            print(f"  [{ts()}] No fallback URL available, cannot publish")
            sys.exit(1)

    result = publish_to_metricool(
        settings=settings,
        media_url=media_url,
        title=title[:100],
        caption=caption,
        caption_instagram=caption,
        caption_youtube=caption,
        desired_publish_at=schedule,
        first_comment=first_comment,
    )

    print(f"  [{ts()}] Publish status: {result.status}")
    if result.error_message:
        print(f"  [{ts()}] Error: {result.error_message}")
    if result.status != "published":
        sys.exit(1)
    return True


def validate_word_counts(episode):
    """Check that narration word counts fit within the video duration budget.

    For image-based (slideshow) episodes, the video duration is driven by
    narration length so there's no fixed budget to overflow — just log stats.
    For Veo-based episodes, checks crossfade-adjusted video duration.
    """
    from lib.mixer import estimate_crossfade_loss, NARRATION_DELAY

    WORDS_PER_SEC = 2.4

    full_text = _extract_full_narration_text(episode)
    total_words = len(full_text.split()) if full_text else 0
    narration_seconds = total_words / WORDS_PER_SEC

    is_slideshow = "sentence_images" in episode

    if is_slideshow:
        num_sentences = len(episode.get("sentence_images", []))
        total_imgs = sum(len(si.get("image_prompts", [])) for si in episode.get("sentence_images", []))
        print(f"  Total narration: {total_words} words")
        print(f"  Estimated narration duration: {narration_seconds:.1f}s (at {WORDS_PER_SEC} wps)")
        print(f"  Mode: Image-based slideshow ({num_sentences} sentences, {total_imgs} images)")
        print(f"  [{ts()}] Slideshow duration will match narration — no fixed video budget")

        if narration_seconds > 58:
            print(f"  [{ts()}] WARNING: Estimated {narration_seconds:.1f}s exceeds ~58s Shorts/Reels ceiling")

        script = episode.get("dialogue_script", "")
        if script and "you" not in script.lower():
            print(f"  [{ts()}] WARNING: No second-person POV ('you') found in script")

        return total_words, num_sentences

    clips = episode.get("clips", [])
    num_clips = len(clips)
    raw_video_duration = sum(float(c.get("duration", 8)) for c in clips)
    crossfade_loss = estimate_crossfade_loss(num_clips)
    effective_duration = raw_video_duration - crossfade_loss - NARRATION_DELAY

    word_max = int(effective_duration * WORDS_PER_SEC)
    word_min = max(80, word_max - 15)

    print(f"  Total narration: {total_words} words")
    print(f"  Estimated narration duration: {narration_seconds:.1f}s (at {WORDS_PER_SEC} wps)")
    print(f"  Video budget: {raw_video_duration:.0f}s raw - {crossfade_loss:.1f}s crossfades "
          f"- {NARRATION_DELAY}s delay = {effective_duration:.1f}s available")
    print(f"  Word budget: {word_min}-{word_max} words (fits {effective_duration:.1f}s)")

    if total_words < word_min:
        print(f"  [{ts()}] WARNING: Total {total_words} words is below {word_min}-word minimum "
              f"— script may be too shallow")
    elif total_words > word_max:
        overflow_seconds = narration_seconds - effective_duration
        print(f"  [{ts()}] WARNING: Total {total_words} words exceeds {word_max}-word budget "
              f"(~{overflow_seconds:.1f}s overflow) — narration may be truncated or sped up")
    else:
        print(f"  [{ts()}] Word count OK: {total_words} words (budget {word_min}-{word_max})")

    if num_clips < 1:
        print(f"  [{ts()}] WARNING: No clips found in episode")
    else:
        print(f"  [{ts()}] Clip count: {num_clips} clips")

    num_img = len(episode.get("image_prompts", []))
    num_vid = len(episode.get("video_prompts", []))
    if num_img != num_clips:
        print(f"  [{ts()}] WARNING: {num_img} image prompts for {num_clips} clips")
    if num_vid != num_clips:
        print(f"  [{ts()}] WARNING: {num_vid} video prompts for {num_clips} clips")

    script = episode.get("dialogue_script", "")
    if script and "you" not in script.lower():
        print(f"  [{ts()}] WARNING: No second-person POV ('you') found in script")

    return total_words, num_clips


# ── Main ──


def main():
    parser = argparse.ArgumentParser(description="You Wouldn't Wanna Be — Automated Pipeline")
    parser.add_argument("topic", nargs="*", help="Episode topic (omit for autonomous selection)")
    parser.add_argument("--publish", action="store_true", help="Publish to YouTube + Instagram via Metricool")
    parser.add_argument("--skip-images", action="store_true", help="Skip image generation phase")
    parser.add_argument("--skip-videos", action="store_true", help="Skip video/slideshow generation phase")
    parser.add_argument("--skip-post", action="store_true", help="Skip stitch/mix phase")
    parser.add_argument("--skip-audio", action="store_true", help="Skip ElevenLabs audio generation phase")
    parser.add_argument("--skip-mix", action="store_true", help="Skip per-clip audio mixing phase (Veo mode only)")
    parser.add_argument("--skip-captions", action="store_true", help="Skip Remotion karaoke captions phase")
    parser.add_argument("--use-veo", action="store_true", help="Use Veo video generation instead of image-based slideshow")
    parser.add_argument("--no-chain", action="store_true", help="(Veo mode) Use independent clip generation instead of extension chain")
    parser.add_argument("--no-qa-regen", action="store_true", help="(Veo mode) Skip auto-regeneration of clips that fail visual consistency QA")
    parser.add_argument("--schedule", type=str, default="", help="Schedule publish at ISO datetime (e.g. '2026-03-17T17:00:00' UTC)")
    parser.add_argument("--force-publish", action="store_true", help="Publish even if visual QA quality gate fails")
    parser.add_argument("--legacy-prompt", action="store_true", help="Use legacy single-pass prompt (generate-episode.txt) instead of two-phase script+prompts")
    parser.add_argument("--legacy-script", action="store_true", help="Use single-shot script generation instead of Writer-Critic-Rewriter pipeline")
    parser.add_argument("--script-file", type=str, default="", help="Path to a pre-written script file — skips script generation, goes straight to prompt generation")
    args = parser.parse_args()

    topic = " ".join(args.topic) if args.topic else None
    use_veo = args.use_veo or args.legacy_prompt

    prompt_mode = "Legacy (single-pass)" if args.legacy_prompt else "Writer-Critic-Rewriter (script → critique → rewrite → prompts)"
    if args.legacy_script:
        prompt_mode = "Two-phase legacy (script → prompts)"
    if args.script_file:
        prompt_mode = f"Pre-written script ({args.script_file})"

    video_mode = "Veo 3.1"
    if use_veo:
        video_mode += " (extension chain)" if not args.no_chain else " (independent clips)"
    else:
        video_mode = "Image-based slideshow (Ken Burns)"

    print(f"\n{'=' * 60}")
    print(f"  You Wouldn't Wanna Be — Automated Pipeline")
    print(f"  Mode: {'Autonomous' if not topic else 'Manual'}")
    print(f"  Prompt: {prompt_mode}")
    print(f"  Video: {video_mode}")
    print(f"  Publish: {'YES' if args.publish else 'no (local only)'}")
    print(f"{'=' * 60}")

    bedrock_key = load_env_key("AWS_ACCESS_KEY_ID_BEDROCK")
    bedrock_secret = load_env_key("AWS_SECRET_ACCESS_KEY_BEDROCK")
    if not bedrock_key or not bedrock_secret:
        print("  ERROR: AWS_ACCESS_KEY_ID_BEDROCK / AWS_SECRET_ACCESS_KEY_BEDROCK not found")
        sys.exit(1)

    if not topic:
        topic = generate_topic()

    _script_artifacts = None
    _sources = []
    if args.script_file:
        script_path = Path(args.script_file)
        if not script_path.is_absolute():
            script_path = REPO_DIR / script_path
        if not script_path.exists():
            print(f"  ERROR: Script file not found: {script_path}")
            sys.exit(1)
        script = script_path.read_text().strip()
        word_count = _count_script_words(script)
        print(f"  [{ts()}] Loaded pre-written script: {script_path.name} ({word_count} words)")
        _sources = generate_sources(topic, script)
        episode = generate_episode_from_script(topic, script)
        total_words, _ = validate_word_counts(episode)
    elif args.legacy_prompt:
        episode = generate_episode_content(topic)
        total_words, _ = validate_word_counts(episode)
    else:
        if args.legacy_script:
            script = generate_script(topic)
        else:
            script, _script_artifacts = generate_script_v2(topic)
        print(f"\n  [{ts()}] Script:\n{script}\n")
        _sources = generate_sources(topic, script)
        episode = generate_episode_from_script(topic, script)
        total_words, _ = validate_word_counts(episode)

    if _sources:
        episode["sources"] = _sources

    ep_dir, slug = write_episode_files(episode)

    if _sources:
        (ep_dir / "05_sources.json").write_text(json.dumps(_sources, indent=2, ensure_ascii=False))
        print(f"  [{ts()}] Saved {len(_sources)} sources to {slug}/05_sources.json")

    if _script_artifacts:
        (ep_dir / "00_draft_script.txt").write_text(_script_artifacts["draft"])
        (ep_dir / "00_critique.md").write_text(_script_artifacts["critique"])
        print(f"  [{ts()}] Saved draft + critique artifacts to {slug}/")

    if not episode.get("style_description"):
        restored = _load_style_description_from_storyboard(ep_dir)
        if restored:
            episode["style_description"] = restored
            print(f"  [{ts()}] Restored style_description from storyboard")

    if not args.skip_images:
        run_images_phase(episode, ep_dir)

    continuous_narration = False
    if not args.skip_audio:
        continuous_narration = run_audio_phase(episode, ep_dir)
    else:
        narration_full = ep_dir / "output" / "audio" / "narration_full.mp3"
        if narration_full.exists():
            continuous_narration = True
            print(f"  [{ts()}] Audio skipped but narration_full.mp3 exists — will use for final mix")

    slideshow_path = None

    if use_veo:
        if not args.skip_videos:
            if args.no_chain:
                run_videos_independent_phase(episode, ep_dir)
            else:
                run_videos_chain_phase(episode, ep_dir)

        severe_clip_count = 0
        if not args.skip_videos:
            _qa_passed, severe_clip_count = run_qa_phase(episode, ep_dir, regen=not args.no_qa_regen)

        if not args.skip_mix:
            run_mix_phase(episode, ep_dir, continuous_narration=continuous_narration)

        final_path = None
        narr_atempo = 1.0
        narr_dur = 0.0
        if not args.skip_post:
            final_path, narr_atempo, narr_dur = run_post_phase(episode, ep_dir, continuous_narration=continuous_narration)
    else:
        if not args.skip_videos:
            slideshow_path = run_slideshow_phase(episode, ep_dir)

        severe_clip_count = 0

        final_path = None
        narr_atempo = 1.0
        narr_dur = 0.0
        if not args.skip_post and slideshow_path:
            final_path, narr_atempo, narr_dur = run_slideshow_post_phase(episode, ep_dir, slideshow_path)

    if final_path is None:
        final_path = ep_dir / "output" / "mixed" / f"final_{slug}.mp4"

    if not args.skip_captions and final_path.exists():
        final_path = run_captions_phase(final_path, ep_dir, narration_atempo=narr_atempo, narration_duration=narr_dur)

    phase_banner("GENERATION COMPLETE")
    if final_path.exists():
        size_mb = final_path.stat().st_size / (1024 * 1024)
        print(f"  Final video: {final_path}")
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print(f"  WARNING: Final video not found at {final_path}")
        if args.publish:
            print(f"  Cannot publish without final video.")
            sys.exit(1)

    images = list((ep_dir / "output" / "images").glob("*.png"))
    print(f"  Images: {len(images)}")
    if use_veo:
        videos = list((ep_dir / "output" / "videos").glob("*.mp4"))
        print(f"  Videos: {len(videos)}")

    if args.publish and final_path.exists():
        if use_veo and severe_clip_count > 2 and not args.force_publish:
            print(f"\n  QUALITY GATE FAILED: {severe_clip_count} clips at severity >= 4/5")
            print(f"  Publishing blocked. Use --force-publish to override.")
            sys.exit(1)
        asset_url = create_github_release(slug, episode["title"], final_path)
        publish_to_metricool_with_upload(episode, final_path, asset_url, schedule=args.schedule)

    phase_banner("ALL DONE")
    print(f"  Episode: {episode['title']}")
    print(f"  Slug: {slug}")


if __name__ == "__main__":
    main()
