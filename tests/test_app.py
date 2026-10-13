from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

import conversation
import grammar
import storage
import worker
from errors import StorageError


@pytest.fixture
def page(tmp_path, monkeypatch):
    path = tmp_path / "app.sqlite3"
    monkeypatch.setenv("SPEAKWELL_DB_PATH", str(path))
    monkeypatch.setattr(worker, "Worker", lambda *a: Mock())

    async def reply(*a, **kw):
        return {"reply": "What would you like to add?", "path": "authored"}

    async def quick(*a, **kwargs):
        return {"state": "withheld", "message": "No supported correction found."}

    monkeypatch.setattr(conversation, "respond", reply)
    monkeypatch.setattr(grammar, "quick_check", quick)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    button(app, "Start new session").click().run()
    assert not app.exception
    return app, path


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_send_restore_and_separate_feedback(page):
    app, path = page
    app.text_area(key="draft").input("He work.").run()
    button(app, "Send").click().run()
    assert not app.exception
    session = storage.sessions(path)[0]
    rows = storage.history(session["id"], path)
    assert len(rows) == 1 and rows[0]["job_state"] == "pending"
    assert app.text_area(key="draft").value == ""
    fresh = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    fresh.query_params["session"] = session["id"]
    fresh.run()
    assert not fresh.exception
    assert any(item.value == "He work." for item in fresh.text)
    assert any(item.value == "1 completed turns" for item in fresh.caption)


def test_unsaved_reply_and_retry(page, monkeypatch):
    app, path = page
    save = storage.save_turn

    def fail(*a, **kw):
        raise StorageError()

    monkeypatch.setattr(storage, "save_turn", fail)
    app.text_area(key="draft").input("Hello").run()
    button(app, "Send").click().run()
    assert not app.exception
    assert any("NOT saved" in item.value for item in app.warning)
    assert any("What would" in item.value for item in app.text)
    assert app.session_state.draft == "Hello"
    assert button(app, "Start new session").disabled
    monkeypatch.setattr(storage, "save_turn", save)
    button(app, "Retry saving reply").click().run()
    assert not app.exception
    assert len(storage.history(storage.sessions(path)[0]["id"], path)) == 1


def mock_recording(monkeypatch, transcript="He work."):
    from types import SimpleNamespace

    import streamlit as st

    import speech

    recordings = {"audio_0": b"audio"}
    monkeypatch.setattr(
        st,
        "audio_input",
        lambda *a, **kw: (
            SimpleNamespace(getvalue=lambda: recordings[kw["key"]])
            if kw["key"] in recordings
            else None
        ),
    )
    transcribe = Mock(return_value=transcript)
    monkeypatch.setattr(speech, "transcribe", transcribe)
    return recordings, transcribe


def test_transcript_requires_review_then_send(page, monkeypatch):
    app, path = page
    _, transcribe = mock_recording(monkeypatch)
    app.run()
    assert not app.exception
    assert len(app.text_area) == 1
    assert all(item.label != "Record a message" for item in app.expander)
    assert app.text_area(key="draft").value == "He work."
    assert storage.history(storage.sessions(path)[0]["id"], path) == []
    app.text_area(key="draft").input("He works.").run()
    app.run()
    assert app.text_area(key="draft").value == "He works."
    transcribe.assert_called_once_with(b"audio")
    button(app, "Send").click().run()
    assert not app.exception
    rows = storage.history(storage.sessions(path)[0]["id"], path)
    assert len(rows) == 1
    assert app.text_area(key="draft").value == ""
    transcribe.assert_called_once()


def test_record_again_preserves_draft_until_new_transcript(page, monkeypatch):
    app, path = page
    recordings, transcribe = mock_recording(monkeypatch)
    app.run()
    button(app, "Record again").click().run()
    assert app.text_area(key="draft").value == "He work."
    transcribe.return_value = "I like walking."
    recordings["audio_1"] = b"second audio"
    app.run()
    assert not app.exception
    assert app.text_area(key="draft").value == "I like walking."
    assert transcribe.call_count == 2
    assert storage.history(storage.sessions(path)[0]["id"], path) == []


