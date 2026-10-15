"""SQLite transactions and immutable completed turns; no repository wrappers."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from .errors import StorageError

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "practice.sqlite3"
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, level TEXT NOT NULL, scenario TEXT NOT NULL,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS turns (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
 learner_text TEXT NOT NULL, tutor_reply TEXT NOT NULL,
 path TEXT NOT NULL, quick_json TEXT NOT NULL,
 created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS jobs (
 turn_id TEXT PRIMARY KEY REFERENCES turns(id),
 state TEXT NOT NULL CHECK(state IN ('pending','running','done','cancelled')),
 token TEXT, result_json TEXT
);
"""


@contextmanager
def connection(path=DEFAULT_PATH):
    conn = None
    try:
        conn = sqlite3.connect(path, timeout=3)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        with conn:
            yield conn
    except (sqlite3.Error, OSError) as exc:
        raise StorageError() from exc
    finally:
        if conn is not None:
            conn.close()


def initialize(path=DEFAULT_PATH):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with connection(path) as conn:
            conn.executescript(SCHEMA)
    except OSError as exc:
        raise StorageError() from exc


def create_session(level, scenario, path=DEFAULT_PATH):
    from .conversation import validate_settings

    validate_settings(level, scenario)
    session_id = str(uuid.uuid4())
    with connection(path) as conn:
        conn.execute(
            "INSERT INTO sessions(id,level,scenario) VALUES(?,?,?)",
            (session_id, level, scenario),
        )
    return session_id


def sessions(path=DEFAULT_PATH):
    with connection(path) as conn:
        return [
            dict(row)
            for row in conn.execute("SELECT * FROM sessions ORDER BY rowid DESC")
        ]


def history(session_id, path=DEFAULT_PATH):
    with connection(path) as conn:
        rows = conn.execute(
            """SELECT t.*, j.state AS job_state, j.result_json
            FROM turns t LEFT JOIN jobs j ON j.turn_id=t.id
            WHERE session_id=? ORDER BY t.rowid""",
            (session_id,),
        ).fetchall()
    return [
        {
            **dict(row),
            "quick": json.loads(row["quick_json"]),
            "grammar": json.loads(row["result_json"]) if row["result_json"] else None,
        }
        for row in rows
    ]


def save_turn(turn, *, grammar=True, path=DEFAULT_PATH):
    """Reply and optional job commit together. A stable ID makes retries idempotent."""
    with connection(path) as conn:
        old = conn.execute("SELECT * FROM turns WHERE id=?", (turn["id"],)).fetchone()
        if old:
            if any(
                old[key] != turn[key]
                for key in ("session_id", "learner_text", "tutor_reply", "path")
            ):
                raise StorageError()
            return
        conn.execute(
            """INSERT INTO turns(id,session_id,learner_text,tutor_reply,path,quick_json)
                     VALUES(?,?,?,?,?,?)""",
            (
                turn["id"],
                turn["session_id"],
                turn["learner_text"],
                turn["tutor_reply"],
                turn["path"],
                json.dumps(turn["quick"]),
            ),
        )
        if grammar:
            conn.execute(
                "INSERT INTO jobs(turn_id,state) VALUES(?,'pending')", (turn["id"],)
            )


def claim(path=DEFAULT_PATH):
    with connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""SELECT t.id, t.session_id, t.learner_text FROM jobs j
            JOIN turns t ON t.id=j.turn_id WHERE j.state='pending' ORDER BY t.rowid LIMIT 1""").fetchone()
        if row is None:
            return None
        token = str(uuid.uuid4())
        conn.execute(
            "UPDATE jobs SET state='running', token=? WHERE turn_id=?",
            (token, row["id"]),
        )
        return {**dict(row), "token": token}


def is_running(job, path=DEFAULT_PATH):
    with connection(path) as conn:
        return (
            conn.execute(
                "SELECT 1 FROM jobs WHERE turn_id=? AND token=? AND state='running'",
                (job["id"], job["token"]),
            ).fetchone()
            is not None
        )


def finish(job, result, path=DEFAULT_PATH):
    with connection(path) as conn:
        updated = conn.execute(
            """UPDATE jobs SET state='done', result_json=?
            WHERE turn_id=? AND token=? AND state='running'
            AND EXISTS (SELECT 1 FROM turns WHERE id=? AND session_id=? AND learner_text=?)""",
            (
                json.dumps(result),
                job["id"],
                job["token"],
                job["id"],
                job["session_id"],
                job["learner_text"],
            ),
        )
        return updated.rowcount == 1


def cancel(turn_id, path=DEFAULT_PATH):
    with connection(path) as conn:
        conn.execute(
            "UPDATE jobs SET state='cancelled', token=NULL WHERE turn_id=? AND state IN ('pending','running')",
            (turn_id,),
        )


def recover(path=DEFAULT_PATH):
    """Caller must own the worker's exclusive process lock."""
    with connection(path) as conn:
        conn.execute(
            "UPDATE jobs SET state='pending', token=NULL WHERE state='running'"
        )
