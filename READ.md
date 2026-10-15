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
  (local T5 proposals with ERRANT edit labels and generic local explanations).
  Suggestions can be wrong and are never applied automatically.
- **Saved sessions:** reopen past sessions from the sidebar; if saving fails, retry without regenerating the reply
- **Background checks:** single worker, cancellable, results tied to the original turn

## Not so Quick start

<details>
<summary>Full install and first-session walkthrough</summary>
 
A step-by-step guide to installing and using Speakeasy. About 20–40 minutes the
first time, mostly downloads. After that, starting a session takes under a minute.
 
Speakeasy runs these components on your computer:
 
| Piece | What it does | Port |
|---|---|---|
| Ollama | Runs the Qwen3 language models | 11434 |
| T5 and ERRANT | Propose corrections and describe edits (on demand) | none |
| Streamlit app | The web interface you use | 8501 |
| Whisper | Transcribes recordings (loads on demand, no server) | none |
 
Everything stays on your machine. You need internet only for the downloads in Parts 3 and 4.
 
---
 
## Part 1: Install the prerequisites
 
You need **uv**. Ollama is optional for model-selected conversation replies. Python is handled for you.
 
### macOS
 
```bash
# Homebrew (skip if you already have it): https://brew.sh
brew install uv
brew install --cask ollama      # or download from https://ollama.com
```
 
### Linux (Debian/Ubuntu shown)
 
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://ollama.com/install.sh | sh
```
 
Restart your terminal so `uv` is on your PATH.
 
### Check each tool
 
```bash
uv --version
ollama --version
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
 
Grammar setup needs no Ollama. Run `uv run --locked python tools/manage.py setup`
to download T5, Whisper, and WordNet data. The spaCy English model is installed
by `uv sync --locked`.

For model-selected conversation replies, use two terminals for this part.
 
**Terminal 1:** start Ollama and leave it running.
 
```bash
bash tools/ollama.sh serve
```
 
**Terminal 2:** download everything.
 
```bash
bash tools/ollama.sh pull qwen3:1.7b      # conversation model, about 1.4 GB
uv run --locked python tools/setup.py speech    # Whisper base.en, pinned revision
uv run --locked python tools/setup.py grammar   # pinned T5 grammar weights
uv run --locked python -c 'import errant, spacy; spacy.load("en_core_web_sm"); errant.load("en"); print("English grammar models ready")'
```
 
Expected output includes `Pinned Whisper base.en files downloaded.` and
`Pinned T5 grammar model files downloaded.` The spaCy English model is installed
by `uv sync --locked`
in Part 3; the final command confirms it loads locally.
 
Models land in `.models/` and `.tools/` inside the project (both are git-ignored).
You will not need internet again.
To force offline startup after installation, set `HF_HUB_OFFLINE=1`,
`TRANSFORMERS_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`, and `UV_OFFLINE=1`, then use
`uv run --offline --locked streamlit run app.py` in Part 5. Grammar inference sets
the Hugging Face offline flags in its child process as well.
 
---
 
## Part 5: Start everything
 
Use one terminal for the app. If using Ollama, keep its terminal from Part 4 open.
 
| Terminal | Command | Leave running |
|---|---|---|
| Optional | `bash tools/ollama.sh serve` | yes |
| App | `uv run --locked python tools/manage.py launch` | yes |
 
Keep a third terminal free for other commands, such as tests.
 
Streamlit prints a local URL, usually **http://127.0.0.1:8501**. Open it in your
browser.
 
### Quick health check (optional)
 
In any free terminal:
 
```bash
curl -s http://127.0.0.1:11434/api/tags | head -c 200     # lists your models
```
 
The command should print JSON. If it is empty or errors, Ollama is not running.
 
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
   - **Quick feedback** uses limited local phrase rules. No detected issue does
     not prove the sentence is correct.
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
 
**Start:** run the app in the project folder. Start Ollama separately only if you
want model-selected conversation replies:
 
```bash
uv run --locked python tools/manage.py launch
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
uv run --locked python tools/acceptance.py     # needs Ollama, Qwen 1.7B, cached T5/spaCy models
```
 
Most tests use mocks, so `pytest` runs without running services; ERRANT integration tests use the installed spaCy model.
 
---

</details>

## Troubleshooting

<details>
<summary>Expand..</summary>
 
| Symptom | Likely cause and fix |
|---|---|
| "Speech model missing. Run: uv run python tools/setup.py speech" | Whisper not downloaded. Run the `speech` setup command from Part 4 |
| Replies use prepared fallback questions | Optional Ollama is not running or the Qwen 1.7B digest does not match. Run `uv run --locked python tools/manage.py setup --with-ollama` and launch with `--with-ollama` |
| Feedback unavailable after a model update | The upstream model tag changed. Re-pull with `tools/ollama.sh pull ...`; see [models.md](models.md) |
| Port 11434 already in use | Another Ollama is running. Stop it (Part 1) or use that instance consistently |
| Full grammar check unavailable | See [troubleshooting.md](troubleshooting.md) |
| Microphone does nothing | Allow microphone access for `127.0.0.1` in your browser; check no other app is using the mic |
| "Record between 0.3 and 60 seconds of speech" | Recording was too short or too long |
| "I didn't catch clear speech" | Near-silent recording. Move closer to the mic and retry |
| Windows errors on startup | Not supported natively. Use WSL2 |
 
Other config and environment variables: see the table in the main
[README](../README.md#configuration).

</details>
 
