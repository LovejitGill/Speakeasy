import asyncio
import threading
import time

import pytest

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

    async def quick(*args):
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
