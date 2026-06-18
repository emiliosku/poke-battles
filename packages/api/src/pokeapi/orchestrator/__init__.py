"""In-process orchestrator.

Schedules battles, runs them against a local Showdown server (or a container
in production), captures events, and updates ratings. Uses an asyncio queue
with a small worker pool to bound concurrent Showdown usage.

This is a single-process orchestrator suitable for dev and small deploys.
Phase 4 splits this into a separate worker service with Docker container pool.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BattleJob:
    id: str = field(default_factory=lambda: f"battle-{uuid.uuid4().hex[:8]}")
    format: str = "gen9randombattle"
    player1: str = ""
    player2: str = ""
    model1: str = ""
    model2: str = ""
    team1_paste: str | None = None
    team2_paste: str | None = None
    on_start: Callable[[BattleJob], Awaitable[None]] | None = None
    on_complete: Callable[[BattleJob, JobResult], Awaitable[None]] | None = None


@dataclass
class JobResult:
    job_id: str
    battle_id: str | None = None
    winner: str | None = None
    turns: int = 0
    duration_s: float = 0.0
    events: tuple | list = ()
    raw_log: str = ""


class Orchestrator:
    def __init__(self, *, max_concurrent: int = 4) -> None:
        self.queue: asyncio.Queue[BattleJob] = asyncio.Queue()
        self.results: dict[str, JobResult] = {}
        self.max_concurrent = max_concurrent
        self._workers: list[asyncio.Task[None]] = []
        self._running = False
        self._runner: Callable[[BattleJob], Awaitable[JobResult]] | None = None

    def set_runner(self, runner: Callable[[BattleJob], Awaitable[JobResult]]) -> None:
        self._runner = runner

    async def submit(self, job: BattleJob) -> str:
        await self.queue.put(job)
        return job.id

    async def get_result(self, job_id: str, timeout: float = 300.0) -> JobResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if job_id in self.results:
                return self.results[job_id]
            await asyncio.sleep(0.1)
        raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self.max_concurrent):
            self._workers.append(asyncio.create_task(self._worker_loop(i)))

    async def stop(self) -> None:
        self._running = False
        for w in self._workers:
            w.cancel()
        for w in self._workers:
            try:
                await w
            except (asyncio.CancelledError, Exception):
                pass
        self._workers.clear()

    async def _worker_loop(self, worker_id: int) -> None:
        logger.info("Orchestrator worker %d started", worker_id)
        while self._running:
            try:
                job = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            if self._runner is None:
                logger.warning("No runner set; cannot process job %s", job.id)
                continue
            try:
                if job.on_start is not None:
                    try:
                        await job.on_start(job)
                    except Exception:
                        logger.exception("on_start callback failed")
                result = await self._runner(job)
                self.results[job.id] = result
                if job.on_complete is not None:
                    try:
                        await job.on_complete(job, result)
                    except Exception:
                        logger.exception("on_complete callback failed")
            except Exception as exc:
                logger.exception("Job %s failed: %s", job.id, exc)
                self.results[job.id] = JobResult(
                    job_id=job.id, winner=None, turns=0, duration_s=0.0
                )


async def default_runner(job: BattleJob) -> JobResult:
    """Stub runner that sleeps to simulate a battle. Replace with real one."""
    t0 = time.monotonic()
    await asyncio.sleep(0.5)
    return JobResult(
        job_id=job.id,
        winner=job.player1,
        turns=20,
        duration_s=time.monotonic() - t0,
    )


__all__ = ["BattleJob", "JobResult", "Orchestrator", "default_runner"]
