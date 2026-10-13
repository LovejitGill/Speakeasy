# 💬 Speakeasy
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Local inference](https://img.shields.io/badge/Inference-local-287D3C)
[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**A Multilingual AI Language Tutor
Speakeasy is a proposed voice-based language-learning application designed to help users practice multiple languages with a virtual AI tutor. Learners will speak into a microphone, hear the tutor respond, and receive targeted feedback on grammar, vocabulary, coherence, and pronunciation.**

Speakeasy helps learners practise English through typed messages or completed
recordings. Review the transcript before sending, receive a conversational reply,
and explore supported grammar suggestions. Models run on your computer; completed
conversations are stored locally in SQLite.

This **Speakeasy** repository is a fresh implementation informed by
[the original Speakwell application](https://github.com/LovejitGill/Speakwell).
It focuses on one conversation workflow with straightforward Python modules.

**Jump to:** [Features/Limitations](#featureslimitations) · [Quickstart](#not-so-quick-start) ·  [Roadmap](#roadmap) · [Verification](#verification)

## Features/Limitations

<details>
<summary>Expand Features</summary>
  
- **Tiered practice:** beginner, intermediate, and advanced levels; daily activities,
  introductions, and ordering-food scenarios.
- **Context-aware follow-ups:** supported prepared questions, bounded recent
  history, conservative name/hobby recall, and explicit stop/no-follow-up handling.
- **Reviewed voice input:** record, transcribe locally with Whisper, edit, then
  explicitly send. Recordings and transcripts never submit themselves.
- **Two grammar checks:** quick evidence-backed suggestions for simple agreement,
  auxiliary-do, modal-verb, and a/an errors; missing helping verbs show
  checker-supported present/past phrase choices without guessing tense, alongside
  independent spelling suggestions. An optional full check runs
  using a model proposal corroborated by local grammar rules. Unsupported edits
  are withheld; no correction found does not mean error-free English.
- **Saved sessions:** restore completed turns after refresh. If saving fails, keep
  the reply visible and retry without generating it again.
- **Recoverable background checks:** one grammar worker, cancellation, duplicate
  prevention, and results attached to the exact submitted turn.

  | Module | Responsibility |
|---|---|
| `app.py` | Page controls, recording, editable drafts, and feedback display |
| `assets/style.css` / `.streamlit/config.toml` | Responsive layout styling and the app-wide color theme |
| `tutor.py` | Coordinate a reply, quick feedback, and saving |
| `conversation.py` / `context.py` | Select follow-ups and handle supported facts, people, and food constraints |
| `grammar.py` | Quick/full checks sharing correction evidence and explanation logic |
| `local.py` / `speech.py` | Bounded local HTTP requests and validated offline transcription |
| `storage.py` / `worker.py` | Direct SQLite operations and recoverable grammar jobs |

The model selects among prepared follow-ups rather than writing unrestricted
conversational prose. This limits invented facts but also limits flexibility.
Context includes at most **four complete learner/tutor exchanges and 3,000
characters**. Supported declarations in the current message can update recalled
facts. Corrections are displayed separately and never enter conversational history.

  </details>

<details>
<summary>Expand Limitations</summary>

- Short answers use supported recent questions about interests, packing, tasks,
  walks, cooking, and orders. Clarification explains what answer a supported
  question is asking for; a following answer retains that question's context.
  Fragments do not become remembered facts. Ambiguous answers and unsupported
  questions still fall back; longer conversations can exhaust prepared follow-ups.
- Checked word comparisons cover **lend/borrow** and **teach/learn**. Ask
  **“What does basketball mean?”** or **“Define bank”** for up to three local
  Open English Wordnet meanings and available examples. Definitions may be formal;
  they do not identify the intended meaning or prove a correction is needed.
  Other unsupported questions still receive an explicit fallback.
- Grammar suggestions are conservative and can still be wrong. Full checks support
  single-line messages; unsupported or ambiguous corrections are withheld.
- Drafts and unsaved replies are memory-only. Refresh loses them; keep the page
  open and use **Retry saving reply** when persistence fails.
- Saved text stays on this computer; recordings are not persisted by the app.
  This is a trusted local application without accounts. Keep session URLs private.
- Interrupted grammar jobs can repeat unfinished inference after restart, but stale
  results cannot overwrite the replacement attempt.
- No continuous listening, spoken replies, pronunciation scoring, additional
  languages, or old-conversation migration is included.

The source's layered experimental engines, historical evaluation commands, and old
SQLite schema were not carried over. Useful policies and tests were adapted from
source commit `7bc00883aac7b16b96f875bb85e4f57b136482c1`; its archives remain in the
original repository.

  </details>

## Not so Quick start

<details>
<summary>Full install and first-session walkthrough</summary>

## Part 1: Prerequisites and code

You need **uv**, **Java 21**, **Ollama**, and **curl**. The commands below let uv
install Python **>=3.12.13, <3.13** and the locked Python packages automatically.
Internet is needed for installation/downloads; normal practice runs locally.

On a Mac supported by Homebrew, install missing tools with:

```bash
brew install uv openjdk@21
brew install --cask ollama
```

Intel Macs may lack compatible Homebrew packages. Reuse existing Java 21/Ollama
installations, or install compatible macOS x64 builds; setup does not install
these system programs for you. This laptop's existing paths are shown below.

If you do not already have the repository:

```bash
git clone https://github.com/LovejitGill/Speakeasy.git
cd Speakeasy
```

Run all remaining commands from the **Speakeasy** folder.

---

## Part 2: One-time setup

```bash
uv run --locked python tools/manage.py setup
```

Setup discovers Java/Ollama, verifies Java 21, prepares LanguageTool, Whisper,
and Open English Wordnet 2025,
and checks/downloads the pinned Qwen models. It saves runtime paths in ignored
`.env.local.json`; later launches load them automatically. Shell environment
variables override saved paths. Do not `source` this JSON file.

**If runtime discovery fails on this Intel development laptop**, run:

```bash
export SPEAKWELL_JAVA="$PWD/../lang_app/.tools/benchmark/jdk-21.0.12.1+1-jre/Contents/Home/bin/java"
export SPEAKWELL_OLLAMA="$PWD/../lang_app/.tools/ollama/ollama"
"$SPEAKWELL_JAVA" -version
"$SPEAKWELL_OLLAMA" --version
uv run --locked python tools/manage.py setup
```

These paths reuse existing tools in the neighboring project. On another computer,
set the variables to that computer's executable paths instead. Java must report
**21**. Setup ends with **Setup verified** and stops only services it started.
Downloads can take several minutes; there is no fixed installation-time guarantee.

---

## Part 3: Launch

```bash
uv run --locked python tools/manage.py launch
```

Open **http://127.0.0.1:8501**. Keep this terminal running.

| Piece | Local port |
|---|---|
| Ollama | 11434 |
| LanguageTool | 8081 |
| Streamlit | 8501 by default |
| Whisper | none; loads when transcribing |

Launch reuses healthy services and starts missing ones. Do not start separate
copies of `ollama.sh` or `checker.sh` as well. For another app port:

```bash
uv run --locked python tools/manage.py launch --port 8502
```

Press **Ctrl+C** to stop the app and services this launch started. Pre-existing
services remain running. Saved conversations remain in `data/practice.sqlite3`.
Use the same launch command next time; setup is not needed for each session.
For an existing installation that only needs the dictionary, run:

```bash
uv run --locked python tools/setup.py wordnet
```

The pinned archive is checksum-verified and indexed locally in `.models/`.
Launch checks that the dictionary file exists; word lookups use no network or model.

Restart the launch after changing backend code; a browser refresh is insufficient.

---

## Part 4: First practice session

1. Choose a **Level** and **Scenario**, then click **Start new session**.
2. Type in **Your message**, or record with the microphone and click Stop.
3. Review/edit the transcript, then click **Send**. Recording never sends itself.
4. Read **Quick feedback** under your message. Optional **Full grammar check**
   runs in the background; it can be cancelled. No correction does not prove
   error-free English.
5. Open saved sessions from the sidebar. Refresh restores saved turns, but loses
   unsent drafts and unsaved replies. If saving fails, use **Retry saving reply**
   before closing the page.

Allow microphone access when prompted. Use **Record again** or **Retry
transcription** as needed. Practice uses prepared follow-ups, not unrestricted
model-generated conversation; longer exchanges may run out of questions.

---

## Part 5: Troubleshooting and verification

- **Missing runtime:** set the two executable paths in Part 2 and rerun setup.
  Do not add a backslash before `@` in Homebrew paths.
- **Port occupied/unhealthy:** inspect the listener; do not kill an unidentified
  process. Choose another app port if only Streamlit's port is occupied.
- **Startup failure:** inspect `.tools/logs/ollama.log` or `checker.log`.
- **Checker download fails:** setup uses curl and verifies the archive checksum.
  For `Checksum mismatch`, remove only `.tools/LanguageTool-6.6.zip` and rerun
  setup. An HTTP 403 is a download failure, not a Java error; do not bypass checks.
- **Python downloads stall:** use the diagnostic command below. Check connection
  or proxy errors; keep `uv.lock` and certificate verification intact.

```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN
lsof -nP -iTCP:8081 -sTCP:LISTEN
UV_HTTP_TIMEOUT=30 UV_HTTP_RETRIES=1 uv sync --locked -v
```

Run only the troubleshooting command relevant to your error. To verify imports:

```bash
uv run --locked python -c "import streamlit, faster_whisper, httpx, numpy; print('Imports OK')"
```

For focused setup/launch tests:

```bash
uv run --locked pytest tests/test_manage.py -q
```

See **Verification** below for the full suite and real-service smoke command.
Standalone scripts do not load `.env.local.json`; for the smoke command, use a
terminal with the Java/runtime exports from Part 2 and keep the app launch running.
The individual scripts in `tools/` remain available for manual troubleshooting.

</details>

## Verification

```bash
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
# With Ollama, both models, and LanguageTool available:
uv run --locked python tools/acceptance.py
```

The last full-suite run passed **189 automated tests**, including service failures,
transaction rollback, duplicate workers, interruption recovery, stale results,
safe rendering, draft recovery, and Streamlit session restoration. Most service
tests use mocks. Real local-service smoke checks also exercised model selection,
grammar suggestions/abstention, and transcription.
A later review covered 25 synthetic conversation turns and 10 grammar examples,
with **13 new regression tests passing**; the full suite was not rerun.
A subsequent latency/rules/layout update passed 13 additional new tests, live
checker examples, and desktop/mobile browser layout checks. It fixed
stale recall after an explicit person correction and confirmed remaining gaps in
topic switching, longer exchanges, and clarification coverage.

The user confirmed recording permissions, playback, transcription, editable review,
explicit sending, and refresh restoration in the browser. This was a manual check,
not browser automation; the updated automatic-transcription flow has automated
UI coverage and an isolated Chrome check using injected speech with real local
Whisper. A fresh physical microphone check remains pending. A separate 24-turn conversation review identified remaining
continuity and clarification limits. These checks do not establish general
accuracy or production readiness.

## Roadmap

- [x] Typed practice, session persistence, and unsaved-reply recovery
- [x] Editable recorded input and manual browser/microphone verification
- [x] Shared grammar evidence and recoverable background checks
- [x] Initial conversation review and same-message recall correction
- [x] Relevant short-answer follow-ups for supported questions
- [x] Useful clarification of supported questions
- [x] Broader conversation and grammar review with new examples
- [ ] Explicit topic switching and longer follow-up coverage

## License

MIT — see [LICENSE](LICENSE). Third-party models and libraries retain their own licenses.

Grammar failures identify the failed stage: Ollama proposal, LanguageTool
verification, or supplemental number/plural check. If the supplemental check
fails, install the checker with `uv run python tools/setup.py checker` and set
`SPEAKWELL_JAVA` to a working Java executable when launching the app. An optional
local `.tools/java` executable/link is also supported. Quick feedback retains
its short deadline; a quick-check failure does not cancel the separate full check.

After changing grammar or worker code, restart the Streamlit process. A browser
refresh alone may retain a cached worker using the previous implementation.
Previously saved feedback is not automatically recalculated.

Open English Wordnet 2025 data © Open English Wordnet contributors, derived from
Princeton WordNet, used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
[Source and downloads](https://en-word.net/downloads). SpeakEasy converts the data
into a SQLite index of meanings/examples; it does not reproduce the full lexical
relationship graph or claim dictionary definitions are learner-adapted.
