# 💬 Speakeasy
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Local inference](https://img.shields.io/badge/Inference-local-287D3C)
[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**AI Language Tutor**

MVP: (Current capabilities) The current proof of concept supports English practice through typed messages or reviewed speech transcripts. It provides prepared tutor responses, limited quick grammar feedback, optional full grammar suggestions, local vocabulary lookup, and saved sessions. It does not yet support real-time conversation, multilingual practice, spoken tutor replies, or pronunciation feedback.
Speakeasy helps learners practise English through typed messages or completed
recordings. Review the transcript before sending, receive a conversational reply,
and explore supported grammar suggestions. Models run on your computer; completed
conversations are stored locally in SQLite.

<details>
<summary>Goals </summary>
  
Multilingual AI Language Tutor
Speakeasy is a proposed voice-based language-learning application designed to help users practice language(s) with a virtual AI tutor to improve grammar and vocabulary, and develop speaking skills through personalized feedback, with a focus on real-time spoken interaction. Learners will speak into a mic, hear the tutor respond, and receive targeted feedback on grammar, vocabulary, coherence, and pronunciation.

  </details>

**Jump to:** [Features/Limitations](#featureslimitations) · [Quickstart](#not-so-quick-start) · [Roadmap](#roadmap)

## Current Features/Limitations

<details>
<summary>Expand Features</summary>
  
- **Tiered practice:** beginner, intermediate, and advanced levels; daily activities,
  introductions, and ordering-food scenarios.
- **Context-aware follow-ups:** supported prepared questions, bounded recent
  history, conservative name/hobby recall, and explicit stop/no-follow-up handling.
- **Reviewed voice input:** record, transcribe locally with Whisper, edit, then
  explicitly send. Recordings and transcripts never submit themselves.
- **Two grammar checks:** quick feedback uses a few deterministic local phrase
  rules and never loads a model. Full feedback runs local CPU T5 in the background;
  ERRANT describes its edits and the app adds generic explanations. Neither ERRANT
  labels nor an unchanged result prove a sentence is correct.
- **Saved sessions:** restore completed turns after refresh. If saving fails, keep
  the reply visible and retry without generating it again.
- **Recoverable background checks:** one grammar worker, cancellation, duplicate
  prevention, and results attached to the exact submitted turn.

| Module | Responsibility |
|---|---|
| `app.py` | Page controls, recording, editable drafts, and feedback display |
| `assets/style.css` / `.streamlit/config.toml` | Responsive layout styling and the app-wide color theme |
| `speakeasy/tutor.py` | Coordinate a reply, quick feedback, and saving |
| `speakeasy/conversation.py` / `speakeasy/context.py` | Select follow-ups and handle supported facts, people, and food constraints |
| `speakeasy/grammar.py` | Quick rules, full checks, ERRANT edits, and local explanations |
| `speakeasy/local.py` / `speakeasy/speech.py` | Bounded local HTTP requests, offline T5 correction and transcription |
| `speakeasy/storage.py` / `speakeasy/worker.py` | Direct SQLite operations and recoverable grammar jobs |
| `speakeasy/vocabulary.py` / `speakeasy/errors.py` | Local dictionary lookup and safe application errors |

Application modules live in the `speakeasy` package; `app.py` remains the
Streamlit entry point. Run commands from the repository root. Model files,
rules, assets, and saved history remain in their existing root directories.

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
  One known routing issue: “What do you mean?” can be treated as a WordNet lookup
  for “you” instead of a request to explain the tutor's question. This also affects
  clarification follow-ups that depend on that reply.
- Checked word comparisons cover **lend/borrow** and **teach/learn**. Ask
  **“What does basketball mean?”** or **“Define bank”** for up to three local
  Open English Wordnet meanings and available examples. Definitions may be formal;
  they do not identify the intended meaning or prove a correction is needed.
  Other unsupported questions still receive an explicit fallback.
- Grammar suggestions can be wrong or change intended meaning. Full checks support
  single-line messages; ERRANT categories describe edits without verifying them.
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

You need **uv**. Ollama is optional for model-selected conversation replies. The lock requires Python **>=3.12.13, <3.13**.
Internet is needed for installation and model downloads; practice runs locally.

On a Mac supported by Homebrew, install missing tools with:

```bash
brew install uv
brew install --cask ollama
```

The Homebrew and Linux installer commands are platform examples and were not run
on the verified Intel Mac; it already had uv and Ollama installed.

Intel Macs may lack compatible Homebrew packages. Reuse existing Ollama
installations, or install compatible macOS x64 builds; setup does not install
these system programs for you. This laptop's existing paths are shown below.

If you do not already have the repository:

```bash
git clone https://github.com/LovejitGill/Speakeasy.git
cd Speakeasy
```

Run all remaining commands from the **Speakeasy** folder.

---

## Part 2: Dependencies and one-time downloads

```bash
uv sync --locked
# Not run on a clean machine here: this downloads weights and data.
uv run --locked python tools/manage.py setup
```

`uv sync --locked` installs the pinned dependencies, including CPU PyTorch,
ERRANT, spaCy, and the `en_core_web_sm` 3.8.0 wheel. Managed setup downloads the
pinned Whisper and T5 weights and local WordNet data. It does not start Ollama or
download Qwen. Setup requires internet on a fresh installation.

For model-selected conversation replies, add `--with-ollama` to setup and launch.
This opt-in mode starts/reuses Ollama and checks/pulls the pinned `qwen3:1.7b`
model. Existing `qwen3:4b` configuration remains supported but is not required
by current conversation or grammar features.

These component commands repeat an individual download or repair a missing local
asset. They were not rerun for this documentation update because the pinned
assets were already installed:

```bash
uv run --locked python tools/setup.py grammar # T5 weights
uv run --locked python tools/setup.py speech  # Whisper weights
uv run --locked python tools/setup.py wordnet # local dictionary data
```

The English spaCy model comes from `uv sync --locked`; it is not downloaded by
`tools/setup.py grammar`. To check the installed ERRANT/spaCy pair:

```bash
uv run --locked python -c 'import errant, spacy; spacy.load("en_core_web_sm"); errant.load("en"); print("ERRANT and English spaCy model ready")'
```

T5 weights live in `.models/gec-t5_small` (override with
`SPEAKWELL_GRAMMAR_MODEL`); all model and data directories are Git-ignored.
The T5 model is `Unbabel/gec-t5_small`; Whisper is
`Systran/faster-whisper-base.en`. The dependency lock and installed model
compatibility were checked on the Intel Mac described below.

**If runtime discovery fails on this Intel development laptop**, run:

```bash
export SPEAKWELL_OLLAMA="$PWD/../lang_app/.tools/ollama/ollama"
"$SPEAKWELL_OLLAMA" --version
uv run --locked python tools/manage.py setup --with-ollama
```

This path reuses an existing tool in the neighboring project. On another computer,
set the variable to that computer's executable path instead. Setup ends with
**Setup verified** and stops only services it started.
Downloads can take several minutes; there is no fixed installation-time guarantee.

---

## Part 3: Launch

```bash
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 UV_OFFLINE=1
# Offline launch sequence; requires the dependencies and all model files above.
# This exact offline launch command was not rerun while editing this guide.
uv run --offline --locked python tools/manage.py launch
```

Open **http://127.0.0.1:8501**. Keep this terminal running.
The launcher reuses local assets without starting Ollama. If `--with-ollama` is
supplied, it starts/reuses the service and verifies the conversation model.
After installation, the Hugging Face and uv offline flags prevent model/package
downloads. T5 also sets its offline flags in its child process. **Tested on the
Intel Mac in this repository:** PyTorch is pinned to 2.2.2 and T5/Whisper use
CPU; Ollama detected CPU inference (`library=cpu`, `-ngl 0`, zero VRAM). Ollama
chooses its available local compute automatically on other systems.

| Piece | Local port |
|---|---|
| Ollama | 11434 |
| Streamlit | 8501 by default |
| Whisper | none; loads when transcribing |

For another app port:

```bash
uv run --locked python tools/manage.py launch --port 8502
```

The alternate-port example is supported by the launcher but was not run in this
audit.

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
4. Read **Quick feedback** under your message. It checks only a small set of
   local phrases; “no issues detected” means those checks found no match. Optional
   **Full grammar check** runs CPU T5/ERRANT in the existing background worker and
   can be cancelled. It accepts single-line input up to 128 T5 tokens. A proposed
   rewrite can change meaning; edits/categories are descriptive and never
   verified or applied automatically. Missing weights or inference errors leave
   the full result unavailable while quick feedback remains usable.
5. Open saved sessions from the sidebar. Refresh restores saved turns, but loses
   unsent drafts and unsaved replies. If saving fails, use **Retry saving reply**
   before closing the page.

Allow microphone access when prompted. Use **Record again** or **Retry
transcription** as needed. Practice uses prepared follow-ups, not unrestricted
model-generated conversation; longer exchanges may run out of questions.

### Verify the app on your device

- Record a short message with your microphone. Confirm the transcript appears
  for review and is not sent until you click **Send**.
- Try a sentence with a possible grammar issue. Review the quick feedback and,
  if enabled, the full suggestion. Check that the original message remains
  unchanged and treat the correction as a suggestion.
- Test a follow-up conversation and open a saved session to confirm your turns
  are restored.

These hands-on checks help you assess microphone behavior and correction
usefulness on your device. Automated tests do not establish general correction
accuracy or physical microphone behavior.

---

## Part 5: Troubleshooting

- **Optional Ollama runtime missing:** set the executable path in Part 2 and rerun setup with `--with-ollama`.
  Do not add a backslash before `@` in Homebrew paths.
- **Port occupied/unhealthy:** inspect the listener; do not kill an unidentified
  process. Choose another app port if only Streamlit's port is occupied.
- **Startup failure:** inspect `.tools/logs/ollama.log`.
- **Full feedback unavailable / T5 files missing:** run
  `uv run --locked python tools/setup.py grammar`; check that
  `SPEAKWELL_GRAMMAR_MODEL`, if set, points to the directory containing the pinned
  T5 files. For a missing spaCy English model or package, run `uv sync --locked`.
  Full feedback reports an unavailable state when these assets cannot load.
- **Whisper files missing:** run `uv run --locked python tools/setup.py speech`.
- **WordNet missing:** run `uv run --locked python tools/setup.py wordnet`.
- **Qwen/Ollama unavailable:** conversation uses prepared follow-ups, and grammar
  feedback remains available. Only `--with-ollama` requires a healthy Ollama
  service and the pinned Qwen 1.7B model. AI-generated Qwen explanations are not
  implemented; full grammar explanations are generic local text.
- **Python downloads stall:** use the diagnostic command below. Check connection
  or proxy errors; keep `uv.lock` and certificate verification intact.

```bash
lsof -nP -iTCP:11434 -sTCP:LISTEN
UV_HTTP_TIMEOUT=30 UV_HTTP_RETRIES=1 uv sync --locked -v
```

These diagnostics are examples and were not needed on the verified host.

Run only the troubleshooting command relevant to your error. To verify imports:

```bash
uv run --locked python -c "import streamlit, faster_whisper, httpx, numpy, errant, spacy; spacy.load('en_core_web_sm'); print('Imports OK')"
```

### Try it on your device

- Type a message and send it. Confirm that a tutor reply and quick feedback appear.
- Try **Full grammar check**. Review any suggestion and confirm your original
  message remains unchanged. Suggestions may be incorrect or miss errors.
- Record a short message. Confirm the transcript appears for review, edit it,
  then send it yourself.
- Open a saved session, then refresh the page and check that completed turns
  are still available.

These steps let you check the app’s behavior on your device, including
microphone access and transcription.

</details>

## Roadmap

- [x] Typed practice, session persistence, and unsaved-reply recovery
- [x] Editable recorded input and manual browser/microphone verification
- [x] Local T5/ERRANT grammar suggestions and recoverable background checks
- [x] Initial conversation review and same-message recall correction
- [x] Relevant short-answer follow-ups for supported questions
- [x] Useful clarification of supported questions
- [x] Broader conversation and grammar review with new examples
- [ ] Explicit topic switching and longer follow-up coverage
- [ ] Add selectable practice languages, with matching tutor conversation,
  transcription, grammar feedback, and vocabulary support.
- [ ] Support real-time spoken conversation, including responsive turn-taking
  and spoken tutor replies.
- [ ] Give learners actionable speech feedback, such as pronunciation,
  intelligibility, and pacing.
- [ ] Personalize conversation topics and feedback to each learner’s goals,
  proficiency, and progress.

## License

MIT — see [LICENSE](LICENSE). Third-party models and libraries retain their own licenses.

After changing grammar or worker code, restart the Streamlit process. A browser
refresh alone may retain a cached worker using the previous implementation.
Previously saved feedback is not automatically recalculated.

Open English Wordnet 2025 data © Open English Wordnet contributors, derived from
Princeton WordNet, used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
[Source and downloads](https://en-word.net/downloads). SpeakEasy converts the data
into a SQLite index of meanings/examples; it does not reproduce the full lexical
relationship graph or claim dictionary definitions are learner-adapted.
