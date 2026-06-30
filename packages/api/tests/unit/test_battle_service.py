"""Unit tests for the battle service chooser builder."""

from __future__ import annotations

import pytest

from pokeapi.services import (
    BattleService,
    _random_chooser,
    _showdown_account_name,
    _winner_from_events,
    build_chooser,
)
from pokeengine.events import Event, EventKind
from pokellm.config import Tier


class TestBuildChooser:
    def test_none_config_returns_random(self) -> None:
        chooser = build_chooser("anything", None)
        assert chooser is _random_chooser

    def test_mock_tier_returns_random(self) -> None:
        from pokellm.config import AgentConfig

        cfg = AgentConfig(
            name="mock",
            provider="mock",
            model_id="mock/deterministic",
            tier=Tier.MOCK,
            supports_tools=False,
        )
        chooser = build_chooser("mock", cfg)
        assert chooser is _random_chooser

    def test_real_tier_returns_llm_chooser(self) -> None:
        from pokellm.config import AgentConfig

        cfg = AgentConfig(
            name="llama",
            provider="cerebras",
            model_id="cerebras/llama3.1-8b",
            tier=Tier.FREE,
        )
        chooser = build_chooser("llama", cfg)
        assert chooser is not _random_chooser
        assert callable(chooser)


class TestRunSimulation:
    def test_showdown_account_name_is_login_safe(self) -> None:
        name = _showdown_account_name("Smoke-Human-abcdef", "1234", "a")

        assert name == "smokehumanabca1234"
        assert len(name) == 18
        assert name.isalnum()

    def test_showdown_account_name_has_fallback_and_side_suffix(self) -> None:
        assert _showdown_account_name("---", "1234", "a") == "playera1234"
        assert _showdown_account_name("---", "1234", "b") == "playerb1234"

    def test_winner_from_events_uses_showdown_win_event(self) -> None:
        events = [
            Event(kind=EventKind.TURN_START, turn=1),
            Event(kind=EventKind.BATTLE_END, turn=4, detail="Alice"),
        ]

        assert _winner_from_events(events) == "Alice"

    def test_winner_from_events_tie_is_draw(self) -> None:
        events = [Event(kind=EventKind.BATTLE_END, turn=4, detail="tie")]

        assert _winner_from_events(events) is None

    @pytest.mark.asyncio
    async def test_team_vs_team_counts_null_winner_as_draw(self) -> None:
        service = BattleService()

        async def fake_run_battle(**_: object) -> dict[str, object | None]:
            return {"winner": None, "winner_side": "tie"}

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        result = await service.run_simulation(
            mode="team_vs_team",
            battle_format="gen9randombattle",
            models=["random", "random"],
            n_battles=1,
        )

        assert result["wins"] == 0
        assert result["losses"] == 0
        assert result["draws"] == 1
        assert result["win_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_team_vs_team_attributes_winner_to_p1(self) -> None:
        service = BattleService()

        async def fake_run_battle(**_: object) -> dict[str, object | None]:
            return {"winner": "sima1234a5678", "winner_side": "p1"}

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        result = await service.run_simulation(
            mode="team_vs_team",
            battle_format="gen9randombattle",
            models=["random", "random"],
            n_battles=1,
        )

        assert result["wins"] == 1
        assert result["losses"] == 0
        assert result["draws"] == 0
        assert result["win_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_team_vs_team_attributes_winner_to_p2(self) -> None:
        service = BattleService()

        async def fake_run_battle(**_: object) -> dict[str, object | None]:
            return {"winner": "simb1234b5678", "winner_side": "p2"}

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        result = await service.run_simulation(
            mode="team_vs_team",
            battle_format="gen9randombattle",
            models=["random", "random"],
            n_battles=1,
        )

        assert result["wins"] == 0
        assert result["losses"] == 1
        assert result["draws"] == 0
        assert result["win_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_round_robin_credits_m1_when_p1_wins(self) -> None:
        service = BattleService()

        async def fake_run_battle(**_: object) -> dict[str, object | None]:
            return {"winner": "rrm1xxa1234", "winner_side": "p1"}

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        result = await service.run_simulation(
            mode="round_robin",
            battle_format="gen9randombattle",
            models=["m1", "m2"],
            n_battles=1,
        )

        results_map = result["results_map"]
        assert results_map["m1"]["wins"] == 1
        assert results_map["m1"]["losses"] == 0
        assert results_map["m2"]["wins"] == 0
        assert results_map["m2"]["losses"] == 1
        assert result["draws"] == 0

    @pytest.mark.asyncio
    async def test_ladder_credits_p1_winner_and_p2_loser(self) -> None:
        service = BattleService()

        async def fake_run_battle(**_: object) -> dict[str, object | None]:
            return {"winner": "ladderm1a1234", "winner_side": "p1"}

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        result = await service.run_simulation(
            mode="ladder",
            battle_format="gen9randombattle",
            models=["m1", "m2"],
            n_battles=4,
        )

        entries = result["entries"]
        # Ladder randomly samples (m1, m2) each round, so p1 may be
        # either model. With p1 always winning, every battle produces
        # exactly one win and one loss across the two models, and no
        # draws.
        total_wins = entries["m1"]["wins"] + entries["m2"]["wins"]
        total_losses = entries["m1"]["losses"] + entries["m2"]["losses"]
        assert total_wins == result["n_battles"]
        assert total_losses == result["n_battles"]
        assert total_wins == total_losses
        assert entries["m1"]["draws"] == 0
        assert entries["m2"]["draws"] == 0
