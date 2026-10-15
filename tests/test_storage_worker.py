import asyncio
import threading
import time

import pytest

import grammar
import storage
import tutor
from errors import StorageError
from worker import Worker


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "practice.sqlite3"
    storage.initialize(path)
    session = storage.create_session("beginner", "introductions", path)
    return path, session


def turn(session, key="turn1"):
    return {
        "id": key,
        "session_id": session,
        "learner_text": "He work.",
        "tutor_reply": "What does he do?",
        "path": "authored",
        "quick": {},
    }


def wait_for(predicate):
    end = time.monotonic() + 4
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Worker did not finish")


def test_atomic_rollback_and_retry(db):
    path, session = db
    with storage.connection(path) as conn:
        conn.execute(
            "CREATE TRIGGER fail BEFORE INSERT ON jobs BEGIN SELECT RAISE(ABORT, 'failure'); END"
        )
    with pytest.raises(StorageError):
        storage.save_turn(turn(session), path=path)
    assert storage.history(session, path) == []
    with storage.connection(path) as conn:
        conn.execute("DROP TRIGGER fail")
    storage.save_turn(turn(session), path=path)
    storage.save_turn(turn(session), path=path)
    assert len(storage.history(session, path)) == 1
    with storage.connection(path) as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_exact_turn_and_stale_result(db):
    path, session = db
    storage.save_turn(turn(session), path=path)
    job = storage.claim(path)
    assert storage.claim(path) is None
    storage.save_turn(turn(session, "turn2"), path=path)
    assert not storage.finish(
        {**job, "learner_text": "wrong"}, {"state": "offered"}, path
    )
    storage.recover(path)
    replacement = storage.claim(path)
    assert not storage.finish(job, {"state": "offered"}, path)
    assert storage.finish(replacement, {"state": "withheld"}, path)
    rows = storage.history(session, path)
    assert rows[0]["grammar"]["state"] == "withheld"
    assert rows[1]["grammar"] is None


def test_duplicate_workers_execute_once(db):
    path, session = db
    storage.save_turn(turn(session), path=path)
    calls = []

    async def check(text):
        calls.append(text)
        await asyncio.sleep(0.15)
        return {"state": "withheld"}

    workers = [Worker(path, check) for _ in range(2)]
    try:
        for worker in workers:
            worker.start()
            worker.start()
        wait_for(lambda: storage.history(session, path)[0]["job_state"] == "done")
        assert calls == ["He work."]
    finally:
        for worker in workers:
            worker.close()


def test_cancellation_interrupts_inference(db):
    path, session = db
    storage.save_turn(turn(session), path=path)
    began, cancelled = threading.Event(), threading.Event()

    async def check(text):
        began.set()
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    worker = Worker(path, check)
    try:
        worker.start()
        assert began.wait(2)
        storage.cancel("turn1", path)
        assert cancelled.wait(2)
        assert storage.history(session, path)[0]["grammar"] is None
    finally:
        worker.close()


def test_restart_recovers_interrupted_job(db):
    path, session = db
    storage.save_turn(turn(session), path=path)
    old = storage.claim(path)

    async def check(text):
        return {"state": "withheld"}

    worker = Worker(path, check)
    try:
        worker.start()
        wait_for(lambda: storage.history(session, path)[0]["job_state"] == "done")
        assert not storage.finish(old, {"state": "offered"}, path)
    finally:
        worker.close()


def test_unsaved_reply_survives(db, monkeypatch):
    path, session = db

    async def reply(*args, **kwargs):
        return {"reply": "Hello.", "path": "authored"}

    async def quick(*args, **kwargs):
        return {"state": "withheld"}

    def fail(*args, **kwargs):
        raise StorageError()

    monkeypatch.setattr(tutor.conversation, "respond", reply)
    monkeypatch.setattr(tutor.grammar, "quick_check", quick)
    monkeypatch.setattr(storage, "save_turn", fail)
    result, saved = tutor.submit("Hello", storage.sessions(path)[0], path=path)
    assert not saved and result["tutor_reply"] == "Hello."
    assert storage.history(session, path) == []


