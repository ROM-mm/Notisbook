"""In-memory registry of long-running jobs with a replayable, live event log."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Literal

JobState = Literal["queued", "running", "succeeded", "failed"]
MAX_LOG_EVENTS = 10_000
MAX_JOBS = 100


@dataclass(frozen=True)
class JobEvent:
    phase: str
    line: str
    progress: float | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"phase": self.phase, "line": self.line}
        if self.progress is not None:
            data["progress"] = self.progress
        return data


@dataclass
class Job:
    id: str
    kind: str
    version: str
    state: JobState = "queued"
    error: str | None = None
    log: list[JobEvent] = field(default_factory=list)
    _cond: asyncio.Condition = field(default_factory=asyncio.Condition, repr=False)

    @property
    def finished(self) -> bool:
        return self.state in ("succeeded", "failed")

    def _has_news(self, index: int) -> bool:
        return index < len(self.log) or self.finished

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "version": self.version,
            "state": self.state,
            "error": self.error,
            "log": [event.as_dict() for event in self.log],
        }

    async def start(self) -> None:
        async with self._cond:
            self.state = "running"
            self._cond.notify_all()

    async def emit(self, phase: str, line: str, progress: float | None = None) -> None:
        async with self._cond:
            if len(self.log) < MAX_LOG_EVENTS:  # a runaway process must not exhaust memory
                self.log.append(JobEvent(phase, line, progress))
            self._cond.notify_all()

    async def finish(self, state: Literal["succeeded", "failed"], error: str | None = None) -> None:
        """Terminal transition; appends the closing `done` event the WS clients wait for."""
        async with self._cond:
            if self.finished:
                return
            self.state = state
            self.error = error
            self.log.append(JobEvent("done", state if error is None else f"{state}: {error}", 1.0))
            self._cond.notify_all()

    async def stream(self) -> AsyncIterator[JobEvent]:
        """Yield the accumulated log, then live events, ending after the terminal event."""
        index = 0
        while True:
            async with self._cond:
                await self._cond.wait_for(partial(self._has_news, index))
                batch = self.log[index:]
                done = self.finished
            for event in batch:
                yield event
            index += len(batch)
            if done:
                return


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self, kind: str, version: str) -> Job:
        self._evict()
        job = Job(uuid.uuid4().hex, kind, version)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _evict(self) -> None:
        for job_id in [j.id for j in self._jobs.values() if j.finished]:
            if len(self._jobs) < MAX_JOBS:
                break
            del self._jobs[job_id]
