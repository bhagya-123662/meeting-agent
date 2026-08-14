# Meeting Notes → Action Items Agent

Turns a raw meeting transcript into:
1. A concise, structured summary (decisions + discussion points)
2. A structured action-item list (owner, due date, priority) extracted from the conversation
3. Output in both **JSON** (machine-readable) and **Markdown** (human-readable, with a table)

Built as a single-purpose CLI agent using the Google Gemini API for extraction (free tier, no
credit card required), with a strict JSON schema enforced natively via Gemini's `response_schema`
mode (not just prompt instructions).

---

## How it works (architecture)

```
transcript.txt
      │
      ▼
 agent.py --input transcript.txt
      │
      ▼
System prompt + a native response_schema define the extraction contract
      │
      ▼
Gemini (gemini-3.7-flash) reads the transcript and returns schema-conformant JSON
      │
      ▼
Response is parsed & validated (json.loads, with fence-stripping fallback)
      │
      ├──► output/<name>_output.json   (structured data)
      └──► output/<name>_output.md     (human-readable summary + action table)
```

There is no multi-agent orchestration here on purpose — this is a single well-specified LLM call
with a strict output contract, since the task (extraction + structuring) doesn't benefit from
additional planning/reasoning loops. See `TRADEOFFS.md` for why.

---

## Setup

### 1. Clone and install

```bash
git clone <this-repo-url>
cd meeting-agent
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure your API key

```bash
cp .env.example .env
```

Edit `.env` and add your Gemini API key:

```
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
```

Get a free key (no credit card required) at https://aistudio.google.com/apikey if you don't have one.

### 3. Run it on the sample transcript

```bash
python agent.py --input sample_data/sample_transcript.txt
```

This writes:
- `output/sample_transcript_output.json`
- `output/sample_transcript_output.md`

and also prints a quick action-item summary to the terminal.

### 4. Run it on your own transcript

```bash
python agent.py --input path/to/your_transcript.txt --out-dir my_output/
```

Any plain-text transcript works — speaker-labeled ("Name: text") transcripts give the best
owner-attribution results, but the agent will still extract what it can from unlabeled text.

### 5. Visual demo (optional UI)

A minimal Streamlit UI is included for demoing the agent visually — paste or upload a transcript,
click Analyze, and see the structured summary + action-item table rendered live, with JSON/Markdown
download buttons. It calls the exact same `call_gemini()` / `render_markdown()` functions as the
CLI — no separate logic path, so what you see in the UI is what the CLI produces.

```bash
streamlit run app.py
```

This opens a browser tab at `http://localhost:8501`. Your `.env` key is picked up automatically,
or you can paste a key directly into the sidebar.

### Optional flags

| Flag | Description | Default |
|------|-------------|---------|
| `--input` / `-i` | Path to transcript `.txt` file | required |
| `--out-dir` / `-o` | Output directory | `output/` |
| `--model` / `-m` | Gemini model name | `gemini-3.7-flash` (or `$GEMINI_MODEL`) |

---

## Sample data included

- `sample_data/sample_transcript.txt` — a synthetic 4-person product launch sync transcript
- `sample_data/sample_transcript_output.json` — expected structured output for that transcript
- `sample_data/sample_transcript_output.md` — expected human-readable output (summary + action table)

These let a reviewer diff their own run against a known-good result.

---

## Output schema

```json
{
  "meeting_title": "string",
  "meeting_date": "string or null",
  "attendees": ["string"],
  "summary": "string",
  "key_decisions": ["string"],
  "discussion_points": ["string"],
  "action_items": [
    {
      "task": "string",
      "owner": "string or null",
      "due_date": "YYYY-MM-DD or raw phrase or null",
      "priority": "high | medium | low",
      "status": "open"
    }
  ]
}
```

---

## Repo structure

```
meeting-agent/
├── agent.py                 # CLI entry point (prompting, parsing, rendering)
├── app.py                   # Streamlit UI (visual demo, reuses agent.py functions)
├── requirements.txt
├── .env.example
├── README.md
├── TRADEOFFS.md
└── sample_data/
    ├── sample_transcript.txt
    ├── sample_transcript_output.json
    └── sample_transcript_output.md
```

## Explaining the code

- `agent.py` is a single file, deliberately, so every line is easy to walk through:
  - `SYSTEM_PROMPT` / `USER_PROMPT_TEMPLATE`: define the extraction contract
  - `call_claude()`: makes the API call, strips markdown fences defensively, parses JSON
  - `render_markdown()`: pure function, converts the parsed dict into a readable `.md` report
  - `main()`: CLI wiring (argparse, file I/O, error handling)

No hidden framework/agent-loop abstraction is used — this keeps the whole pipeline auditable in
one read-through, which matters for an extraction task where you need to trust the output.
