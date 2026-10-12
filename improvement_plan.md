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

## Interface refresh

- Added a dark theme, green action accent, grouped sidebar controls, onboarding
  panel, session overview, and a distinct recording/message composer.
- CSS is local; authored presentation markup stays separate from learner/model
  text. Existing recording review, save recovery, and grammar controls remain.
- All 155 tests and lint/format checks passed after the UI changes.
- Rendered the welcome and conversation screens in isolated headless Chrome at
  desktop and 390px mobile widths. Reviewed screenshots and confirmed no page
  horizontal overflow; production sessions were untouched.

## Remaining work

- Extend question coverage only where new conversation examples justify it.
- Improve explicit topic switching and explanations for follow-up questions.
- General questions and complex statements intentionally have limited coverage.
  Grammar abstains on unsupported/ambiguous changes; no correctness guarantee.
- Drafts/unsaved replies are memory-only and cannot survive browser refresh.
- Worker locking currently supports macOS/Linux. CPU model loading can exceed
  the small conversation/quick-check budgets; fallbacks remain explicit.

Next improvement: review topic switches and longer conversations that exhaust
prepared follow-ups. This is a feature checkpoint; broader quality or
production-readiness claims are not established.

### Direct recording flow
- Visible recorder automatically transcribes into the single editable message box.
  Send remains explicit; Record again preserves the draft until transcription succeeds.
- Failed transcription preserves text and offers an explicit retry; reruns do not
  reprocess the recording or overwrite edits. Fresh manual microphone verification
  of this updated flow remains pending.
- Validation: all 156 tests, Ruff lint/format, and diff whitespace checks passed.

### Transcript handoff fix
- Preserve a completed transcript before spinner cleanup can yield to a rerun,
  then apply it to the editable message box on the next render.
- An interruption regression test reproduced the empty-box failure before the fix.
  All 157 tests and lint/format checks pass.
- Isolated Chrome recorder with an injected speech sample and real local Whisper
  populated the textbox, retained the transcript across history refresh ticks, and
  did not submit a turn. Physical microphone retest remains pending.

### Short answers and clarification
- One authored question-guide table in the existing conversation engine supplies
  relevant next questions and plain-language explanations. No new dependency,
  service, stored state, or model change.
- Clarification and uncertain-answer help retain the underlying recent question.
  Unknown questions, expired context, ambiguous fragments, and person/negation
  boundaries remain conservative. Short answers do not create recall facts.
- All 189 tests and lint/format checks pass, including 32 new regression cases.
  A 12-turn synthetic review passed with live local model selection and authored
  continuation/clarification responses; learner sessions were not modified.
- Supported multi-step reading, task, and food conversations progressed without
  repeated closing replies in this review. Uncovered questions and longer chains
  can still reach generic fallbacks; this is not a general conversation score.

### Broader review with fresh examples
- Reviewed 25 synthetic turns across gardening, topic changes, person corrections,
  and food orders; no learner sessions were read or changed.
- Fixed stale hobby recall after “Not me, my brother.” A narrow explicit person
  correction now withholds ambiguous prior name/hobby facts, without assigning
  them to the other person. Fresh explicit declarations restore recall normally.
- Remaining: longer conversations exhausted follow-ups and repeated closing text;
  explicit topic switches were generic; some generated questions lacked guides.
- Reviewed 10 grammar examples with local models and LanguageTool: quick checks
  offered 2 corrections and withheld 8; full checks offered 4 and withheld 6 after
  correcting the review process's Java/checker paths. No offered edit changed
  intended meaning in this sample. Abstention does not mean grammatical correctness.
- Four initial full checks were unavailable because this shell lacked Java and
  the supplemental checker path; only those four were retried against the existing
  installation. No dependencies or model choices changed.
- All 13 newly added tests passed; changed Python files passed lint/format checks.
  The existing full suite was deliberately not rerun. This small review does not
  establish general accuracy. Next: topic switches and exhausted follow-ups.

### Response time, feedback rules, and layout
- Reply selection and quick feedback now overlap on one event loop using a task
  group; failure cancels sibling work before persistence. No added threads or
  changes to model identities, service restrictions, or per-operation deadlines.
- Full checks skip the Java count-rule subprocess for structurally unrelated
  sentences. In one local before/after sample, a past-tense abstention took
  6.00 → 2.17 s and a quoted-sentence abstention 6.34 → 3.17 s. The count example
  remained about 5.7 s. These few observations are not a performance benchmark.
- Quick checks now support four additional verified local rule IDs for modal and
  auxiliary-do constructions, retaining exact evidence, unique edits, and context
  restrictions. All four new examples were offered by the real local checker.
- Feedback suggestions open visibly with separate sentence/explanation labels;
  abstentions remain compact, and queued/running statuses use readable labels.
- All 13 new tests passed, including request overlap/cancellation, rule boundaries,
  selective subprocess use, and the feedback layout. Only new tests ran; changed
  files passed lint/format checks. Desktop/mobile Chrome checks showed no horizontal
  overflow using synthetic content and a temporary database.
- Conversation selection still hit its 1.4 s fallback budget in the sampled run.
  Cold-model latency and model contention remain; no overall speed guarantee.

### Session-focused layout
- SpeakEasy branding and a level/scenario title replace the previous banner.
- Latest message/reply appear above Record your response. Earlier turns live in
  collapsed Convo below it, newest first; new sessions show only the opener.
- Three new layout tests pass, including unsaved reply visibility. Desktop/mobile
  Chrome checks passed without horizontal overflow. No full-suite rerun.

- Pointers now sit under the learner message. The latest tutor reply and recording
  controls share one composer section. New focused layout regression passed;
  grammar feedback still refreshes independently of the editable draft.
