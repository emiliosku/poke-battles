"""End-to-end demo: spawn local Showdown + run a 1v1 random battle.

Usage:
    uv run python -m pokeengine.demo
    uv run python -m pokeengine.demo --format gen9ou --timeout 180
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import string
import sys
import time

from poke_env.ps_client.server_configuration import ServerConfiguration

from pokeengine.player import AgentPlayer
from pokeengine.runner import ensure_showdown, showdown_server, wait_for_battle

logger = logging.getLogger(__name__)


def _random_suffix(length: int = 4) -> str:
    return "".join(random.choices(string.digits, k=length))


def _server_config_for_port(port: int) -> ServerConfiguration:
    return ServerConfiguration(
        websocket_url=f"ws://localhost:{port}/showdown/websocket",
        authentication_url="https://play.pokemonshowdown.com/action.php?",
    )


def _build_players(battle_format: str, port: int) -> tuple[AgentPlayer, AgentPlayer]:
    suffix = _random_suffix()
    server = _server_config_for_port(port)
    a = AgentPlayer.from_config(
        username=f"demo-a-{suffix}",
        password=None,
        battle_format=battle_format,
        server=server,
    )
    b = AgentPlayer.from_config(
        username=f"demo-b-{suffix}",
        password=None,
        battle_format=battle_format,
        server=server,
    )
    return a, b


async def _run_battle(a: AgentPlayer, b: AgentPlayer, timeout: float) -> None:
    await a.battle_against(b, n_battles=1)
    battle = next(iter(a.battles.values()))
    await wait_for_battle(a, battle.battle_tag, timeout=timeout)


async def amain(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )
    if not args.no_setup:
        ensure_showdown("server")
    port = args.port or 8000
    print(f"\nStarting Showdown on port {port} ...\n")
    with showdown_server("server", port=port) as handle:
        print(f"Showdown ready: pid={handle.pid} port={handle.port}\n")
        a, b = _build_players(args.format, handle.port)
        t0 = time.monotonic()
        try:
            await asyncio.wait_for(_run_battle(a, b, args.timeout), timeout=args.timeout + 30)
        except TimeoutError as exc:
            print(f"Battle timed out: {exc}", file=sys.stderr)
            return 2
        duration = time.monotonic() - t0
        if a._battle_winners:
            tag, winner = next(iter(a._battle_winners.items()))
            result_a = a.result_for(tag)
            print(f"Battle {tag} finished in {duration:.1f}s")
            print(f"  format: {result_a.format if result_a else 'unknown'}")
            print(f"  turns:  {result_a.turns if result_a else 0}")
            print(f"  winner: {winner or 'tie'}")
            print(f"  events (a): {len(a.events_for(tag))}")
            print(f"  events (b): {len(b.events_for(tag))}")
            evs = a.events_for(tag)
            if evs:
                kind_counts: dict[str, int] = {}
                for ev in evs:
                    kind_counts[ev.kind.value] = kind_counts.get(ev.kind.value, 0) + 1
                print(
                    f"  top event kinds: {sorted(kind_counts.items(), key=lambda kv: -kv[1])[:5]}"
                )
            return 0
        print("Battle produced no result", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a 1v1 random battle locally")
    parser.add_argument("--format", default="gen9randombattle")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--no-setup", action="store_true", help="Skip clone/install of Showdown")
    args = parser.parse_args(argv)
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
