"""Unit tests for pokebench.report."""

from __future__ import annotations

from pokebench.report import render_markdown
from pokebench.runner import BattleRecord, BenchmarkResult, Matchup, MatchupResult


def test_render_markdown_includes_summary_table() -> None:
    matchup = Matchup("a", "b")
    result = BenchmarkResult(
        created_at="2026-06-30T00:00:00Z",
        battle_format="gen9randombattle",
        n_battles_per_matchup=2,
        models=("a", "b"),
        duration_s=3.0,
        matchups=(
            MatchupResult(
                matchup=matchup,
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
                        turns=4,
                        duration_s=1.0,
                    ),
                    BattleRecord(
                        matchup_index=0,
                        battle_index=1,
                        model_a="a",
                        model_b="b",
                        p1_model="b",
                        p2_model="a",
                        winner_model=None,
                        winner_side="tie",
                        turns=6,
                        duration_s=2.0,
                    ),
                ),
            ),
        ),
    )

    rendered = render_markdown(result)

    assert "# Benchmark 2026-06-30T00:00:00Z" in rendered
    assert "| `a` vs `b` | 2 | 1 | 0 | 1 | 0 | 100.0% | 5.0 | 1.5s |" in rendered
