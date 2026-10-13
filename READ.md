# 💬 Speakeasy

A local English-practice tutor. Type or record a message, review the transcript,
get a conversational reply, and see grammar suggestions. Models run on your
machine; sessions are stored in local SQLite.

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Local inference](https://img.shields.io/badge/Inference-local-287D3C)](#configuration)
[![MIT License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Jump to:** [Features](#features) · [Quickstart](#quickstart) · [Configuration](#configuration) · [Architecture](#architecture) · [Development](#development) · [Limitations](#limitations) · [Roadmap](#roadmap)

## Features

- **Practice:** 3 levels (beginner, intermediate, advanced) × 3 scenarios (daily activities, introductions, ordering food)
- **Voice input:** record, transcribe locally with Whisper, edit, then send. Nothing submits automatically.
- **Follow-ups:** prepared questions chosen by a local model, with short-term recall of names and hobbies
- **Grammar feedback:** instant rule-based suggestions, plus an optional full check
  (Qwen3 4B proposal verified by LanguageTool). Unsupported edits are withheld.
- **Saved sessions:** reopen past sessions from the sidebar; if saving fails, retry without regenerating the reply
- **Background checks:** single worker, cancellable, results tied to the original turn

## Quickstart

Getting started

A step-by-step guide to installing and using Speakeasy. About 20–40 minutes the first time, mostly downloads. After that, starting a session takes under a minute.

Speakeasy runs four things on your computer:

Piece	What it does	Port
Ollama	Runs the Qwen3 language models	11434
LanguageTool	Checks grammar	8081
Streamlit app	The web interface you use	8501
Whisper	Transcribes recordings (loads on demand, no server)	none

Everything stays on your machine. You need internet only for the downloads in Parts 3 and 4.

Part 1: Install the prerequisites

You need uv, Ollama, and Java 21. Python is handled for you.

macOS
bash
# Homebrew (skip if you already have it): https://brew.sh
brew install uv
brew install --cask ollama      # or download from https://ollama.com
brew install openjdk@21

Homebrew's Java is not on your PATH by default. Find it and set it for the terminal that launches LanguageTool and the app:

bash
# Apple Silicon
export SPEAKWELL_JAVA=/opt/homebrew/opt/openjdk@21/bin/java
# Intel Mac
export SPEAKWELL_JAVA=/usr/local/opt/openjdk@21/bin/java
Linux (Debian/Ubuntu shown)
bash
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://ollama.com/install.sh | sh
sudo apt install openjdk-21-jre-headless

Restart your terminal so uv is on your PATH.

Check each tool
bash
uv --version
ollama --version
java -version      # or: "$SPEAKWELL_JAVA" -version   (must report 21)
Stop any background Ollama

The installers above usually start Ollama automatically on port 11434. Speakeasy runs its own copy through tools/ollama.sh, which keeps models in the project folder. Two copies cannot share the port, and a background copy would not see the project's models, so stop it first:

macOS: quit Ollama from the menu bar icon
Linux: sudo systemctl disable --now ollama
Part 2: Get the code
bash
git clone https://github.com/LovejitGill/Speakeasy.git
cd Speakeasy

Run every later command from this Speakeasy folder.

Part 3: Install the Python dependencies
bash
uv sync --locked

The project needs Python 3.12.13 or newer, so on most machines uv first downloads it (internet required). It then creates a .venv folder and installs the exact package versions in uv.lock. --locked makes it fail rather than silently change versions.

Part 4: Download the models (one time)

You need two terminals for this part.

Terminal 1: start Ollama and leave it running.

bash
bash tools/ollama.sh serve

Terminal 2: download everything.

bash
bash tools/ollama.sh pull qwen3:1.7b      # conversation model, about 1.4 GB
bash tools/ollama.sh pull qwen3:4b        # full grammar model, about 2.5 GB
uv run --locked python tools/setup.py checker   # LanguageTool 6.6, checksum verified
uv run --locked python tools/setup.py speech    # Whisper base.en, pinned revision

Expected output ends with LanguageTool 6.6 verified and extracted. Java 21 is required. and Pinned Whisper base.en files downloaded.

Models land in .models/ and .tools/ inside the project (both are git-ignored). You will not need internet again.

If the checker download prints Checksum mismatch, delete .tools/LanguageTool-6.6.zip and rerun that command.

Part 5: Start everything

Use three terminals in the Speakeasy folder (Terminal 1 is already running Ollama from Part 4).

Terminal	Command	Leave running
1	bash tools/ollama.sh serve	yes
2	bash tools/checker.sh	yes
3	uv run --locked streamlit run app.py	yes

Keep a fourth terminal free for other commands, such as tests.

If you set SPEAKWELL_JAVA in Part 1, set it in both the checker terminal and the app terminal.

Streamlit prints a local URL, usually http://127.0.0.1:8501. Open it in your browser.

Quick health check (optional)

In any free terminal:

bash
curl -s http://127.0.0.1:11434/api/tags | head -c 200     # lists your models
curl -s http://127.0.0.1:8081/v2/languages | head -c 100  # LanguageTool answers

Both should print JSON. If one is empty or errors, that service is not running.

Part 6: Your first practice session
Choose settings in the sidebar: a Level (beginner, intermediate, advanced) and a Scenario (daily activities, introductions, ordering food).
Click Start new session. The tutor asks an opening question.
Answer by typing. Write in the Your message box (up to 1,000 characters) and click Send.
Or answer by voice.
Click the microphone under Record a message and allow microphone access when your browser asks.
Speak one or two sentences, then stop the recording.
Wait for the transcript to appear in the message box. Whisper runs on your CPU, so allow a few seconds.
Check and fix the transcript, then click Send. Nothing is submitted automatically.
Use Record again to redo it, or Retry transcription if it failed.
Read the reply. The tutor responds with a follow-up question.
Read your feedback under your message:
Quick feedback appears immediately: simple rule-based suggestions and optional "Did you mean" spelling alternatives. Click This is a name to stop a name being flagged (remembered until you close the browser session).
Full grammar check runs in the background after you send. It may take up to about a minute. Click Cancel grammar check to stop it. If no correction is shown, that is not proof the sentence is correct.
Keep going. The tutor selects follow-ups from a prepared set, so long conversations eventually run out of new questions.
Settings worth knowing
Full grammar check after sending (sidebar checkbox, on by default): untick it for faster turns with quick feedback only.
Clear draft empties the message box.
Level and scenario apply to new sessions, not the open one.
Coming back later

Sessions are saved automatically in data/practice.sqlite3. Choose one under Your sessions in the sidebar and click Open session. Refreshing the page restores saved turns. Drafts and unsaved replies live in memory only and are lost on refresh.

If saving a reply fails, the reply stays visible; click Retry saving reply rather than sending again.

Part 7: Daily use

Start: open three terminals in the project folder and run:

bash
bash tools/ollama.sh serve
bash tools/checker.sh
uv run --locked streamlit run app.py

Stop: press Ctrl+C in each terminal. Your sessions remain saved.

Update the code:

bash
git pull
uv sync --locked

After changing grammar or worker code yourself, restart Streamlit. A browser refresh alone can leave an old worker running.

Part 8: Run the tests (optional)
bash
uv run --locked pytest -q                      # unit and app tests, no services needed
uv run --locked ruff check . && uv run --locked ruff format --check .
uv run --locked python tools/acceptance.py     # needs Ollama, both models, LanguageTool

Most tests use mocks, so pytest runs without Ollama or LanguageTool.

Troubleshooting
Symptom	Likely cause and fix
"Speech model missing. Run: uv run python tools/setup.py speech"	Whisper not downloaded. Run the speech setup command from Part 4
Replies look generic or fall back to the same questions	Ollama is not running or the model digest does not match. Check tools/ollama.sh serve is up and both models were pulled with tools/ollama.sh
Feedback unavailable after a model update	The upstream model tag changed. Re-pull with tools/ollama.sh pull ...; see models.md
Port 11434 already in use	Another Ollama is running. Stop it (Part 1) or use that instance consistently
cd: .../.tools/LanguageTool-6.6: No such file or directory when starting the checker	LanguageTool is not installed yet. Run uv run --locked python tools/setup.py checker (Part 4)
java: command not found or LanguageTool will not start	Java 21 not installed or not on PATH. Set SPEAKWELL_JAVA
Quick feedback shows nothing right after startup	The first LanguageTool request after launch can be slow. Wait a few seconds and send again
Full grammar check unavailable	See troubleshooting.md
Microphone does nothing	Allow microphone access for 127.0.0.1 in your browser; check no other app is using the mic
"Record between 0.3 and 60 seconds of speech"	Recording was too short or too long
"I didn't catch clear speech"	Near-silent recording. Move closer to the mic and retry
Windows errors on startup	Not supported natively. Use WSL2
## Configuration

Set variables in the terminal that launches each service.

| Variable | Default | Purpose |
|---|---|---|
| `SPEAKWELL_DB_PATH` | `data/practice.sqlite3` | SQLite database |
| `SPEAKWELL_SPEECH_MODEL` | `.models/faster-whisper-base.en` | Local Whisper model folder |
| `SPEAKWELL_LT_DIR` | `.tools/LanguageTool-6.6` | LanguageTool install (set for app and launcher) |
| `SPEAKWELL_JAVA` | `.tools/java` if present, else `java` | Java executable (set for app and launcher) |
| `SPEAKWELL_OLLAMA` | `ollama` on PATH | Ollama executable used by the launcher |

The `SPEAKWELL_` prefix is kept from the project's predecessor,
[Speakwell](https://github.com/LovejitGill/Speakwell).

Services are fixed to localhost (Ollama `:11434`, LanguageTool `:8081`), with
proxies and redirects disabled. Pinned model digests and time budgets are in
[docs/models.md](docs/models.md).

## Architecture

```mermaid
flowchart TD
    UI["Streamlit: settings, recording, editable draft"]
    UI -->|"Recording stopped"| STT["Local Whisper base.en"]
    STT -->|"Transcript for review, never automatic submission"| UI
    UI -->|"Send"| TURN["Turn coordinator"]
    TURN --> CONV["Conversation planner + Qwen3 1.7B selector"]
    TURN --> QUICK["Quick LanguageTool check"]
    TURN -->|"Save reply and optional job atomically"| DB[("SQLite")]
    DB --> WORKER["Single grammar worker"]
    WORKER --> FULL["Qwen3 4B proposal + LanguageTool evidence"]
    FULL -->|"Result for original turn"| DB
    DB -->|"History and feedback"| UI
```

| Module | Responsibility |
|---|---|
| `app.py` | Page controls, recording, editable drafts, feedback display |
| `assets/style.css`, `.streamlit/config.toml` | Layout styling and color theme |
| `tutor.py` | Coordinate a reply, quick feedback, and saving |
| `conversation.py`, `context.py` | Select follow-ups; handle supported facts, people, and food constraints |
| `grammar.py` | Quick and full checks sharing evidence and explanation logic |
| `local.py`, `speech.py` | Bounded local HTTP requests; validated offline transcription |
| `storage.py`, `worker.py` | SQLite operations; recoverable grammar jobs |
| `rules/` | Custom LanguageTool rule for number/plural errors |

The model selects among prepared follow-ups rather than writing free text, which
limits invented facts but also flexibility. Context is capped at four exchanges
and 3,000 characters. Corrections never enter conversation history.

## Development

```bash
uv run --locked pytest -q
uv run --locked ruff check . && uv run --locked ruff format --check .
uv run --locked python tools/acceptance.py   # needs Ollama, both models, LanguageTool
```

After changing grammar or worker code, restart Streamlit; a browser refresh can
keep a stale worker. If feedback is unavailable, see
[docs/troubleshooting.md](docs/troubleshooting.md).

Keep changes focused, add behavioral tests for fixes, and preserve local-only
inference, explicit sending, and conservative correction validation.

## Limitations

- Follow-ups are prepared, so unsupported questions fall back and long chats can run out
- Word explanations cover only lend/borrow and teach/learn
- Grammar suggestions are conservative and can be wrong; full checks handle single-line messages only
- Drafts and unsaved replies are memory-only and lost on refresh
- Trusted local use: no accounts, recordings are not stored, English only, no spoken replies or pronunciation scoring

## Roadmap

- [ ] Explicit topic switching and longer follow-up coverage

Verification history and next steps: [improvement_plan.md](improvement_plan.md)

## License

MIT — see [LICENSE](LICENSE). Third-party models and libraries keep their own licenses.
