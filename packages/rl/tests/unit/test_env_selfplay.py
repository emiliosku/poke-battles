"""Unit tests for the self-play opponent reload in ``PokemonBattleEnv``.

Regression coverage for the self-play mechanism: the opponent must reload a
frozen policy snapshot from ``self_play_snapshot_path`` (or a path set via
``set_opponent_model``) so the agent trains against a periodically-refreshed
version of itself. Without reload-per-battle the opponent would be frozen at
the start of training and self-play would never progress.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pokerl.env import PokemonBattleEnv, _LoadedPolicyOpponent


def _build_minimal_env() -> PokemonBattleEnv:
    env = PokemonBattleEnv.__new__(PokemonBattleEnv)
    env._config = MagicMock()
    env._config.battle_format = "gen9randombattle"
    env._config.self_play_snapshot_path = None
    env._env_id = 0
    env._conn_id = 0
    env._player = None
    env._opponent = None
    env._opponent_model_path = None
    return env


def test_make_opponent_loads_policy_from_path(tmp_path) -> None:
    env = _build_minimal_env()
    dummy_model = MagicMock()
    model_file = tmp_path / "fake_opponent.zip"
    model_file.write_text("")
    with patch("sb3_contrib.MaskablePPO.load", return_value=dummy_model):
        env._opponent_model_path = str(model_file)
        opp = env._make_opponent(MagicMock(), conn_tag="0-0")
    assert isinstance(opp, _LoadedPolicyOpponent)
    assert opp._model is dummy_model


def test_set_opponent_model_updates_path(tmp_path) -> None:
    env = _build_minimal_env()
    snapshot = str(tmp_path / "newer_opponent.zip")
    env.set_opponent_model(snapshot)
    assert env._opponent_model_path == snapshot


def test_make_opponent_falls_back_to_random_when_no_path() -> None:
    env = _build_minimal_env()
    env._config.opponent = "random"
    env._opponent_model_path = None
    opp = env._make_opponent(MagicMock(), conn_tag="0-0")
    # RandomPlayer is the default fallback opponent type.
    assert type(opp).__name__ == "RandomPlayer"
