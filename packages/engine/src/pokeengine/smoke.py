"""Smoke test: verify Showdown is reachable and a battle can start."""

from __future__ import annotations

import asyncio
import logging
import random
import string
import sys
import time
from typing import TYPE_CHECKING

from poke_env.player import RandomPlayer
from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.ps_client.server_configuration import ServerConfiguration

from pokeengine.player import AgentPlayer
from pokeengine.runner import ensure_showdown, showdown_server

if TYPE_CHECKING:
    from poke_env.battle.abstract_battle import AbstractBattle
    from poke_env.player.battle_order import BattleOrder


async def amain() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
    )
    ensure_showdown("server")
    with showdown_server("server", port=8000) as handle:
        server = ServerConfiguration(
            websocket_url=f"ws://localhost:{handle.port}/showdown/websocket",
            authentication_url="https://play.pokemonshowdown.com/action.php?",
        )
        suffix = "".join(random.choices(string.digits, k=4))

        async def debug_chooser(player: AgentPlayer, battle: AbstractBattle) -> BattleOrder:
            print(f"[debug] choose_move called for {battle.battle_tag}", flush=True)
            order = player.choose_random_move(battle)
            print(f"[debug] choose_move returning {order.message!r}", flush=True)
            return order

        a = AgentPlayer(
            account_configuration=AccountConfiguration(f"agent-a-{suffix}", None),
            server_configuration=server,
            battle_format="gen9randombattle",
            max_concurrent_battles=1,
            choose_move_for_turn=debug_chooser,
        )
        b = RandomPlayer(
            account_configuration=AccountConfiguration(f"rand-b-{suffix}", None),
            server_configuration=server,
            battle_format="gen9randombattle",
            max_concurrent_battles=1,
        )
        print("Sending challenge (AgentPlayer vs RandomPlayer)...", flush=True)
        t0 = time.monotonic()
        await a.battle_against(b, n_battles=1)
        print("Challenge sent, waiting for battle to finish...", flush=True)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if a.battles and a.battles.values():
                battle = next(iter(a.battles.values()))
                if battle._finished:
                    print(f"Battle finished after {time.monotonic() - t0:.1f}s!", flush=True)
                    print(f"  player won: {battle._won}", flush=True)
                    print(f"  turns: {battle.turn}", flush=True)
                    return 0
            await asyncio.sleep(0.5)
        print("Timeout after 120s", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
