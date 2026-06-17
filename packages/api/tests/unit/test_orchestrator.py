"""Unit tests for pokeapi.orchestrator."""

from __future__ import annotations

import asyncio

import pytest

from pokeapi.orchestrator import BattleJob, JobResult, Orchestrator


async def _fast_runner(job: BattleJob) -> JobResult:
    await asyncio.sleep(0.01)
    return JobResult(job_id=job.id, winner=job.player1, turns=10, duration_s=0.01)


class TestOrchestrator:
    async def test_start_and_stop(self) -> None:
        orch = Orchestrator(max_concurrent=2)
        await orch.start()
        assert len(orch._workers) == 2
        await orch.stop()
        assert orch._workers == []

    async def test_submit_and_get_result(self) -> None:
        orch = Orchestrator(max_concurrent=1)
        orch.set_runner(_fast_runner)
        await orch.start()
        job = BattleJob(
            format="gen9randombattle",
            player1="alice",
            player2="bob",
            model1="random",
            model2="random",
        )
        job_id = await orch.submit(job)
        result = await orch.get_result(job_id, timeout=2.0)
        assert result.job_id == job_id
        assert result.winner == "alice"
        assert result.turns == 10
        await orch.stop()

    async def test_get_result_timeout(self) -> None:
        orch = Orchestrator(max_concurrent=1)
        await orch.start()
        with pytest.raises(TimeoutError, match="did not finish"):
            await orch.get_result("nonexistent", timeout=0.1)
        await orch.stop()

    async def test_worker_concurrency(self) -> None:
        orch = Orchestrator(max_concurrent=4)
        orch.set_runner(_fast_runner)
        await orch.start()
        job_ids: list[str] = []
        for i in range(8):
            job = BattleJob(
                format="gen9randombattle",
                player1=f"p{i}",
                player2=f"q{i}",
                model1="random",
                model2="random",
            )
            job_ids.append(job.id)
            await orch.submit(job)
        for jid in job_ids:
            result = await orch.get_result(jid, timeout=3.0)
            assert result.turns == 10
        await orch.stop()