def test_killed_process_recovery(db):
    import subprocess
    import sys

    path, session = db
    storage.save_turn(turn(session), path=path)
    code = """
import asyncio, sys, time
from worker import Worker
async def check(text):
    await asyncio.sleep(30)
    return {"state": "withheld"}
worker = Worker(sys.argv[1], check)
worker.start()
time.sleep(30)
"""
    process = subprocess.Popen([sys.executable, "-c", code, str(path)])
    try:
        wait_for(lambda: storage.history(session, path)[0]["job_state"] == "running")
    finally:
        process.kill()
        process.wait()

    async def check(text):
        return {"state": "withheld"}

    replacement = Worker(path, check)
    try:
        replacement.start()
        wait_for(lambda: storage.history(session, path)[0]["job_state"] == "done")
    finally:
        replacement.close()


def test_tutor_queues_original_turns_and_worker_stores_t5_edits(db, monkeypatch):
    path, session_id = db
    session = storage.sessions(path)[0]
    proposals = {
        "He work every day.": "He works every day.",
        "I go yesterday.": "I went yesterday.",
    }
    calls = []
    ui_thread = threading.get_ident()

    async def reply(*args, **kwargs):
        return {"reply": "Tell me more.", "path": "authored"}

    async def correct(text):
        calls.append((text, threading.get_ident()))
        return {"corrected_text": proposals[text]}

    monkeypatch.setattr(tutor.conversation, "respond", reply)
    monkeypatch.setattr(grammar.local, "correct", correct)
    submitted = [tutor.submit(text, session, path=path) for text in proposals]
    assert all(saved for _, saved in submitted)
    assert calls == []
    rows = storage.history(session_id, path)
    assert all(row["job_state"] == "pending" for row in rows)
    assert [row["id"] for row in rows] == [item[0]["id"] for item in submitted]

    worker = Worker(path)
    try:
        worker.start()
        wait_for(
            lambda: all(
                row["job_state"] == "done" for row in storage.history(session_id, path)
            )
        )
    finally:
        worker.close()
    assert [text for text, _ in calls] == list(proposals)
    assert all(thread != ui_thread for _, thread in calls)
    rows = storage.history(session_id, path)
    for row, (submitted_turn, _) in zip(rows, submitted, strict=True):
        original = submitted_turn["learner_text"]
        assert row["id"] == submitted_turn["id"]
        assert row["learner_text"] == original
        result = row["grammar"]
        assert result["corrected_text"] == proposals[original]
        assert result["proposal_provenance"] == "AI-generated"
        assert result["edits"][0]["provenance"] == "generic local"
        assert result["edits"][0]["explanation"]


def test_cancelled_late_result_cannot_replace_next_turn(db):
    path, session = db
    storage.save_turn(turn(session), path=path)
    began, discarded = threading.Event(), threading.Event()

    async def check(text):
        if text == "He work.":
            began.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                discarded.set()
                # Simulate an inference implementation that returns after cancellation.
                return {"state": "offered", "corrected_text": "Stale suggestion."}
        return {"state": "offered", "corrected_text": "She works."}

    worker = Worker(path, check)
    try:
        worker.start()
        assert began.wait(2)
        storage.cancel("turn1", path)
        storage.save_turn(
            {**turn(session, "turn2"), "learner_text": "She work."}, path=path
        )
        wait_for(lambda: storage.history(session, path)[1]["job_state"] == "done")
        assert discarded.is_set()
        first, second = storage.history(session, path)
        assert first["job_state"] == "cancelled"
        assert first["grammar"] is None
        assert second["grammar"]["corrected_text"] == "She works."
        assert [first["learner_text"], second["learner_text"]] == [
            "He work.",
            "She work.",
        ]
    finally:
        worker.close()


