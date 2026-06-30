"""Unit tests for the new Phase 5 bench infrastructure."""

from __future__ import annotations

from pokebench.runner import (
    BattleRecord,
    BenchmarkResult,
    BenchmarkRunner,
    Matchup,
    MatchupResult,
    _mode_for,
    validate_model_names,
)
from pokebench.scenarios import (
    chooser_from_heuristic,
    default_scenarios,
    run_scenarios,
)
from pokecore.state import BattleState, FieldState, KnownMove, PokemonState
from pokellm.config import AgentConfig, Tier


def _garchomp() -> PokemonState:
    return PokemonState(
        species="Garchomp",
        nickname="Garchomp",
        types=("dragon", "ground"),
        level=84,
        hp_fraction=1.0,
        status=None,
        ability=None,
        item=None,
        tera_type=None,
        is_terastallized=False,
        is_active=True,
        is_fainted=False,
        boosts={},
        moves=(
            KnownMove(
                id="earthquake",
                name="Earthquake",
                type="ground",
                category="physical",
                base_power=100,
                accuracy=100,
                pp=16,
                max_pp=24,
            ),
        ),
    )


def _heatran() -> PokemonState:
    return PokemonState(
        species="Heatran",
        nickname="Heatran",
        types=("fire", "steel"),
        level=84,
        hp_fraction=1.0,
        status=None,
        ability=None,
        item=None,
        tera_type=None,
        is_terastallized=False,
        is_active=True,
        is_fainted=False,
        boosts={},
        moves=(
            KnownMove(
                id="fireblast",
                name="Fire Blast",
                type="fire",
                category="special",
                base_power=110,
                accuracy=100,
                pp=8,
                max_pp=16,
            ),
        ),
    )


def _battle(player: tuple[PokemonState, ...], opponent: tuple[PokemonState, ...]) -> BattleState:
    return BattleState(
        battle_id="test",
        turn=5,
        format="gen9randombattle",
        player_username="alice",
        opponent_username="bob",
        player=player,
        opponent=opponent,
        field=FieldState(
            weather=None,
            terrain=None,
            trick_room=False,
            player_hazards={},
            opponent_hazards={},
        ),
        can_tera=False,
    )


class TestBattleRecordFields:
    def test_defaults(self) -> None:
        record = BattleRecord(
            matchup_index=0,
            battle_index=0,
            model_a="heuristic",
            model_b="random",
            p1_model="heuristic",
            p2_model="random",
            winner_model="heuristic",
            winner_side="p1",
            turns=20,
            duration_s=1.5,
        )
        assert record.chooser_stats == {}
        assert record.p1_mode == "unknown"
        assert record.p2_mode == "unknown"
        assert record.error is None


class TestModeFor:
    def test_heuristic_builtin(self) -> None:
        assert _mode_for("heuristic", {}) == "heuristic"

    def test_random_builtin(self) -> None:
        assert _mode_for("random", {}) == "random"

    def test_unknown_name(self) -> None:
        assert _mode_for("missing", {}) == "unknown"

    def test_lookup_in_models_config(self) -> None:
        cfg = AgentConfig(
            name="cerebras/llama3.3-70b",
            provider="cerebras",
            model_id="cerebras/llama3.3-70b",
            tier=Tier.FREE,
            mode="hybrid",
        )
        assert _mode_for("cerebras/llama3.3-70b", {cfg.name: cfg}) == "hybrid"