def test_long_transcript_validation_preserves_draft(page, monkeypatch):
    app, _path = page
    mock_recording(monkeypatch, "x" * 1001)
    app.run()
    button(app, "Send").click().run()
    assert not app.exception and app.error
    assert len(app.text_area(key="draft").value) == 1001


def test_learner_content_not_rendered_as_html_or_markdown(page):
    app, _path = page
    text = "<script>alert(1)</script> ![tracker](https://example.com/private)"
    app.text_area(key="draft").input(text).run()
    button(app, "Send").click().run()
    assert any(item.value == text for item in app.text)
    assert all(text not in item.value for item in app.markdown)
    assert all(text not in str(item.proto) for item in app.get("html"))


def test_failed_transcription_preserves_draft_and_retries_explicitly(page, monkeypatch):
    import speech

    app, _path = page
    app.text_area(key="draft").input("Typed draft").run()
    _, transcribe = mock_recording(monkeypatch)
    transcribe.side_effect = speech.SpeechServiceError(
        "Local transcription failed. Please retry."
    )
    app.run()
    app.run()
    assert not app.exception and app.error
    assert app.text_area(key="draft").value == "Typed draft"
    transcribe.assert_called_once()
    transcribe.side_effect = None
    button(app, "Retry transcription").click().run()
    assert not app.exception and not app.error
    assert app.text_area(key="draft").value == "He work."
    assert transcribe.call_count == 2


def test_storage_outage_still_shows_unsaved_reply(page, monkeypatch):
    app, _path = page

    def fail(*a, **kw):
        raise StorageError()

    monkeypatch.setattr(storage, "save_turn", fail)
    app.text_area(key="draft").input("Hello").run()
    button(app, "Send").click().run()
    monkeypatch.setattr(storage, "initialize", fail)
    app.run()
    assert not app.exception
    assert any("NOT saved" in item.value for item in app.warning)
    assert any("What would" in item.value for item in app.text)
    assert app.text_area(key="draft").value == "Hello"


def test_transcript_survives_rerun_when_spinner_closes(page, monkeypatch):
    from contextlib import contextmanager

    import streamlit as st

    app, path = page
    _, transcribe = mock_recording(monkeypatch)

    @contextmanager
    def interrupted_spinner(text, **kwargs):
        yield
        if text == "Transcribing locally…":
            st.rerun()

    monkeypatch.setattr(st, "spinner", interrupted_spinner)
    app.run()
    assert not app.exception
    assert app.text_area(key="draft").value == "He work."
    transcribe.assert_called_once()
    assert storage.history(storage.sessions(path)[0]["id"], path) == []


def test_feedback_layout_exposes_correction_and_explanation(page, monkeypatch):
    app, _ = page

    async def quick(text, **kwargs):
        return {
            "state": "offered",
            "corrected_text": "She can sing.",
            "explanation": "After can, use the basic verb form.",
        }

    monkeypatch.setattr(grammar, "quick_check", quick)
    app.text_area(key="draft").input("She can sings.").run()
    button(app, "Send").click().run()
    assert not app.exception
    panel = next(
        e for e in app.expander if e.label == "Quick feedback · Suggested edit"
    )
    assert panel.proto.expanded
    assert any(t.value == "She can sing." for t in panel.text)
    assert any(c.value == "WHY THIS CHANGE" for c in panel.caption)
    assert any(t.value == "She can sings." for t in app.text)


def test_session_layout_starts_with_only_opener(page):
    app, _ = page
    assert app.title[0].value == "Beginner - Daily Activities"
    assert any("SpeakEasy" in str(item.proto) for item in app.sidebar.get("html"))
    assert [item.value for item in app.text] == [
        conversation.OPENERS["daily activities"]
    ]
    assert any(item.value == "Record your response:" for item in app.subheader)
    assert not any(item.label == "Conversation History" for item in app.expander)


