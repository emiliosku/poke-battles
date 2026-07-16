"""Regression tests for the per-battle event-loop cleanup.

Without this, ``PokemonBattleEnv._run_battle_background`` would call
``loop.close()`` while pending tasks (websocket readers, ps_client
housekeeping, etc.) were still scheduled. The orphans keep the
player's ``ps_client`` busy, so on the next ``env.reset()`` the
player's first obs is never produced and ``obs_queue.get`` times out
at 120s — a 200x slowdown on the second battle onward.

These tests verify the battle-over event fires promptly after the
battle thread exits.
"""

from __future__ import annotations

import asyncio
import threading
import time
from queue import Queue
from unittest.mock import MagicMock

from pokerl.env import PokemonBattleEnv


def _build_env() -> PokemonBattleEnv:
    """Build a minimal env wired to mock players.

    The mock player's ``battle_against`` returns a simple coroutine
    that simulates a short battle. The env must fire the
    ``_battle_over`` event after ``_run_battle_background`` finishes.
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
    env._started = True
    env._step_count = 0
    env._battle_count = 0
    env._reward_tracker = MagicMock()
    env._reward_tracker.step = MagicMock(return_value=0.0)
    env._current_battle = None
    env._action_mask = [True] * 9
    env._battle_over = threading.Event()
    env._server_config = MagicMock()
    env._opponent_model = None
    env._loop = None
    env._logged_in = threading.Event()
    env._start_battle = asyncio.Event()
    env._shutdown = threading.Event()

    async def noop() -> None:
        return None

    player = MagicMock()
    opponent = MagicMock()
    player.ps_client.logged_in.is_set = MagicMock(return_value=True)
    opponent.ps_client.logged_in.is_set = MagicMock(return_value=True)
    player.ps_client.logged_in.wait = MagicMock(return_value=noop())
    opponent.ps_client.logged_in.wait = MagicMock(return_value=noop())
    player.battle_against = MagicMock(return_value=noop())

    # _run_battle_background now builds fresh players per battle via
    # _build_players(); mock it to return our mock players so the
    # thread sets env._player / env._opponent as the real code does.
    env._build_players = MagicMock(return_value=(player, opponent))
    return env


def _run_one_battle(env: PokemonBattleEnv) -> threading.Thread:
    """Start the persistent battle loop, run exactly one battle, then stop
    the loop cleanly.

    The loop idles waiting for ``_start_battle`` between battles; we pre-set
    ``_logged_in`` (login is mocked) and immediately trigger a battle, then
    break the loop by setting ``_shutdown`` and waking the idle wait.
    """
    env._logged_in.set()  # login is mocked; skip the wait
    thread = threading.Thread(target=env._run_battle_background, daemon=True)
    thread.start()

    # Trigger the first battle on the loop (wait for the thread to install it).
    for _ in range(50):
        if env._loop is not None:
            break
        time.sleep(0.05)
    loop = env._loop
    assert loop is not None
    loop.call_soon_threadsafe(env._start_battle.set)

    # Wait for the first battle to set _battle_over (or time out).
    env._battle_over.wait(timeout=10.0)

    # Break the idle loop: set shutdown and wake the wait on _start_battle.
    env._shutdown.set()
    loop.call_soon_threadsafe(env._start_battle.set)
    return thread


def test_battle_over_event_fires_after_battle() -> None:
    """The ``_battle_over`` threading.Event must be set after a battle ends,
    so that ``step()`` can detect the end of battle immediately instead of
    waiting 120s.
    """
    env = _build_env()
    assert not env._battle_over.is_set()

    thread = _run_one_battle(env)
    thread.join(timeout=10.0)
    assert not thread.is_alive(), "Battle thread did not exit cleanly"
    assert env._battle_over.is_set(), (
        "_battle_over event should be set after a battle ends"
    )


def test_battle_over_event_fires_quickly() -> None:
    """The event must fire within 5s of the battle starting (the mock
    battle completes instantly).
    """
    env = _build_env()

    t0 = time.perf_counter()
    thread = _run_one_battle(env)
    thread.join(timeout=10.0)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"Battle + cleanup took {elapsed:.1f}s, expected < 5s"
    assert env._battle_over.is_set()


def test_battle_over_event_cleared_on_reset() -> None:
    """``reset()`` must clear the event so a new battle can be detected
    separately from the previous one.
    """
    env = _build_env()

    thread = _run_one_battle(env)
    thread.join(timeout=10.0)
    assert env._battle_over.is_set()

    env._battle_over.clear()
    assert not env._battle_over.is_set(), (
        "Event must be cleared before starting a new battle"
    )
