# Implementation status

- Baseline: destination `bb256dba80f8acf2cc9dd531f80dc0171ecf1481`, clean, with
  only LICENSE and a one-line README. Source reviewed at
  `7bc00883aac7b16b96f875bb85e4f57b136482c1`; source files left unchanged.
- Implemented: typed contextual practice, conservative recall/person policies,
  editable recording transcripts, SQLite session restore, visible unsaved replies,
  quick corrections, separate full checks, exact-turn job results, cancellation,
  duplicate prevention, transaction rollback, and interruption recovery.
- Simpler structure: one conversation planner, shared grammar evidence, direct
  SQLite functions, and one worker. No strategy chain, schema compatibility,
  evaluation archives, or generic service/repository framework.
- Intentional differences and local setup are documented in README.

## Verification

- Clean `uv sync --locked` succeeded, including Intel Mac-compatible ONNX Runtime.
- All 155 automated behavioral/security/failure checks and Streamlit AppTest
  passed. Most service tests use mocks; Ruff, compilation, and shell checks passed.
- Real Streamlit startup and HTTP health endpoint passed.
- Real LanguageTool quick correction passed after warm-up; cold quick checks can
  time out. The supplemental XML rule also passed against LanguageTool 6.6.
- Real local Whisper transcribed the public JFK recording; this confirms the
  pipeline, not transcription accuracy. The user subsequently confirmed all six
  browser/microphone steps passed: recording permission, playback, transcription,
  editing without automatic submission, explicit sending, and refresh restoration.
- Real Ollama identity checks and warm model-selected conversation passed.
  Full grammar withheld the first example and offered a correction for the
  second; the final two-example service smoke command exited successfully.
- Service checks used existing local Java/checker directories through environment
  variables; configure those paths or run setup for a fresh app launch.
- Qwen and Whisper model copies now live in the ignored model folder. Whisper
  loaded successfully from the default app path; physical microphone verification
  was user-performed, not browser automation.

## Conversation review

- Reviewed 24 synthetic turns across six conversations using local Ollama, covering
  introductions/recall, changed facts, short answers, food/person constraints,
  negation/topic changes, and reference questions. No learner sessions were modified.
- Found and fixed stale recall when a learner retracts a fact and asks about it in
  the same message. Current declarations now override previous facts; the update
  also remains usable on subsequent turns. Six regression cases were added.
- Stop/no-follow-up controls, missing-information fallback, and person separation
  held in these examples. This small review is not a general quality score.
- Short answers produced generic invitations and eventually repeated closing text.
  Topic changes and question clarification also need more useful supported replies.

## Remaining work

- Improve short-answer continuity and question clarification without guessing facts.
- Review broader conversation and grammar coverage with new examples.
- General questions and complex statements intentionally have limited coverage.
  Grammar abstains on unsupported/ambiguous changes; no correctness guarantee.
- Drafts/unsaved replies are memory-only and cannot survive browser refresh.
- Worker locking currently supports macOS/Linux. CPU model loading can exceed
  the small conversation/quick-check budgets; fallbacks remain explicit.

Next improvement: short-answer continuity and targeted question clarification,
with regression tests for relevance and avoiding repeated closing replies. Suitable for a feature checkpoint
once reviewed; broader quality or production-readiness claims are not established.
