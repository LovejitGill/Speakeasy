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

    async def quick(*a):
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


def test_transcript_requires_review_then_send(page):
    app, path = page
    app.session_state.transcript = "He work."
    app.run()
    assert not app.exception
    assert app.text_area(key="draft").value == ""
    assert storage.history(storage.sessions(path)[0]["id"], path) == []
    app.text_area(key="transcript").input("He works.").run()
    button(app, "Use reviewed transcript as draft").click().run()
    assert not app.exception
    assert app.text_area(key="draft").value == "He works."
    assert storage.history(storage.sessions(path)[0]["id"], path) == []


def test_long_transcript_validation_preserves_draft(page):
    app, _path = page
    app.session_state.transcript = "x" * 1001
    app.run()
    button(app, "Use reviewed transcript as draft").click().run()
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


def test_failed_transcription_preserves_both_drafts(page, monkeypatch):
    from types import SimpleNamespace

    import streamlit as st

    import speech

    app, _path = page
    app.session_state.transcript = "Earlier editable transcript"
    app.text_area(key="draft").input("Typed draft").run()
    monkeypatch.setattr(
        st, "audio_input", lambda *a, **kw: SimpleNamespace(getvalue=lambda: b"audio")
    )

    def fail(*a):
        raise speech.SpeechServiceError("Local transcription failed. Please retry.")

    monkeypatch.setattr(speech, "transcribe", fail)
    app.run()
    button(app, "Transcribe recording").click().run()
    assert not app.exception and app.error
    assert app.text_area(key="draft").value == "Typed draft"
    assert app.text_area(key="transcript").value == "Earlier editable transcript"


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
