"""Pairwise benchmark runner for agent matchups."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import cast

from pokeapi.services import BattleService
from pokellm.config import AgentConfig, find_models_yaml, load_models_yaml

RunBattle = Callable[[str, str, str, str, str, float], Awaitable[Mapping[str, object]]]
ProgressCallback = Callable[["BattleRecord"], None]


@dataclass(frozen=True, slots=True)
class Matchup:
    """A pair of models to benchmark against each other."""

    model_a: str
    model_b: str

    @property
    def label(self) -> str:
        return f"{self.model_a} vs {self.model_b}"


@dataclass(frozen=True, slots=True)
class BattleRecord:
    """One completed benchmark battle."""

    matchup_index: int
    battle_index: int
    model_a: str
    model_b: str
    p1_model: str
    p2_model: str
    winner_model: str | None
    winner_side: str
    turns: int
    duration_s: float
    error: str | None = None
    # Per-side chooser stats from the live chooser (e.g. llm_calls, fallback_random).
    # Empty dict when the chooser didn't report any stats.
    chooser_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    # Mode each side ran in: 'heuristic', 'hybrid', 'legacy', or 'random'.
    p1_mode: str = "unknown"
    p2_mode: str = "unknown"


@dataclass(frozen=True, slots=True)
class MatchupResult:
    """Aggregate result for one pairwise matchup."""

    matchup: Matchup
    records: tuple[BattleRecord, ...]

    @property
    def battles(self) -> int:
        return len(self.records)

    @property
    def model_a_wins(self) -> int:
        return sum(1 for record in self.records if record.winner_model == self.matchup.model_a)

    @property
    def model_b_wins(self) -> int:
        return sum(1 for record in self.records if record.winner_model == self.matchup.model_b)

    @property
    def draws(self) -> int:
        return sum(
            1 for record in self.records if record.winner_model is None and record.error is None
        )

    @property
    def errors(self) -> int:
        return sum(1 for record in self.records if record.error is not None)

    @property
    def model_a_win_rate(self) -> float:
        decisive = self.model_a_wins + self.model_b_wins
        return self.model_a_wins / decisive if decisive else 0.0

    @property
    def avg_turns(self) -> float:
        records = [record for record in self.records if record.turns > 0]
        return sum(record.turns for record in records) / len(records) if records else 0.0

    @property
    def avg_duration_s(self) -> float:
        return (
            sum(record.duration_s for record in self.records) / len(self.records)
            if self.records
            else 0.0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "matchup": asdict(self.matchup),
            "battles": self.battles,
            "model_a_wins": self.model_a_wins,
            "model_b_wins": self.model_b_wins,
            "draws": self.draws,
            "errors": self.errors,
            "model_a_win_rate": self.model_a_win_rate,
            "avg_turns": self.avg_turns,
            "avg_duration_s": self.avg_duration_s,
            "per_model_stats": self.per_model_stats(),
            "records": [asdict(record) for record in self.records],
        }

    def per_model_stats(self) -> dict[str, dict[str, float]]:
        """Aggregate per-side chooser stats for this matchup.

        Returns a dict like::

            {
                "model_a": {"llm_calls": 12.0, "fallback_random": 0.0},
                "model_b": {...},
            }
        """
        out: dict[str, dict[str, float]] = {
            self.matchup.model_a: {},
            self.matchup.model_b: {},
        }
        for record in self.records:
            for _side, model in (
                ("p1", record.p1_model),
                ("p2", record.p2_model),
            ):
                # Map side to the model_a/model_b bucket the bench reports on
                if model == self.matchup.model_a:
                    bucket = out[self.matchup.model_a]
                elif model == self.matchup.model_b:
                    bucket = out[self.matchup.model_b]
                else:
                    continue
                for key, value in record.chooser_stats.get(model, {}).items():
                    bucket[key] = bucket.get(key, 0.0) + float(value)
        # Average per battle
        n = max(1, self.battles)
        return {
            model: {key: value / n for key, value in stats.items()} for model, stats in out.items()
        }


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Complete benchmark result for one run."""

    created_at: str
    battle_format: str
    n_battles_per_matchup: int
    models: tuple[str, ...]
    matchups: tuple[MatchupResult, ...]
    duration_s: float
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def total_battles(self) -> int:
        return sum(matchup.battles for matchup in self.matchups)

    def to_dict(self) -> dict[str, object]:
        return {
            "created_at": self.created_at,
            "battle_format": self.battle_format,
            "n_battles_per_matchup": self.n_battles_per_matchup,
            "models": list(self.models),
            "total_battles": self.total_battles,
            "duration_s": self.duration_s,
            "metadata": self.metadata,
            "model_summary": self.model_summary(),
            "matchups": [matchup.to_dict() for matchup in self.matchups],
        }

    def model_summary(self) -> dict[str, dict[str, object]]:
        """Per-model aggregate: total wins, total games, win rate, avg duration,
        and average chooser stats across all matchups."""
        wins: dict[str, int] = dict.fromkeys(self.models, 0)
        games: dict[str, int] = dict.fromkeys(self.models, 0)
        durations: dict[str, list[float]] = {m: [] for m in self.models}
        stats_acc: dict[str, dict[str, float]] = {m: {} for m in self.models}
        for matchup in self.matchups:
            for record in matchup.records:
                for model in (record.p1_model, record.p2_model):
                    if model not in games:
                        games[model] = 0
                    games[model] += 1
                    durations.setdefault(model, []).append(record.duration_s)
                if record.winner_model in wins:
                    wins[record.winner_model] += 1
                for model, chooser_stats in record.chooser_stats.items():
                    for key, value in chooser_stats.items():
                        stats_acc.setdefault(model, {})[key] = stats_acc.get(model, {}).get(
                            key, 0.0
                        ) + float(value)
        summary: dict[str, dict[str, object]] = {}
        for model in sorted(set(self.models) | set(games)):
            total = games.get(model, 0)
            win = wins.get(model, 0)
            avg_dur = sum(durations.get(model, [])) / max(1, len(durations.get(model, [])))
            stats: dict[str, float] = stats_acc.get(model, {})
            stats_avg = {k: round(v / max(1, total), 2) for k, v in stats.items()}
            summary[model] = {
                "games": total,
                "wins": win,
                "win_rate": round(win / total, 3) if total else 0.0,
                "avg_duration_s": round(avg_dur, 2),
                "avg_chooser_stats": stats_avg,
            }
        return summary


