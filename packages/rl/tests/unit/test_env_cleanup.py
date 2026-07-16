"""Regression tests for the per-battle event-loop cleanup.

Without this, ``PokemonBattleEnv._run_battle_background`` would call
``loop.close()`` while pending tasks (websocket readers, ps_client
housekeeping, etc.) were still scheduled. The orphans keep the
player's ``ps_client`` busy, so on the next ``env.reset()`` the
player's first obs is never produced and ``obs_queue.get`` times out
at 120s — a 200x slowdown on the second battle onward.

These tests verify the cleanup happens.
"""

from __future__ import annotations

import asyncio
import threading
import time
from queue import Queue
from unittest.mock import MagicMock

import pytest

from pokerl.env import PokemonBattleEnv


def _build_env(num_pending_tasks: int = 3) -> PokemonBattleEnv:
    """Build a minimal env wired to mock players.

    The mock player's ``battle_against`` returns a coroutine that
    spawns ``num_pending_tasks`` long-lived tasks on the event loop
    before returning. The cleanup must cancel them.
    """
    env = PokemonBattleEnv.__new__(PokemonBattleEnv)
    env._config = MagicMock()
    env._config.server_host = "127.0.0.1"
    env._config.server_port = 8001
    env._config.battle_format = "gen9randombattle"
    env._config.opponent = "random"
    env._env_id = 0
    env._reward_config = MagicMock()
    env._obs_queue = Queue(maxsize=8)
    env._action_queue = Queue(maxsize=8)
    env._started = True  # skip _start_background in reset()
    env._step_count = 0
    env._battle_count = 0
    env._reward_tracker = MagicMock()
    env._reward_tracker.step = MagicMock(return_value=0.0)
    env._current_battle = None
    env._action_mask = [True] * 9
    env._pending_tasks: list[asyncio.Task] = []
    env._captured_loop: asyncio.AbstractEventLoop | None = None

    async def long_running() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return

    async def battle_coro() -> None:
        loop = asyncio.get_running_loop()
        env._captured_loop = loop
        for _ in range(num_pending_tasks):
            env._pending_tasks.append(loop.create_task(long_running()))

    async def noop() -> None:
        return None

    player = MagicMock()
    opponent = MagicMock()
    player.ps_client.logged_in.is_set = MagicMock(return_value=True)
    opponent.ps_client.logged_in.is_set = MagicMock(return_value=True)

    async def _noop() -> None:
        return None

    player.ps_client.logged_in.wait = MagicMock(return_value=_noop())
    opponent.ps_client.logged_in.wait = MagicMock(return_value=_noop())
    player.battle_against = MagicMock(return_value=battle_coro())
    opponent.battle_against = MagicMock(return_value=noop())
    env._player = player
    env._opponent = opponent
    return env


def test_run_battle_background_cancels_pending_tasks() -> None:
    """All pending tasks on the battle loop must be cancelled before
    the loop closes, otherwise they leak as orphans and corrupt the
    next episode.
    """
    env = _build_env(num_pending_tasks=3)

    thread = threading.Thread(target=env._run_battle_background, daemon=True)
    thread.start()
    thread.join(timeout=10.0)
    assert not thread.is_alive(), "Battle thread did not exit cleanly"

    assert env._captured_loop is not None
    assert env._captured_loop.is_closed(), "Loop should be closed"
    for task in env._pending_tasks:
        assert task.cancelled() or task.done(), (
            f"Pending task {task!r} was left in non-terminal state"
        )


def test_run_battle_background_runs_quickly() -> None:
    """Cleanup must not block on a 60s ``asyncio.sleep`` — the spawned
    long-lived tasks must be cancelled, not awaited.
    """
    env = _build_env(num_pending_tasks=3)

    t0 = time.perf_counter()
    thread = threading.Thread(target=env._run_battle_background, daemon=True)
    thread.start()
    thread.join(timeout=10.0)
    elapsed = time.perf_counter() - t0
    assert not thread.is_alive()
    assert elapsed < 10.0, f"Cleanup took {elapsed:.1f}s, expected < 10s"


def test_run_battle_background_does_not_raise_on_cleanup_error() -> None:
    """If a cancelled task raises, the cleanup must still proceed
    and close the loop normally.
    """
    env = _build_env(num_pending_tasks=0)

    async def angry() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise RuntimeError("I refuse to be cancelled!")

    async def angry_battle_coro() -> None:
        loop = asyncio.get_running_loop()
        env._captured_loop = loop
        env._angry_task = loop.create_task(angry())

    env._player.battle_against = MagicMock(return_value=angry_battle_coro())

    thread = threading.Thread(target=env._run_battle_background, daemon=True)
    thread.start()
    thread.join(timeout=10.0)
    assert not thread.is_alive()
    assert env._captured_loop is not None
    assert env._captured_loop.is_closed()


@pytest.mark.parametrize("num_extra_tasks", [0, 1, 5])
def test_cleanup_handles_varying_number_of_pending_tasks(num_extra_tasks: int) -> None:
    """The cleanup must work for 0, 1, or many pending tasks."""
    env = _build_env(num_pending_tasks=num_extra_tasks)

    thread = threading.Thread(target=env._run_battle_background, daemon=True)
    thread.start()
    thread.join(timeout=10.0)
    assert not thread.is_alive()
    for task in env._pending_tasks:
        assert task.cancelled() or task.done()
