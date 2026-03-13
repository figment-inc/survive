#!/usr/bin/env python3
"""Build the n8n workflow JSON for You Wouldn't Wanna Be automated pipeline.

The workflow is simpler than excellenthistory's because survive.history has a full
lib/ module system. The n8n workflow just calls run_pipeline.py as a subprocess
rather than reimplementing the pipeline in n8n nodes.

Usage:
  python n8n/_build_workflow.py
"""

import json
import uuid
import pathlib


def uid():
    return str(uuid.uuid4())


nodes = []
connections = {}


def add(name, ntype, pos, params, tv="4.2", **kw):
    n = {
        "id": uid(),
        "name": name,
        "type": ntype,
        "position": pos,
        "parameters": params,
        "typeVersion": float(tv) if "." in str(tv) else int(tv),
    }
    n.update(kw)
    nodes.append(n)
    return n


def connect(src, dst, si=0, di=0):
    connections.setdefault(src, {"main": []})
    while len(connections[src]["main"]) <= si:
        connections[src]["main"].append([])
    connections[src]["main"][si].append({"node": dst, "type": "main", "index": di})


# ============================================================
# Phase 0: Schedule Trigger (every 6 hours)
# ============================================================
add(
    "Schedule Trigger",
    "n8n-nodes-base.scheduleTrigger",
    [-800, 400],
    {
        "rule": {
            "interval": [
                {
                    "field": "hours",
                    "hoursInterval": 6,
                }
            ]
        }
    },
    tv="1.2",
)

# ============================================================
# Set Environment Variables
# ============================================================
add(
    "Set Environment",
    "n8n-nodes-base.set",
    [-520, 400],
    {
        "options": {},
        "assignments": {
            "assignments": [
                {"id": uid(), "name": "ANTHROPIC_API_KEY", "type": "string", "value": ""},
                {"id": uid(), "name": "GEMINI_API_KEY", "type": "string", "value": ""},
                {"id": uid(), "name": "NANOBANANA_API_KEY", "type": "string", "value": ""},
                {"id": uid(), "name": "NANOBANANA_MODEL", "type": "string", "value": "nano-banana-pro"},
                {"id": uid(), "name": "ELEVENLABS_API_KEY", "type": "string", "value": ""},
                {"id": uid(), "name": "ELEVENLABS_VOICE_ID", "type": "string", "value": ""},
                {"id": uid(), "name": "METRICOOL_USER_TOKEN", "type": "string", "value": ""},
                {"id": uid(), "name": "METRICOOL_BLOG_ID", "type": "string", "value": ""},
                {"id": uid(), "name": "METRICOOL_USER_ID", "type": "string", "value": ""},
                {"id": uid(), "name": "METRICOOL_PUBLISH_ENABLED", "type": "string", "value": "true"},
                {"id": uid(), "name": "REPO_DIR", "type": "string", "value": "/path/to/survive.history"},
                {"id": uid(), "name": "DISCORD_WEBHOOK_URL", "type": "string", "value": ""},
            ]
        },
    },
    tv="3.4",
    notesInFlow=True,
    notes="SET ALL VALUES BEFORE STARTING",
)

connect("Schedule Trigger", "Set Environment")

# ============================================================
# Run Pipeline (Execute Command)
# ============================================================
add(
    "Run Pipeline",
    "n8n-nodes-base.executeCommand",
    [-200, 400],
    {
        "command": (
            '=cd {{ $json.REPO_DIR }} && '
            'ANTHROPIC_API_KEY={{ $json.ANTHROPIC_API_KEY }} '
            'GEMINI_API_KEY={{ $json.GEMINI_API_KEY }} '
            'NANOBANANA_API_KEY={{ $json.NANOBANANA_API_KEY }} '
            'NANOBANANA_MODEL={{ $json.NANOBANANA_MODEL }} '
            'ELEVENLABS_API_KEY={{ $json.ELEVENLABS_API_KEY }} '
            'ELEVENLABS_VOICE_ID={{ $json.ELEVENLABS_VOICE_ID }} '
            'METRICOOL_USER_TOKEN={{ $json.METRICOOL_USER_TOKEN }} '
            'METRICOOL_BLOG_ID={{ $json.METRICOOL_BLOG_ID }} '
            'METRICOOL_USER_ID={{ $json.METRICOOL_USER_ID }} '
            'METRICOOL_PUBLISH_ENABLED={{ $json.METRICOOL_PUBLISH_ENABLED }} '
            'python3 n8n/run_pipeline.py --publish 2>&1'
        ),
    },
    tv=1,
)

connect("Set Environment", "Run Pipeline")

