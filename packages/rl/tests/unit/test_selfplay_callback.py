"""Unit test for the ``SelfPlayCallback`` swap logic."""

from __future__ import annotations

from unittest.mock import MagicMock

from pokerl.train import SelfPlayCallback


def _make_callback() -> tuple[SelfPlayCallback, MagicMock, MagicMock]:
    env = MagicMock()
    model = MagicMock()
    model.num_timesteps = 0
    cb = SelfPlayCallback(env, "/tmp/snap.zip", update_freq=50_000)
    cb.model = model  # type: ignore[attr-defined]
    # Avoid the VecEnv-unwrap loop on a MagicMock: just return the mock env.
    cb._base_env = lambda: env  # type: ignore[method-assign]
    return cb, env, model


def test_on_step_skips_before_threshold() -> None:
    cb, env, model = _make_callback()
    model.num_timesteps = 10_000
    assert cb.on_step() is True
    env.set_opponent_model.assert_not_called()


def test_on_step_swaps_at_threshold() -> None:
    cb, env, model = _make_callback()
    model.num_timesteps = 50_000
    assert cb.on_step() is True
    env.set_opponent_model.assert_called_once_with("/tmp/snap.zip")
    model.save.assert_called_once_with("/tmp/snap.zip")


def test_on_step_does_not_repeat_immediately() -> None:
    cb, env, model = _make_callback()
    model.num_timesteps = 50_000
    cb.on_step()
    env.reset_mock()
    model.num_timesteps = 55_000
    cb.on_step()
    env.set_opponent_model.assert_not_called()
