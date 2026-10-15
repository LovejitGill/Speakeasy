"""Reply and quick feedback overlap without extra threads or partial saves."""

import asyncio

import pytest

import local
import tutor
from errors import ServiceError


def test_independent_requests_overlap_and_save_once(monkeypatch):
    from unittest.mock import Mock

    ready = asyncio.Event()

    async def reply(*args, **kwargs):
        await asyncio.wait_for(ready.wait(), timeout=1)
        return {"reply": "Tell me more.", "path": "authored"}

    async def quick(text, **kwargs):
        ready.set()
        return {"state": "withheld"}

    monkeypatch.setattr(tutor.storage, "history", lambda *a: [])
    save = Mock()
    monkeypatch.setattr(tutor.storage, "save_turn", save)
    monkeypatch.setattr(tutor.conversation, "respond", reply)
    monkeypatch.setattr(tutor.grammar, "quick_check", quick)
    turn, saved = tutor.submit(
        "Hello", {"id": "test", "level": "beginner", "scenario": "daily activities"}
    )
    assert saved and turn["tutor_reply"] == "Tell me more."
    save.assert_called_once()


def test_failed_reply_cancels_quick_work_and_never_saves(monkeypatch):
    from unittest.mock import Mock

    started = asyncio.Event()
    cancelled = []

    async def reply(*args, **kwargs):
        await started.wait()
        raise RuntimeError("test failure")

    async def quick(text, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(tutor.storage, "history", lambda *a: [])
    save = Mock()
    monkeypatch.setattr(tutor.storage, "save_turn", save)
    monkeypatch.setattr(tutor.conversation, "respond", reply)
    monkeypatch.setattr(tutor.grammar, "quick_check", quick)
    with pytest.raises(ExceptionGroup):
        tutor.submit(
            "Hello", {"id": "test", "level": "beginner", "scenario": "daily activities"}
        )
    assert cancelled == [True]
    save.assert_not_called()


def test_full_grammar_toggle_only_controls_queued_job(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    path = tmp_path / "practice.sqlite3"
    tutor.storage.initialize(path)
    tutor.storage.create_session("beginner", "daily activities", path)
    session = tutor.storage.sessions(path)[0]
    monkeypatch.setattr(
        tutor.conversation,
        "respond",
        AsyncMock(return_value={"reply": "Tell me more.", "path": "authored"}),
    )
    full = AsyncMock(side_effect=AssertionError("Full checks belong in the worker"))
    monkeypatch.setattr(tutor.grammar, "full_check", full)
    for enabled in (False, True):
        result, saved = tutor.submit(
            "I like basketballing.", session, full_grammar=enabled, path=path
        )
        assert saved
        assert result["learner_text"] == "I like basketballing."
        assert result["quick"]["corrected_text"] == "I like playing basketball."
    rows = tutor.storage.history(session["id"], path)
    assert [row["job_state"] for row in rows] == [None, "pending"]
    full.assert_not_awaited()


def test_missing_ollama_preserves_reply_quick_feedback_and_original(
    tmp_path, monkeypatch
):
    path = tmp_path / "practice.sqlite3"
    tutor.storage.initialize(path)
    tutor.storage.create_session("beginner", "daily activities", path)
    session = tutor.storage.sessions(path)[0]

    async def unavailable(*args, **kwargs):
        raise ServiceError()

    monkeypatch.setattr(local, "request", unavailable)
    turn, saved = tutor.submit(
        "I enjoy to swim.", session, full_grammar=False, path=path
    )
    assert saved
    assert turn["path"] == "local_fallback"
    assert turn["tutor_reply"]
    assert turn["quick"]["corrected_text"] == "I enjoy swimming."
    row = tutor.storage.history(session["id"], path)[0]
    assert row["learner_text"] == "I enjoy to swim."
    assert row["job_state"] is None
