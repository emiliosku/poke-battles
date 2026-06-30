"""Command line entry point for pokebench."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from pokebench.report import render_markdown
from pokebench.runner import (
    BattleRecord,
    BenchmarkRunner,
    load_available_model_configs,
    validate_model_names,
    write_result,
)
from pokebench.scenarios import (
    chooser_from_heuristic,
    default_scenarios,
    run_scenarios,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run poke-battles agent benchmarks")
    parser.add_argument("--models", nargs="+", default=["random", "heuristic"])
    parser.add_argument("--n-battles", type=int, default=10)
    parser.add_argument("--format", default="gen9randombattle")
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--models-yaml", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("bench_results"))
    parser.add_argument("--showdown-dir", default="server")
    parser.add_argument("--showdown-port", type=int, default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--scenario",
        action="store_true",
        help="Run regression scenarios offline (no Showdown) instead of a live bench.",
    )
    return parser


async def amain(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.scenario:
        return _run_scenario_mode()
    try:
        configs = load_available_model_configs(args.models_yaml)
        validate_model_names(args.models, configs)
        runner = BenchmarkRunner(
            models_config=configs,
            showdown_dir=args.showdown_dir,
            showdown_port=args.showdown_port,
        )
        result = await runner.run(
            models=args.models,
            n_battles=args.n_battles,
            battle_format=args.format,
            timeout=args.timeout,
            progress_callback=None if args.quiet else _print_progress,
        )
    except Exception as exc:
        print(f"pokebench failed: {exc}", file=sys.stderr)
        return 2

    print(render_markdown(result))
    if not args.no_write:
        path = write_result(result, args.output_dir)
        print(f"Wrote JSON: {path}")
    return 0


def _run_scenario_mode() -> int:
    """Run the offline regression-scenario harness."""
    scenarios = default_scenarios()
    chooser = chooser_from_heuristic()
    report = run_scenarios(scenarios, chooser)
    print(f"Scenarios: {report.passed}/{report.total} passed")
    for r in report.results:
        status = "PASS" if r.matched else "FAIL"
        expected = r.expected or "(any)"
        print(
            f"  [{status}] {r.name:30s}  expected={expected:30s}  actual={r.actual:30s}  score={r.top_score:.1f}"
        )
    return 0 if report.failed == 0 else 1


def _print_progress(record: BattleRecord) -> None:
    if record.error is not None:
        outcome = f"error: {record.error}"
    elif record.winner_model is None:
        outcome = "draw"
    else:
        outcome = f"winner={record.winner_model}"
    print(
        f"[{record.matchup_index + 1}:{record.battle_index + 1}] "
        f"{record.p1_model} vs {record.p2_model}: {outcome}"
    )


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())