def build_matchups(models: Sequence[str]) -> list[Matchup]:
    """Build pairwise model matchups from a model list."""
    unique_models = list(dict.fromkeys(models))
    if len(unique_models) < 2:
        raise ValueError("benchmark requires at least two distinct models")
    return [Matchup(a, b) for a, b in combinations(unique_models, 2)]


def load_available_model_configs(path: Path | None = None) -> dict[str, AgentConfig]:
    """Load model configs for any non-random agents."""
    models_path = path or find_models_yaml()
    if not models_path.exists():
        return {}
    return load_models_yaml(models_path)


def validate_model_names(models: Sequence[str], configs: Mapping[str, AgentConfig]) -> None:
    """Fail early when a model name would silently become the random chooser.

    Recognized built-in names: ``random`` and ``heuristic``. Any other name
    must be a key in ``configs`` (i.e. come from ``models.yaml``).
    """
    builtins = {"random", "heuristic"}
    missing = sorted({model for model in models if model not in builtins and model not in configs})
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"unknown benchmark model(s): {names}")


def _mode_for(model_name: str, configs: Mapping[str, AgentConfig]) -> str:
    """Return the chooser mode for a model name: 'heuristic', 'hybrid',
    'legacy', or 'random'. Falls back to the model name if unknown."""
    if model_name == "heuristic":
        return "heuristic"
    if model_name == "random":
        return "random"
    cfg = configs.get(model_name)
    if cfg is None:
        return "unknown"
    return cfg.mode