# ============================================================
# Check Exit Code
# ============================================================
add(
    "Pipeline Succeeded?",
    "n8n-nodes-base.if",
    [100, 400],
    {
        "options": {},
        "conditions": {
            "combinator": "and",
            "conditions": [
                {
                    "id": uid(),
                    "operator": {"type": "number", "operation": "equals"},
                    "leftValue": "={{ $json.exitCode }}",
                    "rightValue": 0,
                }
            ],
            "options": {
                "version": 2,
                "leftValue": "",
                "caseSensitive": True,
                "typeValidation": "strict",
            },
        },
    },
    tv="2.2",
)

connect("Run Pipeline", "Pipeline Succeeded?")

# ============================================================
# Success Notification
# ============================================================
add(
    "Discord Success",
    "n8n-nodes-base.httpRequest",
    [400, 300],
    {
        "url": "={{ $('Set Environment').item.json.DISCORD_WEBHOOK_URL }}",
        "method": "POST",
        "sendBody": True,
        "contentType": "raw",
        "rawContentType": "application/json",
        "body": (
            '={"content": "New You Wouldn\'t Wanna Be episode generated and published!\\n'
            "```\\n{{ $('Run Pipeline').item.json.stdout.slice(-500) }}\\n```\"}"
        ),
        "options": {},
    },
    tv="4.2",
)

connect("Pipeline Succeeded?", "Discord Success", 0)

# ============================================================
# Failure Notification
# ============================================================
add(
    "Discord Failure",
    "n8n-nodes-base.httpRequest",
    [400, 500],
    {
        "url": "={{ $('Set Environment').item.json.DISCORD_WEBHOOK_URL }}",
        "method": "POST",
        "sendBody": True,
        "contentType": "raw",
        "rawContentType": "application/json",
        "body": (
            '={"content": "FAILED: You Wouldn\'t Wanna Be pipeline error!\\n'
            "Exit code: {{ $('Run Pipeline').item.json.exitCode }}\\n"
            "```\\n{{ $('Run Pipeline').item.json.stderr.slice(-500) }}\\n```\"}"
        ),
        "options": {},
    },
    tv="4.2",
)

connect("Pipeline Succeeded?", "Discord Failure", 1)

# ============================================================
# Sticky Notes for documentation
# ============================================================
add(
    "Sticky Note - Setup",
    "n8n-nodes-base.stickyNote",
    [-860, 180],
    {
        "width": 700,
        "height": 400,
        "color": 3,
        "content": (
            "# You Wouldn't Wanna Be — Automated Pipeline\n\n"
            "## Before you start:\n"
            "1. Set ALL API keys in the 'Set Environment' node\n"
            "2. Set REPO_DIR to the absolute path of the survive.history repo\n"
            "3. Ensure Python 3.10+, ffmpeg, and gh CLI are installed on the n8n host\n"
            "4. Install Python deps: `pip install -r requirements.txt`\n"
            "5. Place skeleton reference image at `.channel/reference_images/skeleton_front_neutral.jpg`\n"
            "6. (Optional) Set DISCORD_WEBHOOK_URL for notifications\n\n"
            "## How it works:\n"
            "- Runs every 6 hours (or manual trigger)\n"
            "- Claude picks a new historical disaster topic\n"
            "- Claude generates all prompts (image, video, narration)\n"
            "- NanoBanana Pro generates keyframe images\n"
            "- Veo 3.1 generates video clips with ambient audio\n"
            "- ElevenLabs generates narrator TTS + background music\n"
            "- ffmpeg mixes audio, burns captions, stitches final video\n"
            "- Publishes via GitHub Release + Metricool (IG Reel + YT Short)"
        ),
    },
    tv=1,
)

add(
    "Sticky Note - Pipeline",
    "n8n-nodes-base.stickyNote",
    [-260, 180],
    {
        "width": 300,
        "height": 120,
        "color": 5,
        "content": (
            "## Pipeline Execution\n"
            "Runs `n8n/run_pipeline.py --publish`\n"
            "~30-45 min per episode"
        ),
    },
    tv=1,
)

add(
    "Sticky Note - Notifications",
    "n8n-nodes-base.stickyNote",
    [340, 180],
    {
        "width": 300,
        "height": 120,
        "color": 7,
        "content": (
            "## Notifications\n"
            "Discord webhook on success/failure\n"
            "Includes pipeline output tail"
        ),
    },
    tv=1,
)

# ============================================================
# Build final workflow JSON
# ============================================================
workflow = {
    "id": uid().replace("-", "")[:16],
    "meta": {"instanceId": uid()},
    "name": "You Wouldn't Wanna Be — Automated Pipeline (Every 6 Hours)",
    "tags": [],
    "nodes": nodes,
    "active": False,
    "pinData": {},
    "settings": {"executionOrder": "v1"},
    "versionId": uid(),
    "connections": connections,
}

out = pathlib.Path(__file__).parent / "survive-history-workflow.json"
out.write_text(json.dumps(workflow, indent=2))
print(f"Written {out} ({out.stat().st_size / 1024:.1f} KB, {len(nodes)} nodes)")
