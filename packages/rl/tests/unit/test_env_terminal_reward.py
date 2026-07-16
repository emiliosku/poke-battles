"""Unit tests for terminal reward correctness in ``PokemonBattleEnv.step``.

Regression coverage for the bug where ``step()`` returned ``loss_reward``
(-1.0) unconditionally whenever the battle ended on the player's action
(poke-env does not call ``choose_move`` again, so no terminal observation
is queued and ``step()`` fell through to the ``_battle_over`` path, which
hardcoded a loss). That corrupted the win/loss signal and prevented the
agent from learning.
"""

from __future__ import annotations

import threading
from queue import Queue
from unittest.mock import MagicMock

import numpy as np

from pokerl.env import PokemonBattleEnv
from pokerl.rewards import RewardConfig


def _build_env() -> PokemonBattleEnv:
    env = PokemonBattleEnv.__new__(PokemonBattleEnv)
    env._config = MagicMock()
    env._config.server_host = "127.0.0.1"
    env._config.server_port = 8001
    env._config.battle_format = "gen9randombattle"
    env._config.opponent = "random"
    env._env_id = 0
    env._reward_config = RewardConfig()
    env._obs_queue = Queue(maxsize=8)
    env._action_queue = Queue(maxsize=8)
    env._started = True
    env._step_count = 0
    env._battle_count = 0
    env._reward_tracker = None
    env._current_battle = None
    env._action_mask = [True] * 9
    env._battle_over = threading.Event()
    env._thread = None
    return env


def _fake_battle(*, finished: bool, won: bool | None) -> MagicMock:
    battle = MagicMock()
    battle.finished = finished
    battle.won = won
    return battle


def test_terminal_result_returns_win_reward_on_win() -> None:
    env = _build_env()
    env._reward_tracker = MagicMock()
    env._reward_tracker.step = MagicMock(return_value=0.0)
    env._current_battle = _fake_battle(finished=True, won=True)

    obs, reward, terminated, truncated, info = env._terminal_result(reason="battle_over")

    assert terminated and truncated
    assert reward == env._reward_config.win_reward
    assert info["won"] is True
    assert info["terminal_reason"] == "battle_over"
    assert isinstance(obs, np.ndarray) and obs.shape == (360,)


def test_terminal_result_returns_loss_reward_on_loss() -> None:
    env = _build_env()
    env._reward_tracker = MagicMock()
    env._reward_tracker.step = MagicMock(return_value=0.0)
    env._current_battle = _fake_battle(finished=True, won=False)

    _obs, reward, _t, _tr, info = env._terminal_result(reason="battle_over")

    assert reward == env._reward_config.loss_reward
    assert info["won"] is False


def test_terminal_result_hardcodes_loss_when_battle_not_finished() -> None:
    """A genuine hang (battle thread died without finishing) is a loss."""
    env = _build_env()
    env._reward_tracker = MagicMock()
    env._reward_tracker.step = MagicMock(return_value=0.0)
    env._current_battle = _fake_battle(finished=False, won=None)

    _obs, reward, _t, _tr, info = env._terminal_result(reason="timeout")

    assert reward == env._reward_config.loss_reward
    assert info["won"] is False
    assert info["terminal_reason"] == "timeout"
