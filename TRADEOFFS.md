# Tradeoff Notes

## Model / approach choice

**Single structured LLM call vs. multi-step agent pipeline.** I chose one well-specified call to
Gemini with a strict JSON schema (enforced natively via `response_schema`, not just prompt
instructions), rather than a multi-step agent (e.g. a
"summarize" step, then a separate "extract action items" step, then a "resolve dates" step).

Why: this task is fundamentally an extraction + structuring problem, not a task requiring
multi-step planning, tool use, or iterative reasoning. A modern instruction-following model can
reliably do summary + extraction + date resolution in a single pass when the schema and rules are
explicit. Splitting it into multiple calls would add latency, cost, and more failure points
(e.g. inconsistent state between steps) without a clear accuracy benefit for transcripts of this
size (a few hundred to a few thousand words).

**Where I would reconsider this:** for very long transcripts (multi-hour meetings, >50k tokens),
I'd chunk the transcript and do a map-reduce style pass (extract-per-chunk, then merge/dedupe
action items) since a single call would risk losing detail or hitting context limits.

## Why not a classic NLP pipeline (spaCy/regex-based extraction)?

An alternative approach would be rule-based: named-entity recognition for people, regex/date-parser
libraries for due dates, and TextRank/extractive summarization for the summary. This would be
cheaper and fully deterministic. I didn't go this route because:
- Action items in real meetings are phrased very inconsistently ("I'll own X", "can you send Y by
  Friday", "let's push this to next week") — pattern matching this robustly is a much bigger
  engineering effort than prompting a capable LLM, and it fails much more silently on Speaker
  Diarization or the different verbal cues.
  Overlap between people, decisions, and commitments is also hard to disentangle rule-by-rule.
- Relative date resolution ("by the 14th", "next Monday") given a reference meeting date is a
  small reasoning task that instruction-following LLMs handle naturally, whereas building a robust
  rule-based resolver (handling ambiguity, incomplete dates, etc.) is nontrivial.
- The JSON schema + prompt constraints already give me enough determinism/structure for this use
  case — the main risk (schema drift) is handled by explicit schema instructions + defensive
  parsing in code, not by discarding the LLM approach.

The clear tradeoff: this approach costs API tokens per run and is not offline/free, and it is only
as reliable as the model's instruction-following (mitigated with a strict schema + validation, but
not 100% guaranteed — see Known Limitations).

## Model selection

Used `gemini-2.5-flash` as the default — it's fast, free-tier accessible (no billing setup
required), and good enough for a short, well-bounded extraction task like this (nuanced
attribution like "who owns this task" and relative-date resolution). The model is configurable
via `--model` / `GEMINI_MODEL` so a more powerful model (e.g. `gemini-2.5-pro`) can be swapped in
without code changes if higher reasoning quality is needed.

**Why Gemini over Claude/OpenAI for this submission:** primarily practical — Gemini's free tier
requires no credit card, which matters for a fast turnaround build. The architecture is not
tied to one provider: `call_gemini()` is a single isolated function, so swapping in Claude's
Messages API or OpenAI's Chat Completions API is a contained change, not a rewrite.

## Known limitations

- **Schema enforcement relies on Gemini's `response_schema` mode**, which is enforced server-side
  and is fairly reliable, but not infallible — the code still defensively strips markdown fences
  and validates with `json.loads` before trusting the output, and will raise a clear error rather
  than silently emitting bad data if parsing ever fails.
- **No chunking for very long transcripts.** Currently the whole transcript is sent in one call;
  this works well up to typical meeting lengths but would need a map-reduce approach for hours-long
  transcripts.
- **No speaker diarization / audio input.** The agent assumes a text transcript is already
  available (e.g. from Zoom/Teams/Otter.ai export) with speaker labels. Adding a
  transcription step (e.g. Whisper) for raw audio input would be a natural next step.
- **No deduplication across multiple meetings.** If run meeting-over-meeting, the agent doesn't
  currently track action items across sessions (e.g. marking a previously open item as done). This
  would require a small persistence layer (e.g. SQLite) to track item state over time.
- **Single LLM provider.** Only Gemini's API is wired up. Given more time, I'd abstract the
  model call behind a thin interface to support Claude/OpenAI/local models as a fallback.
- **No automated tests.** Given the time constraint, I validated manually against the sample
  transcript. I'd add unit tests for `render_markdown()` (pure function, easy to test) and an
  integration test with a mocked API response for `call_claude()`.

## What I'd improve with more time

1. Use structured output / tool-calling for schema-guaranteed JSON instead of prompt-only.
2. Add a lightweight Streamlit/Flask UI for drag-and-drop transcript upload.
3. Add multi-transcript batch mode + a simple SQLite-backed action-item tracker across meetings.
4. Add automated tests (unit tests for rendering, integration test with a mocked API).
5. Support audio input via a transcription step (e.g. Whisper) ahead of the extraction step.
