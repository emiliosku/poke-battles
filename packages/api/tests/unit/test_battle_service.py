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
from pokeapi.services.choosers import (
    _legacy_decision_to_order,
    _Order,
    _record_rationale,
    _resolve_order,
)
from pokeengine.events import Event, EventKind
from pokellm.config import Tier


class TestBuildChooser:
    def test_heuristic_uses_legal_random_order_for_doubles(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pokeapi.services.choosers as choosers

        class _DoubleBattle:
            pass

        class _Player:
            def choose_random_move(self, battle: object) -> str:
                return "legal-double-order"

        monkeypatch.setattr(choosers, "DoubleBattle", _DoubleBattle)

        assert choosers._heuristic_chooser(_Player(), _DoubleBattle()) == "legal-double-order"  # type: ignore[arg-type]

    def test_legacy_order_keeps_terastallization_flag(self) -> None:
        decision = type(
            "Decision",
            (),
            {"action": "choose_move", "move_id": "thunderbolt", "terastallize": True},
        )()
        order = _legacy_decision_to_order(decision)
        move = type("Move", (), {"id": "thunderbolt"})()

        class _Player:
            def create_order(
                self, selected: object, **kwargs: object
            ) -> tuple[object, dict[str, object]]:
                return selected, kwargs

            def choose_random_move(self, battle: object) -> None:
                return None

        battle = type("Battle", (), {"available_moves": [move], "available_switches": []})()

        assert order == _Order(action="choose_move", move_id="thunderbolt", terastallize=True)
        assert _resolve_order(_Player(), order, battle) == (move, {"terastallize": True})  # type: ignore[arg-type]

    def test_rationale_recorder_keeps_only_real_commentary(self) -> None:
        recorded: list[tuple[str, str | None, str]] = []

        _record_rationale(
            lambda _battle, action, target, commentary: recorded.append(
                (action, target, commentary)
            ),
            object(),
            "choose_move",
            "earthquake",
            "  pressure their switch  ",
        )
        _record_rationale(
            lambda _battle, action, target, commentary: recorded.append(
                (action, target, commentary)
            ),
            object(),
            "choose_move",
            "protect",
            "   ",
        )

        assert recorded == [("choose_move", "earthquake", "pressure their switch")]

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

    def test_model_name_rl_returns_callable(self) -> None:
        chooser = build_chooser("rl", None)
        assert chooser is not _random_chooser
        assert callable(chooser)

    def test_mode_rl_via_config_returns_callable(self) -> None:
        from pokellm.config import AgentConfig

        cfg = AgentConfig(
            name="rl",
            provider="rl",
            model_id="pokerl/ppo/v1",
            tier=Tier.LOCAL,
            mode="rl",
        )
        chooser = build_chooser("rl", cfg)
        assert callable(chooser)
        assert chooser is not _random_chooser


class TestBuildRlChooser:
    def test_unset_model_path_falls_back_to_random(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pokeapi.services import _build_rl_chooser, agent_stats

        monkeypatch.delenv("POKERL_MODEL_PATH", raising=False)
        chooser = _build_rl_chooser("rl")

        class _Player:
            def choose_random_move(self, battle: object) -> str:
                return "random"

        result = _Player.__call__  # type: ignore[attr-defined]
        del result  # silence linter

        import asyncio

        chosen = asyncio.run(chooser(_Player(), object()))  # type: ignore[arg-type]
        assert chosen == "random"
        assert agent_stats["rl"]["rl_calls"] == 1
        assert agent_stats["rl"]["fallback_random"] == 1

    def test_missing_model_file_falls_back_to_random(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        from pokeapi.services import _build_rl_chooser, agent_stats

        missing = tmp_path / "does_not_exist.zip"
        monkeypatch.setenv("POKERL_MODEL_PATH", str(missing))

        chooser = _build_rl_chooser("rl")

        class _Player:
            def choose_random_move(self, battle: object) -> str:
                return "random"

        import asyncio

        chosen = asyncio.run(chooser(_Player(), object()))  # type: ignore[arg-type]
        assert chosen == "random"
        assert agent_stats["rl"]["fallback_random"] == 1


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
    async def test_run_job_preserves_winner_side(self) -> None:
        service = BattleService()

        async def fake_run_battle(**_: object) -> dict[str, object]:
            return {"battle_id": "showdown-1", "winner": "alicea1234", "winner_side": "p1"}

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        from pokeapi.orchestrator import BattleJob

        result = await service.run_job(BattleJob(player1="Alice", player2="Bob"))

        assert result.winner == "alicea1234"
        assert result.winner_side == "p1"

    @pytest.mark.asyncio
    async def test_run_job_preserves_rationales(self) -> None:
        service = BattleService()

        async def fake_run_battle(**_: object) -> dict[str, object]:
            return {
                "battle_id": "showdown-1",
                "winner": "alicea1234",
                "winner_side": "p1",
                "rationales": [
                    {
                        "turn": 2,
                        "model": "model-a",
                        "action": "choose_move",
                        "target": "earthquake",
                        "commentary": "pressure their switch",
                    }
                ],
            }

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        from pokeapi.orchestrator import BattleJob

        result = await service.run_job(BattleJob(player1="Alice", player2="Bob"))

        assert result.rationales == [
            {
                "turn": 2,
                "model": "model-a",
                "action": "choose_move",
                "target": "earthquake",
                "commentary": "pressure their switch",
            }
        ]

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

    @pytest.mark.asyncio
    async def test_team_vs_team_emits_progress_per_battle(self) -> None:
        service = BattleService()
        sides = iter(["p1", "p2", "p1", "tie", "p1"])

        async def fake_run_battle(**_: object) -> dict[str, object | None]:
            return {"winner": "sima1234a5678", "winner_side": next(sides)}

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        calls: list[tuple[int, int, int, int]] = []

        def on_progress(battles_done: int, wins: int, losses: int, draws: int) -> None:
            calls.append((battles_done, wins, losses, draws))

        result = await service.run_simulation(
            mode="team_vs_team",
            battle_format="gen9randombattle",
            models=["random", "random"],
            n_battles=5,
            progress_callback=on_progress,
        )

        # Called once per battle, with monotonically increasing
        # battles_done.
        assert len(calls) == 5
        assert [c[0] for c in calls] == [1, 2, 3, 4, 5]
        # Final callback matches the result tallies (3 wins, 1 loss, 1 draw).
        assert calls[-1] == (5, 3, 1, 1)
        assert result["wins"] == 3
        assert result["losses"] == 1
        assert result["draws"] == 1

    @pytest.mark.asyncio
    async def test_round_robin_emits_running_totals(self) -> None:
        service = BattleService()
        sides = iter(["p1", "p1", "p2", "p1"])

        async def fake_run_battle(**_: object) -> dict[str, object | None]:
            return {"winner": "rrm1xxa1234", "winner_side": next(sides)}

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        calls: list[tuple[int, int, int, int]] = []
        await service.run_simulation(
            mode="round_robin",
            battle_format="gen9randombattle",
            models=["m1", "m2"],
            n_battles=2,
            progress_callback=lambda done, wins, losses, draws: calls.append(
                (done, wins, losses, draws)
            ),
        )

        # round_robin runs n_battles per matchup, so 2 battles per
        # matchup, 1 matchup (m1, m2) -> 2 calls.
        assert len(calls) == 2
        # After both battles: m1 won both (p1), so wins=2, losses=0.
        assert calls[-1][0] == 2
        assert calls[-1][1] == 2
        assert calls[-1][2] == 0
        assert calls[-1][3] == 0

    @pytest.mark.asyncio
    async def test_progress_callback_optional(self) -> None:
        service = BattleService()

        async def fake_run_battle(**_: object) -> dict[str, object | None]:
            return {"winner": "sima1234a5678", "winner_side": "p1"}

        service.run_battle = fake_run_battle  # type: ignore[method-assign]

        # No progress_callback supplied should still complete normally.
        result = await service.run_simulation(
            mode="team_vs_team",
            battle_format="gen9randombattle",
            models=["random", "random"],
            n_battles=3,
        )
        assert result["wins"] == 3
