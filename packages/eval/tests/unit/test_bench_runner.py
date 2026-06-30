"""Unit tests for pokebench.runner."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from pokebench.runner import BenchmarkRunner, build_matchups, validate_model_names
from pokellm.config import AgentConfig


def test_build_matchups_pairwise_and_deduplicates() -> None:
    matchups = build_matchups(["a", "b", "a", "c"])

    assert [(m.model_a, m.model_b) for m in matchups] == [("a", "b"), ("a", "c"), ("b", "c")]


def test_build_matchups_requires_two_models() -> None:
    with pytest.raises(ValueError, match="at least two"):
        build_matchups(["random"])


def test_validate_model_names_allows_random_and_known_configs() -> None:
    config = AgentConfig(name="mock", provider="mock", model_id="mock/deterministic")
    validate_model_names(["random", "mock"], {"mock": config})


def test_validate_model_names_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown benchmark model"):
        validate_model_names(["typo"], {})


@pytest.mark.asyncio
async def test_runner_alternates_sides_and_attributes_winners() -> None:
    sides = iter(["p1", "p2", "tie"])
    calls: list[tuple[str, str]] = []
    stopped = False

    async def fake_run_battle(
        battle_format: str,
        player1: str,
        player2: str,
        model1: str,
        model2: str,
        timeout: float,
    ) -> Mapping[str, object]:
        assert battle_format == "gen9randombattle"
        assert player1
        assert player2
        assert timeout == 12.0
        calls.append((model1, model2))
        return {"winner_side": next(sides), "turns": 7, "duration_s": 1.25}

    def stop() -> None:
        nonlocal stopped
        stopped = True

    runner = BenchmarkRunner(run_battle=fake_run_battle, stop=stop)
    result = await runner.run(
        models=["a", "b"],
        n_battles=3,
        battle_format="gen9randombattle",
        timeout=12.0,
    )

    matchup = result.matchups[0]
    assert calls == [("a", "b"), ("b", "a"), ("a", "b")]
    assert matchup.model_a_wins == 2
    assert matchup.model_b_wins == 0
    assert matchup.draws == 1
    assert matchup.errors == 0
    assert matchup.avg_turns == 7.0
    assert stopped


@pytest.mark.asyncio
async def test_runner_records_errors_as_non_decisive() -> None:
    async def fake_run_battle(
        battle_format: str,
        player1: str,
        player2: str,
        model1: str,
        model2: str,
        timeout: float,
    ) -> Mapping[str, object]:
        return {"error": "battle timed out", "duration_s": 2.0}

    result = await BenchmarkRunner(run_battle=fake_run_battle).run(
        models=["a", "b"],
        n_battles=1,
        battle_format="gen9randombattle",
    )

    matchup = result.matchups[0]
    assert matchup.errors == 1
    assert matchup.draws == 0
    assert matchup.model_a_win_rate == 0.0