def test_session_layout_latest_first_older_below_composer(page):
    app, path = page
    sid = storage.sessions(path)[0]["id"]
    for index in range(3):
        storage.save_turn(
            {
                "id": f"layout-{index}",
                "session_id": sid,
                "learner_text": f"Message {index}",
                "tutor_reply": f"Reply {index}",
                "path": "authored",
                "quick": {"state": "withheld"},
            },
            grammar=False,
            path=path,
        )
    app.run()
    assert not app.exception
    assert [item.value for item in app.text] == [
        "Message 2",
        "Reply 2",
        "Message 1",
        "Reply 1",
        "Message 0",
        "Reply 0",
    ]
    older = next(e for e in app.expander if e.label == "Conversation History")
    assert not older.proto.expanded
    assert [t.value for t in older.text] == [
        "Message 1",
        "Reply 1",
        "Message 0",
        "Reply 0",
    ]
    nodes = list(app.main)
    composer_index = next(
        i
        for i, n in enumerate(nodes)
        if getattr(n, "value", None) == "Record your response:"
    )
    history_index = next(
        i
        for i, n in enumerate(nodes)
        if getattr(n, "label", None) == "Conversation History"
    )
    assert composer_index < history_index


def test_session_layout_unsaved_reply_stays_above_saved_history(page):
    app, path = page
    sid = storage.sessions(path)[0]["id"]
    turn = {
        "id": "saved-layout",
        "session_id": sid,
        "learner_text": "Earlier message",
        "tutor_reply": "Earlier reply",
        "path": "authored",
        "quick": {"state": "withheld"},
    }
    storage.save_turn(turn, grammar=False, path=path)
    app.session_state.unsaved = {
        **turn,
        "id": "unsaved-layout",
        "learner_text": "Newest message",
        "tutor_reply": "Newest reply",
        "full_grammar": False,
    }
    app.run()
    assert not app.exception
    assert [t.value for t in app.text] == [
        "Newest message",
        "Newest reply",
        "Earlier message",
        "Earlier reply",
    ]
    assert any("NOT saved" in warning.value for warning in app.warning)
    assert button(app, "Retry saving reply")
    assert app.text_area(key="draft").disabled


def test_pointers_belong_to_learner_and_reply_shares_composer(page):
    app, path = page
    sid = storage.sessions(path)[0]["id"]
    storage.save_turn(
        {
            "id": "pointers-layout",
            "session_id": sid,
            "learner_text": "She can sings.",
            "tutor_reply": "Tell me more.",
            "path": "authored",
            "quick": {
                "state": "offered",
                "corrected_text": "She can sing.",
                "explanation": "Say She can sing.",
            },
        },
        grammar=False,
        path=path,
    )
    app.run()
    assert not app.exception
    learner = app.chat_message[0]
    assert any(c.value == "Pointers:" for c in learner.caption)
    assert any(t.value == "She can sing." for t in learner.text)
    assert not any(t.value == "Tell me more." for t in learner.text)
    composer = next(n for n in app.main if getattr(n, "key", None) == "composer")
    assert any(t.value == "Tell me more." for t in composer.text)
    assert any(h.value == "Record your response:" for h in composer.subheader)
    assert [t.value for t in composer.text] == ["Tell me more."]


def test_send_accepts_pending_text_without_prior_rerun(page):
    app, path = page
    assert not button(app, "Send").disabled
    app.text_area(key="draft").input("A freshly typed message.")
    button(app, "Send").click().run()
    assert not app.exception
    rows = storage.history(storage.sessions(path)[0]["id"], path)
    assert len(rows) == 1
    assert rows[0]["learner_text"] == "A freshly typed message."


def test_enabled_send_still_rejects_empty_input(page):
    app, path = page
    button(app, "Send").click().run()
    assert not app.exception and app.error
    assert storage.history(storage.sessions(path)[0]["id"], path) == []


