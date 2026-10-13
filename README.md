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

**Jump to:** [Features/Limitations](#Features/Limitations) · [Quickstart](#quickstart) · [Configuration](#configuration) · [Roadmap](#roadmap) · [Verification](#verification) 

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
  auxiliary-do, modal-verb, and a/an errors, plus an optional full check
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
- Checked word explanations cover **lend/borrow** and **teach/learn**. Other direct
  questions and unsupported clarification requests receive an explicit fallback.
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
 
A step-by-step guide to installing and using Speakeasy. About 20–40 minutes the
first time, mostly downloads. After that, starting a session takes under a minute.
 
Speakeasy runs four things on your computer:
 
| Piece | What it does | Port |
|---|---|---|
| Ollama | Runs the Qwen3 language models | 11434 |
| LanguageTool | Checks grammar | 8081 |
| Streamlit app | The web interface you use | 8501 |
| Whisper | Transcribes recordings (loads on demand, no server) | none |
 
Everything stays on your machine. You need internet only for the downloads in Parts 3 and 4.
 
---
 
## Part 1: Install the prerequisites
 
You need **uv**, **Ollama**, and **Java 21**. Python is handled for you.
 
### macOS
 
```bash
# Homebrew (skip if you already have it): https://brew.sh
brew install uv
brew install --cask ollama      # or download from https://ollama.com
brew install openjdk@21
```
 
Homebrew's Java is not on your PATH by default. Find it and set it for the
terminal that launches LanguageTool and the app:
 
```bash
# Apple Silicon
export SPEAKWELL_JAVA=/opt/homebrew/opt/openjdk@21/bin/java
# Intel Mac
export SPEAKWELL_JAVA=/usr/local/opt/openjdk@21/bin/java
```
 
### Linux (Debian/Ubuntu shown)
 
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://ollama.com/install.sh | sh
sudo apt install openjdk-21-jre-headless
```
 
Restart your terminal so `uv` is on your PATH.
 
### Check each tool
 
```bash
uv --version
ollama --version
java -version      # or: "$SPEAKWELL_JAVA" -version   (must report 21)
```
 
### Stop any background Ollama
 
The installers above usually start Ollama automatically on port 11434. Speakeasy
runs its own copy through `tools/ollama.sh`, which keeps models in the project
folder. Two copies cannot share the port, and a background copy would not see the
project's models, so stop it first:
 
- **macOS:** quit Ollama from the menu bar icon
- **Linux:** `sudo systemctl disable --now ollama`
---
 
## Part 2: Get the code
 
```bash
git clone https://github.com/LovejitGill/Speakeasy.git
cd Speakeasy
```
 
Run every later command from this `Speakeasy` folder.
 
---
 
## Part 3: Install the Python dependencies
 
```bash
uv sync --locked
```
 
The project needs Python 3.12.13 or newer, so on most machines uv first downloads
it (internet required). It then creates a `.venv` folder and installs the exact
package versions in `uv.lock`. `--locked` makes it fail rather than silently
change versions.
 
---
 
## Part 4: Download the models (one time)
 
You need two terminals for this part.
 
**Terminal 1:** start Ollama and leave it running.
 
```bash
bash tools/ollama.sh serve
```
 
**Terminal 2:** download everything.
 
```bash
bash tools/ollama.sh pull qwen3:1.7b      # conversation model, about 1.4 GB
bash tools/ollama.sh pull qwen3:4b        # full grammar model, about 2.5 GB
uv run --locked python tools/setup.py checker   # LanguageTool 6.6, checksum verified
uv run --locked python tools/setup.py speech    # Whisper base.en, pinned revision
```
 
Expected output ends with `LanguageTool 6.6 verified and extracted. Java 21 is
required.` and `Pinned Whisper base.en files downloaded.`
 
Models land in `.models/` and `.tools/` inside the project (both are git-ignored).
You will not need internet again.
 
If the checker download prints `Checksum mismatch`, delete
`.tools/LanguageTool-6.6.zip` and rerun that command.
 
---
 
## Part 5: Start everything
 
Use **three terminals** in the `Speakeasy` folder (Terminal 1 is already running
Ollama from Part 4).
 
| Terminal | Command | Leave running |
|---|---|---|
| 1 | `bash tools/ollama.sh serve` | yes |
| 2 | `bash tools/checker.sh` | yes |
| 3 | `uv run --locked streamlit run app.py` | yes |
 
Keep a fourth terminal free for other commands, such as tests.
 
If you set `SPEAKWELL_JAVA` in Part 1, set it in **both** the checker terminal and
the app terminal.
 
Streamlit prints a local URL, usually **http://127.0.0.1:8501**. Open it in your
browser.
 
### Quick health check (optional)
 
In any free terminal:
 
```bash
curl -s http://127.0.0.1:11434/api/tags | head -c 200     # lists your models
curl -s http://127.0.0.1:8081/v2/languages | head -c 100  # LanguageTool answers
```
 
Both should print JSON. If one is empty or errors, that service is not running.
 
---
 
## Part 6: Your first practice session
 
1. **Choose settings** in the sidebar: a **Level** (beginner, intermediate,
   advanced) and a **Scenario** (daily activities, introductions, ordering food).
2. Click **Start new session**. The tutor asks an opening question.
3. **Answer by typing.** Write in the **Your message** box (up to 1,000
   characters) and click **Send**.
4. **Or answer by voice.**
   1. Click the microphone under **Record a message** and allow microphone access
      when your browser asks.
   2. Speak one or two sentences, then stop the recording.
   3. Wait for the transcript to appear in the message box. Whisper runs on your
      CPU, so allow a few seconds.
   4. **Check and fix the transcript**, then click **Send**. Nothing is submitted
      automatically.
   5. Use **Record again** to redo it, or **Retry transcription** if it failed.
5. **Read the reply.** The tutor responds with a follow-up question.
6. **Read your feedback** under your message:
   - **Quick feedback** appears immediately: simple rule-based suggestions and
     optional "Did you mean" spelling alternatives. Click **This is a name** to
     stop a name being flagged (remembered until you close the browser session).
   - **Full grammar check** runs in the background after you send. It may take up
     to about a minute. Click **Cancel grammar check** to stop it. If no correction
     is shown, that is not proof the sentence is correct.
7. **Keep going.** The tutor selects follow-ups from a prepared set, so long
   conversations eventually run out of new questions.
### Settings worth knowing
 
- **Full grammar check after sending** (sidebar checkbox, on by default): untick
  it for faster turns with quick feedback only.
- **Clear draft** empties the message box.
- Level and scenario apply to **new** sessions, not the open one.
### Coming back later
 
Sessions are saved automatically in `data/practice.sqlite3`. Choose one under
**Your sessions** in the sidebar and click **Open session**. Refreshing the page
restores saved turns. Drafts and unsaved replies live in memory only and are lost
on refresh.
 
If saving a reply fails, the reply stays visible; click **Retry saving reply**
rather than sending again.
 
---
 
## Part 7: Daily use
 
**Start:** open three terminals in the project folder and run:
 
```bash
bash tools/ollama.sh serve
bash tools/checker.sh
uv run --locked streamlit run app.py
```
 
**Stop:** press `Ctrl+C` in each terminal. Your sessions remain saved.
 
**Update the code:**
 
```bash
git pull
uv sync --locked
```
 
After changing grammar or worker code yourself, **restart Streamlit**. A browser
refresh alone can leave an old worker running.
 
---
 
## Part 8: Run the tests (optional)
 
```bash
uv run --locked pytest -q                      # unit and app tests, no services needed
uv run --locked ruff check . && uv run --locked ruff format --check .
uv run --locked python tools/acceptance.py     # needs Ollama, both models, LanguageTool
```
 
Most tests use mocks, so `pytest` runs without Ollama or LanguageTool.
 
---

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
