"""Reply and quick feedback overlap without extra threads or partial saves."""

import asyncio

import pytest

import tutor


def test_independent_requests_overlap_and_save_once(monkeypatch):
    from unittest.mock import Mock

    ready = asyncio.Event()

    async def reply(*args, **kwargs):
        await asyncio.wait_for(ready.wait(), timeout=1)
        return {"reply": "Tell me more.", "path": "authored"}

    async def quick(text):
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

    async def quick(text):
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