@pytest.mark.parametrize("state", ["withheld", "unavailable"])
def test_quick_feedback_encourages_only_completed_checks(page, monkeypatch, state):
    app, _ = page

    async def quick(text, **kwargs):
        return {
            "state": state,
            "message": "No supported correction found. This does not mean the message is error-free."
            if state == "withheld"
            else "Grammar feedback could not finish.",
        }

    monkeypatch.setattr(grammar, "quick_check", quick)
    app.text_area(key="draft").input("I like books.")
    button(app, "Send").click().run()
    assert not app.exception
    panel = next(e for e in app.expander if e.label.startswith("Quick feedback"))
    if state == "withheld":
        assert "Nice effort! No supported corrections found." in panel.label
        assert any("does not mean" in c.value for c in panel.caption)
    else:
        assert "Unavailable" in panel.label
        assert "Nice effort" not in panel.label


def test_spelling_feedback_is_optional_and_keeps_saved_original(page, monkeypatch):
    app, path = page

    async def quick(text, **kwargs):
        assert kwargs["spelling"] is True
        return {
            "state": "spelling",
            "message": "Review possible spellings.",
            "spelling": [{"word": "baskteball", "alternatives": ["basketball"]}],
        }

    monkeypatch.setattr(grammar, "quick_check", quick)
    app.text_area(key="draft").input("I like baskteball.")
    button(app, "Send").click().run()
    assert not app.exception
    panel = next(
        e for e in app.expander if e.label == "Quick feedback · Spelling to review"
    )
    assert panel.proto.expanded
    assert any(t.value == "Did you mean: basketball?" for t in panel.text)
    rows = storage.history(storage.sessions(path)[0]["id"], path)
    assert rows[0]["learner_text"] == "I like baskteball."


@pytest.mark.parametrize("edit", [False, True])
def test_recorded_draft_spelling_enabled_only_after_edit(page, monkeypatch, edit):
    app, _ = page
    mock_recording(monkeypatch, "I like books.")
    flags = []

    async def quick(text, **kwargs):
        flags.append(kwargs["spelling"])
        return {"state": "withheld"}

    monkeypatch.setattr(grammar, "quick_check", quick)
    app.run()
    if edit:
        app.text_area(key="draft").input("I like boooks.")
    button(app, "Send").click().run()
    assert not app.exception
    assert flags == [edit]


def test_confirm_spelling_name_is_runtime_only_and_preserves_text(page, monkeypatch):
    app, path = page
    seen = []

    async def quick(text, **kwargs):
        seen.append(kwargs["names"])
        return {
            "state": "spelling",
            "spelling": [{"word": "Zorvania", "alternatives": ["Romania"]}],
        }

    monkeypatch.setattr(grammar, "quick_check", quick)
    app.text_area(key="draft").input("I visited Zorvania.")
    button(app, "Send").click().run()
    assert any(t.value == "Did you mean: Romania?" for t in app.text)
    button(app, "This is a name").click().run()
    assert not app.exception
    assert app.session_state["spelling_names"] == {"zorvania"}
    assert not any(t.value == "Check this word: Zorvania" for t in app.text)
    app.text_area(key="draft").input("Zorvania is beautiful.")
    button(app, "Send").click().run()
    assert seen[-1] == {"zorvania"}
    rows = storage.history(storage.sessions(path)[0]["id"], path)
    assert rows[0]["learner_text"] == "I visited Zorvania."
    fresh = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    fresh.query_params["session"] = rows[0]["session_id"]
    fresh.run()
    assert "spelling_names" not in fresh.session_state


def test_missing_auxiliary_choices_display_without_changing_message(page, monkeypatch):
    app, path = page

    async def quick(text, **kwargs):
        return {
            "state": "suggestions",
            "message": "Choose the tense that matches what you mean.",
            "grammar_suggestions": [
                {
                    "original": "I playing",
                    "choices": ["Present: I am playing", "Past: I was playing"],
                }
            ],
        }

    monkeypatch.setattr(grammar, "quick_check", quick)
    app.text_area(key="draft").input("I playing basketball.")
    button(app, "Send").click().run()
    assert not app.exception
    assert any(t.value == "Present: I am playing" for t in app.text)
    assert any(t.value == "Past: I was playing" for t in app.text)
    panel = next(e for e in app.expander if "Choose the intended tense" in e.label)
    assert panel.proto.expanded
    rows = storage.history(storage.sessions(path)[0]["id"], path)
    assert rows[0]["learner_text"] == "I playing basketball."
