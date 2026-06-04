"""Subprocess job runner with live Server-Sent-Events streaming.

Each run launches the tool's existing CLI as a child process (the same proven
script the launcher uses), pumps its combined stdout/stderr line-by-line into an
in-memory buffer + a per-subscriber queue, and exposes an async SSE generator the
browser consumes via EventSource.

Design notes:
- stdin is DEVNULL so a tool that falls back to input() (youtube, the API-key
  prompt) fails fast with EOF instead of hanging a request forever.
- The interpreter is sys.executable, i.e. the same venv running the web app, so
  the child inherits the suite's installed signalyser_core.
- Output is captured AND kept, so a browser that connects late (or reconnects)
  still replays the full transcript.
"""
from __future__ import annotations

import os
import sys
import uuid
import queue
import threading
import subprocess
from dataclasses import dataclass, field

from signalyser_core.io import SUITE_ROOT
from .config import Tool

_SENTINEL = object()  # marks end-of-stream on a subscriber queue


@dataclass
class Job:
    id: str
    tool_key: str
    tool_label: str
    argv: list[str]
    status: str = "running"           # "running" | "done" | "error"
    returncode: int | None = None
    lines: list[str] = field(default_factory=list)
    _subscribers: list[queue.Queue] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    proc: subprocess.Popen | None = None

    def _emit(self, line: str) -> None:
        with self._lock:
            self.lines.append(line)
            for q in self._subscribers:
                q.put(line)

    def _finish(self, status: str, returncode: int | None) -> None:
        with self._lock:
            self.status = status
            self.returncode = returncode
            for q in self._subscribers:
                q.put(_SENTINEL)

    def subscribe(self) -> queue.Queue:
        """Register a queue that gets the backlog immediately, then live lines."""
        q: queue.Queue = queue.Queue()
        with self._lock:
            for line in self.lines:
                q.put(line)
            if self.status == "running":
                self._subscribers.append(q)
            else:
                q.put(_SENTINEL)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)


class JobManager:
    """Owns running/finished jobs for the process lifetime."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, tool: Tool, tool_args: list[str]) -> Job:
        job_id = uuid.uuid4().hex[:12]
        argv = [sys.executable, str(tool.script_path), *tool_args]
        job = Job(id=job_id, tool_key=tool.key, tool_label=tool.label, argv=argv)
        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        return job

    def _run(self, job: Job) -> None:
        env = dict(os.environ)
        env.setdefault("PYTHONUNBUFFERED", "1")
        try:
            proc = subprocess.Popen(
                job.argv,
                cwd=str(SUITE_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
        except OSError as e:
            job._emit(f"[runner] failed to launch tool: {e}")
            job._finish("error", None)
            return

        job.proc = proc
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                job._emit(line.rstrip("\n"))
            proc.wait()
        except Exception as e:  # noqa: BLE001 - surface any pump failure to the UI
            job._emit(f"[runner] error while streaming: {e}")
            job._finish("error", proc.returncode)
            return

        status = "done" if proc.returncode == 0 else "error"
        job._finish(status, proc.returncode)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job and job.proc and job.status == "running":
            job.proc.terminate()
            return True
        return False

    def sse(self, job_id: str):
        """Yield SSE-formatted events for a job until it finishes.

        Event stream:
          data: <output line>\n\n      (one per line, repeated)
          event: done\ndata: <rc>\n\n  (final, then the stream closes)
        """
        job = self._jobs.get(job_id)
        if job is None:
            yield "event: error\ndata: unknown job\n\n"
            return
        q = job.subscribe()
        try:
            while True:
                item = q.get()
                if item is _SENTINEL:
                    break
                # Escape newlines defensively (shouldn't occur — we split on them).
                for chunk in str(item).split("\n"):
                    yield f"data: {chunk}\n\n"
            yield f"event: done\ndata: {job.returncode}\n\n"
        finally:
            job.unsubscribe(q)


# Module-level singleton the app shares.
manager = JobManager()
