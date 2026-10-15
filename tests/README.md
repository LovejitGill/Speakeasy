# Development tests

Run these commands from the repository root with the project environment installed.

## Automated checks

```bash
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The test suite includes unit and UI tests. Real T5 model tests are skipped unless
`SPEAKWELL_REAL_T5_TEST=1` is set and the model weights are available locally.

## Optional local-service smoke test

```bash
uv run --locked python tools/acceptance.py
```

This checks model-selected conversation replies through Ollama/Qwen, quick grammar
feedback, and full T5/ERRANT grammar feedback. It requires a running Ollama
service with the pinned Qwen 1.7B model, plus local T5 and spaCy model files.
It may report a blocked result when Ollama or the required model is unavailable.

## Latest recorded results

Run on 2026-10-15:

- `pytest -q`: 323 passed, 8 failed, 11 skipped.
- `ruff check .`: passed.
- `ruff format --check .`: 28 files already formatted.
- Import check for Streamlit, Whisper, ERRANT, spaCy, and `en_core_web_sm`: passed.
- `tests/test_manage.py`: 13 passed.
- `tools/acceptance.py`: blocked because Ollama was unavailable. Quick feedback
  and both full grammar smoke cases returned offered results.

The eight test failures concern conversation clarification routing. “What do you
mean?” can be handled as a WordNet lookup for “you” instead of a request to
explain the tutor's question. See the current limitations in the project
[README](../README.md).

These results are a record of one development environment, not a guarantee of
model correction quality or microphone behavior on other devices.