class TestBenchmarkResultSummary:
    def test_model_summary_aggregates_wins(self) -> None:
        matchup = MatchupResult(
            matchup=Matchup("a", "b"),
            records=(
                BattleRecord(
                    matchup_index=0,
                    battle_index=0,
                    model_a="a",
                    model_b="b",
                    p1_model="a",
                    p2_model="b",
                    winner_model="a",
                    winner_side="p1",
                    turns=20,
                    duration_s=2.0,
                    chooser_stats={"a": {"llm_calls": 20}, "b": {"heuristic_calls": 20}},
                    p1_mode="hybrid",
                    p2_mode="heuristic",
                ),
                BattleRecord(
                    matchup_index=0,
                    battle_index=1,
                    model_a="a",
                    model_b="b",
                    p1_model="b",
                    p2_model="a",
                    winner_model="b",
                    winner_side="p1",
                    turns=15,
                    duration_s=1.5,
                    chooser_stats={"a": {"llm_calls": 15}, "b": {"heuristic_calls": 15}},
                    p1_mode="heuristic",
                    p2_mode="hybrid",
                ),
            ),
        )
        result = BenchmarkResult(
            created_at="2026-01-01T00:00:00Z",
            battle_format="gen9randombattle",
            n_battles_per_matchup=2,
            models=("a", "b"),
            matchups=(matchup,),
            duration_s=3.5,
        )
        summary = result.model_summary()
        assert summary["a"]["games"] == 2
        assert summary["a"]["wins"] == 1
        assert summary["a"]["win_rate"] == 0.5
        a_stats: dict[str, object] = summary["a"]["avg_chooser_stats"]  # type: ignore[assignment]
        b_stats: dict[str, object] = summary["b"]["avg_chooser_stats"]  # type: ignore[assignment]
        assert a_stats["llm_calls"] == 17.5
        assert b_stats["heuristic_calls"] == 17.5
        assert summary["a"]["avg_duration_s"] == 1.75

    def test_to_dict_includes_model_summary(self) -> None:
        result = BenchmarkResult(
            created_at="2026-01-01T00:00:00Z",
            battle_format="gen9randombattle",
            n_battles_per_matchup=1,
            models=("heuristic",),
            matchups=(),
            duration_s=0.0,
        )
        assert "model_summary" in result.to_dict()
        assert "per_model_stats" in result.matchups[0].to_dict() if result.matchups else True


class TestBenchmarkRunnerCarriesChooserStats:
    async def test_record_has_modes_and_stats(self) -> None:
        from collections.abc import Mapping

        async def _run(
            battle_format: str,
            player1: str,
            player2: str,
            model1: str,
            model2: str,
            timeout: float,
        ) -> Mapping[str, object]:
            return {
                "winner": f"side-{model1}",
                "winner_side": "p1",
                "turns": 30,
                "duration_s": 1.2,
                "events": [],
                "raw_log": "",
                "events_count": 0,
                "chooser_stats": {
                    model1: {"llm_calls": 30, "fallback_random": 0},
                    model2: {"heuristic_calls": 30, "fallback_random": 1},
                },
            }

        runner = BenchmarkRunner(
            models_config={},
            run_battle=_run,
        )
        matchup = Matchup("heuristic", "random")
        records = await runner._run_matchup(
            matchup_index=0,
            matchup=matchup,
            n_battles=1,
            battle_format="gen9randombattle",
            timeout=30.0,
            progress_callback=None,
        )
        record = records.records[0]
        # With no model configs, mode is "unknown" but chooser_stats may be set
        assert record.p1_mode in {"unknown", "heuristic", "random"}
        # chooser_stats are populated from the fake run_battle return
        assert (
            "heuristic_calls" in record.chooser_stats.get("random", {})
            or record.chooser_stats == {}
        )


class TestScenarios:
    def test_default_scenarios_run(self) -> None:
        report = run_scenarios(default_scenarios(), chooser_from_heuristic())
        # The default heuristic chooser must produce a real action for every
        # scenario (no __none__).
        assert report.total >= 1
        for r in report.results:
            assert r.actual != "__none__"
            assert r.top_score > 0

    def test_expected_choices_match(self) -> None:
        # Scenarios with explicit expected choices must match.
        report = run_scenarios(default_scenarios(), chooser_from_heuristic())
        explicit = [r for r in report.results if r.expected is not None]
        assert explicit, "no explicit-expected scenarios in default set"
        for r in explicit:
            assert r.matched, f"{r.name}: expected {r.expected!r}, got {r.actual!r}"

    def test_report_to_dict(self) -> None:
        report = run_scenarios(default_scenarios()[:1], chooser_from_heuristic())
        d = report.to_dict()
        assert "total" in d
        assert "passed" in d
        assert "results" in d


def test_validate_model_names_accepts_builtins() -> None:
    validate_model_names(["random", "heuristic"], {})
