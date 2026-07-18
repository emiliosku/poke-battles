"""Unit test for the dead-connection watchdog in ``PokemonBattleEnv``.

Regression coverage for the hang where the Showdown websocket drops mid-battle
without raising (poke-env 0.15 leaves the battle coroutine hanging). Without
the watchdog the env blocks forever in ``reset()``/``step()`` waiting for an
observation that never arrives. The watchdog must detect the stall and force a
reconnect (set ``_connection_dead`` and ``_battle_over``).
"""

from __future__ import annotations

import threading
import time

from pokerl.env import WATCHDOG_TIMEOUT, PokemonBattleEnv


def _build_minimal_env() -> PokemonBattleEnv:
    env = PokemonBattleEnv.__new__(PokemonBattleEnv)
    env._config = None  # type: ignore[assignment]
    env._player = None
    env._opponent = None
    env._connection_dead = False
    env._battle_active = True
    env._last_obs_time = time.monotonic()
    env._battle_over = threading.Event()
    env._watchdog_stop = threading.Event()
    # A dummy thread that stays alive for the duration of the test so the
    # watchdog treats the battle as in-progress (not already finished).
    def _hang() -> None:
        time.sleep(30.0)

    env._thread = threading.Thread(target=_hang, daemon=True)
    env._thread.start()
    return env


def test_watchdog_forces_reconnect_on_stall() -> None:
    env = _build_minimal_env()
    # Pretend the last observation was long ago (simulate a dead connection).
    env._last_obs_time = time.monotonic() - (WATCHDOG_TIMEOUT + 10.0)

    wt = threading.Thread(target=env._watchdog_loop, daemon=True)
    wt.start()
    wt.join(timeout=10.0)
    env._watchdog_stop.set()

    assert env._connection_dead is True
    assert env._battle_over.is_set() is True
    assert env._battle_active is False


def test_watchdog_does_not_fire_during_active_battle() -> None:
    env = _build_minimal_env()
    # Recent observation -> battle is healthy.
    env._last_obs_time = time.monotonic() - 1.0

    wt = threading.Thread(target=env._watchdog_loop, daemon=True)
    wt.start()
    wt.join(timeout=10.0)
    env._watchdog_stop.set()

    assert env._connection_dead is False
    assert env._battle_over.is_set() is False


def test_watchdog_skips_when_no_active_battle() -> None:
    env = _build_minimal_env()
    env._battle_active = False
    env._last_obs_time = time.monotonic() - (WATCHDOG_TIMEOUT + 100.0)

    wt = threading.Thread(target=env._watchdog_loop, daemon=True)
    wt.start()
    wt.join(timeout=10.0)
    env._watchdog_stop.set()

    assert env._connection_dead is False
