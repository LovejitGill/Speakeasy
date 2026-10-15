"""One worker per database, independent of Streamlit, with crash recovery."""

import asyncio
import fcntl
import threading
from pathlib import Path

import grammar
import storage
from errors import StorageError


class Worker:
    def __init__(self, path=storage.DEFAULT_PATH, check=grammar.full_check):
        self.path = str(Path(path).resolve())
        self.check = check
        self.stop = threading.Event()
        self.thread = None
        self.guard = threading.Lock()

    def start(self):
        with self.guard:
            if self.thread and self.thread.is_alive():
                return
            self.stop.clear()
            self.thread = threading.Thread(
                target=self._run, daemon=True, name="grammar"
            )
            self.thread.start()

    async def _execute(self, job):
        if self.stop.is_set() or not storage.is_running(job, self.path):
            return
        task = asyncio.create_task(self.check(job["learner_text"]))
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.1)
                if self.stop.is_set() or not storage.is_running(job, self.path):
                    return
            try:
                result = task.result()
            except Exception:  # noqa: BLE001 -- preserve jobs and suppress private diagnostics
                result = dict(grammar.UNAVAILABLE)
            if self.stop.is_set():
                return
            # finish atomically checks this attempt's token and immutable turn text.
            # Cancellation/recovery can win even after inference has completed.
            storage.finish(job, result, self.path)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def _run(self):
        # OS lock remains held for the worker lifetime, including inference.
        # No leases can expire while a paused worker is still doing the same job.
        try:
            with open(self.path + ".worker.lock", "a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return
                storage.recover(self.path)
                while not self.stop.is_set():
                    try:
                        job = storage.claim(self.path)
                        if job:
                            asyncio.run(self._execute(job))
                        else:
                            self.stop.wait(0.3)
                    except StorageError:
                        # Release the lock before a replacement worker recovers.
                        return
        except OSError:
            return

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
