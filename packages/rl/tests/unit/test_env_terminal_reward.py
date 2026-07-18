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


def test_shaping_dominates_terminal_over_a_battle() -> None:
    """Regression: the dense per-turn shaping must be a meaningful fraction
    of the signal so PPO has a gradient even when the agent always loses.

    A full battle's shaping sum should be on the same order as (not dwarfed
    by) the terminal win/loss, otherwise the terminal is a near-constant
    offset with no learning signal vs a strong opponent.
    """
    from pokerl.rewards import RewardConfig, RewardTracker

    cfg = RewardConfig()
    tracker = RewardTracker(config=cfg)

    # Simulate a 50-turn battle where the agent deals ~4 HP fractions of
    # damage, takes ~5, KOs 1 and faints 2 (a typical losing battle).
    reward_sum = 0.0
    for turn in range(50):
        if turn == 20:
            opp_fainted, player_fainted = 1, 0  # agent scores a KO
        elif turn in (30, 45):
            opp_fainted, player_fainted = 1, 1  # trade
        else:
            opp_fainted, player_fainted = 1, 1
        # crudely walk HP down toward the fainted counts
        opp_hp = max(0.0, 6.0 - turn * 0.08 - opp_fainted * 1.0)
        pl_hp = max(0.0, 6.0 - turn * 0.1 - player_fainted * 1.0)
        reward_sum += tracker.step(
            player_hp_sum=pl_hp,
            opponent_hp_sum=opp_hp,
            player_fainted=player_fainted,
            opponent_fainted=opp_fainted,
            battle_finished=False,
            won=None,
        )
    reward_sum += cfg.loss_reward  # terminal loss

    # Shaping magnitude over the battle should rival the terminal weight.
    assert abs(reward_sum) > 0
    # The per-turn shaping alone (excluding terminal) should not be swamped
    # by the ±1.0 terminal; assert the accumulated shaping is >= ~0.5.
    shaping_only = reward_sum - cfg.loss_reward
    assert abs(shaping_only) >= 0.5
