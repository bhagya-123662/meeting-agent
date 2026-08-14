#!/usr/bin/env python3
"""
Meeting Notes -> Action Items Agent
------------------------------------
Reads a meeting transcript (plain text) and produces:
  1. A concise structured summary (decisions + discussion themes)
  2. A structured action-item list (owner, due date, priority) where stated
  3. Output as JSON (machine-readable) and Markdown (human-readable)

Usage:
    python agent.py --input sample_data/sample_transcript.txt
    python agent.py --input sample_data/sample_transcript.txt --out-dir output/
    python agent.py --input sample_data/sample_transcript.txt --model gemini-2.5-flash

Requires:
    GEMINI_API_KEY environment variable (see .env.example)
    Get a free key (no credit card required) at https://aistudio.google.com/apikey
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    print("Missing dependency 'google-genai'. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv is optional; env vars can also be set directly in the shell
    pass


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a precise meeting-notes analyst. You read raw meeting \
transcripts and extract exactly what was said - you never invent facts, owners, \
or dates that are not present or clearly implied in the transcript.

You must respond with ONLY valid JSON (no markdown fences, no commentary) \
matching this exact schema:

{
  "meeting_title": string,
  "meeting_date": string or null,
  "attendees": [string],
  "summary": string,               // 3-6 sentence overview of what the meeting covered
  "key_decisions": [string],       // explicit decisions made during the meeting
  "discussion_points": [string],   // notable topics discussed that weren't necessarily decisions
  "action_items": [
    {
      "task": string,              // clear, specific description of the action
      "owner": string or null,     // person responsible; null if not stated
      "due_date": string or null,  // ISO format YYYY-MM-DD if statable, else the raw phrase (e.g. "next Monday"), else null
      "priority": "high" | "medium" | "low",   // infer from urgency/language if not explicit
      "status": "open"             // always "open" for a freshly parsed transcript
    }
  ]
}

Rules:
- Only extract action items that are explicitly assigned or clearly actionable next steps.
- If a date is relative (e.g. "by the 14th") and a meeting date is available, resolve it to an absolute
  ISO date using the meeting date as reference. If you cannot confidently resolve it, keep the raw phrase.
- Do not fabricate owners. If no owner is stated, use null.
- Keep the summary factual and concise - no filler.
- Output must be valid JSON and nothing else.
"""

USER_PROMPT_TEMPLATE = """Here is a meeting transcript. Extract the structured summary and action items \
per the schema described in the system prompt.

TRANSCRIPT:
---
{transcript}
---
"""

# Gemini supports a native JSON response schema (response_schema), which is more reliable than
# prompt-only JSON instructions since the API enforces the shape server-side rather than hoping
# the model follows instructions. This is a nice reliability upgrade over plain prompt-based JSON.
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "meeting_title": {"type": "STRING"},
        "meeting_date": {"type": "STRING", "nullable": True},
        "attendees": {"type": "ARRAY", "items": {"type": "STRING"}},
        "summary": {"type": "STRING"},
        "key_decisions": {"type": "ARRAY", "items": {"type": "STRING"}},
        "discussion_points": {"type": "ARRAY", "items": {"type": "STRING"}},
        "action_items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "task": {"type": "STRING"},
                    "owner": {"type": "STRING", "nullable": True},
                    "due_date": {"type": "STRING", "nullable": True},
                    "priority": {"type": "STRING", "enum": ["high", "medium", "low"]},
                    "status": {"type": "STRING"},
                },
                "required": ["task", "owner", "due_date", "priority", "status"],
            },
        },
    },
    "required": [
        "meeting_title", "meeting_date", "attendees", "summary",
        "key_decisions", "discussion_points", "action_items",
    ],
}


def call_gemini(transcript: str, model: str, api_key: str) -> dict:
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=USER_PROMPT_TEMPLATE.format(transcript=transcript),
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )

    raw_text = response.text.strip()

    # Defensive cleanup in case the model wraps output in ```json fences anyway
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:].strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model did not return valid JSON. Raw output:\n{raw_text}"
        ) from e


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(data: dict) -> str:
    lines = []
    lines.append(f"# Meeting Summary: {data.get('meeting_title', 'Untitled Meeting')}")
    if data.get("meeting_date"):
        lines.append(f"**Date:** {data['meeting_date']}")
    if data.get("attendees"):
        lines.append(f"**Attendees:** {', '.join(data['attendees'])}")
    lines.append("")
    lines.append("## Summary")
    lines.append(data.get("summary", "").strip())
    lines.append("")

    if data.get("key_decisions"):
        lines.append("## Key Decisions")
        for d in data["key_decisions"]:
            lines.append(f"- {d}")
        lines.append("")

    if data.get("discussion_points"):
        lines.append("## Discussion Points")
        for d in data["discussion_points"]:
            lines.append(f"- {d}")
        lines.append("")

    lines.append("## Action Items")
    items = data.get("action_items", [])
    if not items:
        lines.append("_No action items extracted._")
    else:
        lines.append("| Task | Owner | Due Date | Priority | Status |")
        lines.append("|------|-------|----------|----------|--------|")
        for item in items:
            task = item.get("task", "")
            owner = item.get("owner") or "_unassigned_"
            due = item.get("due_date") or "_not stated_"
            priority = item.get("priority", "medium")
            status = item.get("status", "open")
            lines.append(f"| {task} | {owner} | {due} | {priority} | {status} |")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Turn a meeting transcript into a summary + action items.")
    parser.add_argument("--input", "-i", required=True, help="Path to transcript text file")
    parser.add_argument("--out-dir", "-o", default="output", help="Directory to write JSON/Markdown output")
    parser.add_argument(
        "--model", "-m", default=os.getenv("GEMINI_MODEL", "gemini-3.7-flash"),
        help="Gemini model to use (default: gemini-2.5-flash, or $GEMINI_MODEL)"
    )
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is not set.")
        print("Copy .env.example to .env and add your key, or export it directly.")
        print("Get a free key (no credit card required) at https://aistudio.google.com/apikey")
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}")
        sys.exit(1)

    transcript = input_path.read_text(encoding="utf-8")

    print(f"Reading transcript from {input_path} ...")
    print(f"Calling model '{args.model}' ...")

    try:
        data = call_gemini(transcript, model=args.model, api_key=api_key)
    except Exception as e:
        print(f"ERROR while calling the model: {e}")
        sys.exit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = input_path.stem
    json_path = out_dir / f"{stem}_output.json"
    md_path = out_dir / f"{stem}_output.md"

    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(data), encoding="utf-8")

    print(f"\nDone. Wrote:\n  - {json_path}\n  - {md_path}\n")
    print("--- Action Items ---")
    for item in data.get("action_items", []):
        print(f"  [{item.get('priority','medium').upper()}] {item.get('task')} "
              f"(owner: {item.get('owner') or 'unassigned'}, due: {item.get('due_date') or 'n/a'})")


if __name__ == "__main__":
    main()