class BenchmarkRunner:
    """Run pairwise benchmarks through the existing BattleService."""

    def __init__(
        self,
        *,
        models_config: Mapping[str, AgentConfig] | None = None,
        showdown_dir: str = "server",
        showdown_port: int | None = None,
        run_battle: RunBattle | None = None,
        stop: Callable[[], None] | None = None,
    ) -> None:
        self._models_config: Mapping[str, AgentConfig] = dict(models_config or {})
        self._service: BattleService | None = None
        self._run_battle: RunBattle
        self._stop = stop
        if run_battle is None:
            self._service = BattleService(
                showdown_dir=showdown_dir,
                showdown_port=showdown_port,
                models=dict(self._models_config),
            )
            self._run_battle = self._run_battle_service
            self._stop = self._service.stop
        else:
            self._run_battle = run_battle

    async def run(
        self,
        *,
        models: Sequence[str],
        n_battles: int,
        battle_format: str,
        timeout: float = 240.0,
        progress_callback: ProgressCallback | None = None,
    ) -> BenchmarkResult:
        """Run all pairwise matchups and return structured results."""
        if n_battles < 1:
            raise ValueError("n_battles must be >= 1")
        matchups = build_matchups(models)
        started = time.monotonic()
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            matchup_results: list[MatchupResult] = []
            for matchup_index, matchup in enumerate(matchups):
                matchup_results.append(
                    await self._run_matchup(
                        matchup_index=matchup_index,
                        matchup=matchup,
                        n_battles=n_battles,
                        battle_format=battle_format,
                        timeout=timeout,
                        progress_callback=progress_callback,
                    )
                )
            duration_s = time.monotonic() - started
            return BenchmarkResult(
                created_at=created_at,
                battle_format=battle_format,
                n_battles_per_matchup=n_battles,
                models=tuple(dict.fromkeys(models)),
                matchups=tuple(matchup_results),
                duration_s=duration_s,
                metadata={
                    "decision_latency_s": None,
                    "tokens": None,
                },
            )
        finally:
            if self._stop is not None:
                self._stop()

    async def _run_matchup(
        self,
        *,
        matchup_index: int,
        matchup: Matchup,
        n_battles: int,
        battle_format: str,
        timeout: float,
        progress_callback: ProgressCallback | None,
    ) -> MatchupResult:
        records: list[BattleRecord] = []
        for battle_index in range(n_battles):
            if battle_index % 2 == 0:
                p1_model = matchup.model_a
                p2_model = matchup.model_b
            else:
                p1_model = matchup.model_b
                p2_model = matchup.model_a
            record = await self._run_one_battle(
                matchup_index=matchup_index,
                battle_index=battle_index,
                matchup=matchup,
                p1_model=p1_model,
                p2_model=p2_model,
                battle_format=battle_format,
                timeout=timeout,
            )
            records.append(record)
            if progress_callback is not None:
                progress_callback(record)
        return MatchupResult(matchup=matchup, records=tuple(records))

    async def _run_one_battle(
        self,
        *,
        matchup_index: int,
        battle_index: int,
        matchup: Matchup,
        p1_model: str,
        p2_model: str,
        battle_format: str,
        timeout: float,
    ) -> BattleRecord:
        started = time.monotonic()
        result = await self._run_battle(
            battle_format,
            f"bench-{matchup_index}-{battle_index}-a",
            f"bench-{matchup_index}-{battle_index}-b",
            p1_model,
            p2_model,
            timeout,
        )
        duration_s = _as_float(result.get("duration_s"), time.monotonic() - started)
        error = str(result["error"]) if "error" in result else None
        winner_side = str(result.get("winner_side", "tie"))
        winner_model = _winner_model(winner_side=winner_side, p1_model=p1_model, p2_model=p2_model)
        if error is not None:
            winner_model = None
            winner_side = "error"
        chooser_stats: dict[str, dict[str, int]] = {}
        raw_stats = result.get("chooser_stats")
        if isinstance(raw_stats, dict):
            for name, stats in raw_stats.items():
                if isinstance(stats, dict):
                    chooser_stats[str(name)] = {str(k): int(v) for k, v in stats.items()}
        return BattleRecord(
            matchup_index=matchup_index,
            battle_index=battle_index,
            model_a=matchup.model_a,
            model_b=matchup.model_b,
            p1_model=p1_model,
            p2_model=p2_model,
            winner_model=winner_model,
            winner_side=winner_side,
            turns=_as_int(result.get("turns"), 0),
            duration_s=duration_s,
            error=error,
            chooser_stats=chooser_stats,
            p1_mode=_mode_for(p1_model, self._models_config),
            p2_mode=_mode_for(p2_model, self._models_config),
        )

    async def _run_battle_service(
        self,
        battle_format: str,
        player1: str,
        player2: str,
        model1: str,
        model2: str,
        timeout: float,
    ) -> Mapping[str, object]:
        if self._service is None:
            raise RuntimeError("BattleService was not initialized")
        return cast(
            "Mapping[str, object]",
            await self._service.run_battle(
                battle_format=battle_format,
                player1=player1,
                player2=player2,
                model1=model1,
                model2=model2,
                timeout=timeout,
            ),
        )


def _winner_model(*, winner_side: str, p1_model: str, p2_model: str) -> str | None:
    if winner_side == "p1":
        return p1_model
    if winner_side == "p2":
        return p2_model
    return None


def _as_float(value: object, default: float) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    return default


def _as_int(value: object, default: int) -> int:
    if isinstance(value, int | float | str):
        return int(value)
    return default


def write_result(result: BenchmarkResult, output_dir: Path) -> Path:
    """Write benchmark JSON to an output directory and return the path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_created_at = result.created_at.replace(":", "").replace("-", "")
    path = output_dir / f"benchmark-{safe_created_at}.json"
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