def test_stale_completion_cannot_overwrite_new_attempt(db):
    path, session = db
    storage.save_turn(turn(session), path=path)
    old_job = storage.claim(path)

    async def exercise():
        began, release = asyncio.Event(), asyncio.Event()

        async def check(text):
            began.set()
            await release.wait()
            return {"state": "offered", "corrected_text": "Old attempt."}

        execution = asyncio.create_task(Worker(path, check)._execute(old_job))
        await asyncio.wait_for(began.wait(), 2)
        # Invalidate the attempt while it is in flight, as crash recovery does.
        storage.recover(path)
        new_job = storage.claim(path)
        assert new_job["token"] != old_job["token"]
        await Worker(
            path,
            lambda text: asyncio.sleep(
                0, result={"state": "offered", "corrected_text": "New attempt."}
            ),
        )._execute(new_job)
        release.set()
        await asyncio.wait_for(execution, 2)

    asyncio.run(exercise())
    row = storage.history(session, path)[0]
    assert row["grammar"]["corrected_text"] == "New attempt."
    assert row["learner_text"] == "He work."


def test_cancel_wins_between_inference_completion_and_persistence(db, monkeypatch):
    path, session = db
    storage.save_turn(turn(session), path=path)
    job = storage.claim(path)
    finish = storage.finish
    writes = []

    def cancel_before_finish(job, result, path):
        storage.cancel(job["id"], path)
        writes.append(finish(job, result, path))

    async def check(text):
        return {"state": "offered", "corrected_text": "He works."}

    monkeypatch.setattr(storage, "finish", cancel_before_finish)
    asyncio.run(Worker(path, check)._execute(job))
    assert writes == [False]
    assert storage.history(session, path)[0]["grammar"] is None


def test_discarded_job_does_not_start_inference(db):
    from unittest.mock import AsyncMock

    path, session = db
    storage.save_turn(turn(session), path=path)
    job = storage.claim(path)
    storage.cancel(job["id"], path)
    check = AsyncMock()
    asyncio.run(Worker(path, check)._execute(job))
    check.assert_not_awaited()


def test_worker_model_unavailable_preserves_conversation_and_quick(db, monkeypatch):
    path, session_id = db
    monkeypatch.setenv("SPEAKWELL_GRAMMAR_MODEL", str(path.parent / "missing-model"))

    async def reply(*args, **kwargs):
        return {"reply": "What do you like?", "path": "authored"}

    monkeypatch.setattr(tutor.conversation, "respond", reply)
    result, saved = tutor.submit(
        "I like basketballing.", storage.sessions(path)[0], path=path
    )
    assert saved and result["quick"]["state"] == "offered"
    worker = Worker(path)
    try:
        worker.start()
        wait_for(lambda: storage.history(session_id, path)[0]["job_state"] == "done")
    finally:
        worker.close()
    row = storage.history(session_id, path)[0]
    assert row["grammar"]["state"] == "unavailable"
    assert "T5" in row["grammar"]["message"]
    assert row["learner_text"] == "I like basketballing."
    assert row["quick"] == result["quick"]
    assert row["tutor_reply"] == "What do you like?"


def test_worker_cancel_reaps_inference_process_and_continues(db, monkeypatch):
    import sys

    path, session = db
    marker = path.parent / "inference-started"
    storage.save_turn(turn(session), path=path)
    storage.save_turn(
        {**turn(session, "turn2"), "learner_text": "She work."}, path=path
    )
    spawn = asyncio.create_subprocess_exec
    children = []
    code = """
import json, pathlib, sys, time
text = json.load(sys.stdin)['text']
if text == 'He work.':
    pathlib.Path(sys.argv[1]).touch()
    time.sleep(30)
print(json.dumps({'corrected_text': 'She works.'}))
"""

    async def inference_child(*args, **kwargs):
        child = await spawn(sys.executable, "-c", code, str(marker), **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(
        grammar.local.asyncio, "create_subprocess_exec", inference_child
    )
    worker = Worker(path)
    try:
        worker.start()
        wait_for(marker.exists)
        storage.cancel("turn1", path)
        wait_for(lambda: storage.history(session, path)[1]["job_state"] == "done")
        assert len(children) == 2
        assert children[0].returncode is not None and children[0].returncode != 0
        assert children[1].returncode == 0
        rows = storage.history(session, path)
        assert rows[0]["grammar"] is None
        assert rows[1]["grammar"]["corrected_text"] == "She works."
    finally:
        worker.close()
