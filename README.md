# Speakwell in Speakeasy

Local English practice with typed messages, editable recording transcripts, saved
sessions, and conservative grammar suggestions. Fresh implementation informed by
[Speakwell](https://github.com/LovejitGill/Speakwell), reference commit
`7bc00883aac7b16b96f875bb85e4f57b136482c1`.

## Setup and launch

Requires Python 3.12.13, uv, Ollama, and Java 21 for LanguageTool. macOS/Linux only
(the worker uses an OS file lock). The lockfile includes Intel Mac compatibility.
No new runtime dependency family was added; the unused Ollama SDK was omitted.

```bash
uv sync --locked
# In another terminal, keep Ollama running locally:
bash tools/ollama.sh serve
# Explicit downloads; normal app operation never downloads models:
bash tools/ollama.sh pull qwen3:1.7b
bash tools/ollama.sh pull qwen3:4b
uv run python tools/setup.py checker
uv run python tools/setup.py speech
```

Then run each service in its own terminal:

```bash
bash tools/checker.sh
uv run streamlit run app.py
```

Open the local URL printed by Streamlit. Services bind locally; this application
has no accounts and is intended for one trusted computer, not public hosting.
Text is saved in `data/practice.sqlite3`; recordings stay in memory. Keep session
URLs private. Models and databases are ignored by Git.

Optional paths: `SPEAKWELL_DB_PATH`, `SPEAKWELL_SPEECH_MODEL` (a local Whisper
folder), `SPEAKWELL_LT_DIR`, `SPEAKWELL_JAVA` (Java executable), and `SPEAKWELL_OLLAMA` (Ollama executable). Set the Java
and checker paths in both the checker and app terminals if using existing tools.
There is no configurable remote inference endpoint. HTTP proxies and redirects
are disabled. Missing services produce explicit fallbacks or unavailable feedback.

Model identity is checked before sending text to Ollama:

| Use | Model | Required digest |
|---|---|---|
| Follow-up selection | Qwen3 1.7B | `8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7` |
| Full grammar proposal | Qwen3 4B | `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` |

Changed upstream tags may fail these checks. Inspect `/api/tags` and review any
model change instead of bypassing verification. Whisper uses CPU INT8 `base.en`,
revision `3d3d5dee26484f91867d81cb899cfcf72b96be6c`; LanguageTool is version 6.6.
Models retain the reference application's memory requirements, including the 4B
model for full checks. The first request after loading may use the timed fallback.

## Practice

Choose beginner/intermediate/advanced and daily activities/introductions/ordering
food, then start a session. Settings stay with that session. Saved sessions and
session URLs restore completed turns after refresh. Counters come from saved rows.

Recording is deliberate: **Record → Transcribe → Edit transcript → Use as draft →
Send**. Using a transcript explicitly replaces the typed draft. Neither recording
nor transcription sends a message. Invalid WAVs, silence, unclear speech, and
service failures leave drafts available for recovery. Valid recordings are mono,
16 kHz PCM16 WAV, 0.3–60 seconds, at most 2 MB. Drafts are memory-only; refresh loses
unsent drafts and unsaved replies. An unsaved reply stays visible with a retry
button; keep that page open until saving succeeds.

Quick corrections use narrow LanguageTool evidence. The optional full check runs
separately after the reply is saved, using a Qwen3 4B proposal plus exact matching
rule evidence. Unsupported corrections are withheld. “No supported correction”
does not certify correct grammar. Correction text never enters conversation history.
Full checks are associated with immutable turn IDs, can be cancelled, and execute
one at a time. Saving a turn and its job is one transaction. Interrupted jobs are
retried after exclusive worker ownership is recovered; a crash can repeat an
unfinished model call, but stale results cannot overwrite a newer attempt.

## Design and differences from the reference

- `app.py`: controls and temporary drafts; `tutor.py`: completes and saves a turn.
- `conversation.py`: one planner and model selector; `context.py`: focused,
  conservative person/recall/food policies adapted from the reference.
- `grammar.py`: quick and full checks sharing evidence and explanations.
- `local.py`: bounded loopback HTTP; `speech.py`: validated offline transcription.
- `storage.py`: direct SQLite operations; `worker.py`: one recoverable worker.

The new conversation engine selects among supported prepared follow-ups rather
than generating unrestricted prose. It handles recent interests, food constraints,
packing, unfinished tasks, simple future meals, and supported name/hobby recall.
Only the last four complete pairs, at most 3,000 characters, supply context.
Unknown questions get an explicit fallback. Complex or ambiguous statements may
receive a general invitation. Stop/no-follow-up requests take precedence.
Word explanations cover lend/borrow and teach/learn; question clarification quotes
the prior reply rather than claiming an unverified explanation.

There is one conversation mode. Historical strategy chains, developer evaluations,
old schemas, streaming voice, spoken replies, pronunciation scoring, and migrations
are omitted. No historical evaluation score validates this implementation.

Whisper runs in a fresh child process for each recording, allowing a 90-second
timeout and cleanup without persisting audio; this trades model reload latency for
simple lifecycle management. Quick checks have a 0.3-second budget; conversation
selection has 1.4 seconds. Full grammar has a 55-second deadline. These are software
deadlines, not hard real-time guarantees.

## Verification

```bash
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
# With both models and LanguageTool running:
uv run --locked python tools/acceptance.py
```

Tests cover behavior, service validation, rollback, cancellation, duplicate workers,
process interruption, stale results, safe rendering, refresh, draft recovery, and
audio rejection. Streamlit AppTest simulates controls; it does not verify browser
microphone permissions. See `improvement_plan.md` for this checkout's results and
remaining acceptance work. Keep the source repository and its evaluation archives
unchanged; no source-tree or old-database compatibility is required.
