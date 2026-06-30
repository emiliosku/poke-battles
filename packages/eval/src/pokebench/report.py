"""Human-readable benchmark reports."""

from __future__ import annotations

from pokebench.runner import BenchmarkResult, MatchupResult


def render_markdown(result: BenchmarkResult) -> str:
    """Render a benchmark result as a compact markdown document."""
    lines = [
        f"# Benchmark {result.created_at}",
        "",
        f"Format: `{result.battle_format}`",
        f"Battles per matchup: `{result.n_battles_per_matchup}`",
        f"Total battles: `{result.total_battles}`",
        f"Duration: `{result.duration_s:.1f}s`",
        "",
    ]
    lines.extend(_render_model_summary(result))
    lines.append("")
    lines.append(
        "| Matchup | Battles | A wins | B wins | Draws | Errors | A win % | Avg turns | Avg duration |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    lines.extend(_render_matchup_row(matchup) for matchup in result.matchups)
    return "\n".join(lines) + "\n"


def _render_model_summary(result: BenchmarkResult) -> list[str]:
    summary = result.model_summary()
    if not summary:
        return []
    lines = ["## Per-model summary", ""]
    lines.append("| Model | Mode | Games | Wins | Win % | Avg duration | Avg chooser stats |")
    lines.append("|---|---|---:|---:|---:|---:|---|")
    for model in sorted(summary):
        data = summary[model]
        games_raw: object = data.get("games", 0)
        wins_raw: object = data.get("wins", 0)
        win_rate_raw: object = data.get("win_rate", 0.0)
        avg_dur_raw: object = data.get("avg_duration_s", 0.0)
        games = int(games_raw) if isinstance(games_raw, (int, float, str)) else 0
        wins = int(wins_raw) if isinstance(wins_raw, (int, float, str)) else 0
        win_rate = float(win_rate_raw) if isinstance(win_rate_raw, (int, float, str)) else 0.0
        avg_dur = float(avg_dur_raw) if isinstance(avg_dur_raw, (int, float, str)) else 0.0
        stats: dict[str, object] = data.get("avg_chooser_stats", {})  # type: ignore[assignment]
        stats_str = ", ".join(f"{k}={v}" for k, v in stats.items()) or "—"
        mode = _mode_str(model, result)
        lines.append(
            f"| `{model}` | {mode} | {games} | {wins} | {win_rate * 100:.1f}% | {avg_dur:.1f}s | {stats_str} |"
        )
    return lines


def _mode_str(model: str, result: BenchmarkResult) -> str:
    """Best-effort: surface the mode from the first matchup record."""
    for matchup in result.matchups:
        for record in matchup.records:
            if record.p1_model == model:
                return record.p1_mode
            if record.p2_model == model:
                return record.p2_mode
    return "unknown"


def _render_matchup_row(matchup: MatchupResult) -> str:
    return (
        f"| `{matchup.matchup.model_a}` vs `{matchup.matchup.model_b}` "
        f"| {matchup.battles} "
        f"| {matchup.model_a_wins} "
        f"| {matchup.model_b_wins} "
        f"| {matchup.draws} "
        f"| {matchup.errors} "
        f"| {matchup.model_a_win_rate * 100:.1f}% "
        f"| {matchup.avg_turns:.1f} "
        f"| {matchup.avg_duration_s:.1f}s |"
    )
