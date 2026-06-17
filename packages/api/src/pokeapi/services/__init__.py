"""Battle service: orchestrate a single battle using pokeengine.

This bridges the API orchestrator (which dispatches jobs) and the actual
Showdown server + AgentPlayer (which do the work). LLM-backed choosers are
plugged in when a :class:`pokellm.config.AgentConfig` is registered for the
model name; otherwise a random chooser is used.
"""

from __future__ import annotations

import asyncio
import logging
import random
import string
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.ps_client.server_configuration import ServerConfiguration

from pokeengine.player import AgentPlayer
from pokeengine.runner import (
    ShowdownHandle,
    ensure_showdown,
    showdown_server,
)

if TYPE_CHECKING:
    from pokellm.config import AgentConfig

logger = logging.getLogger(__name__)


def _random_suffix(length: int = 4) -> str:
    return "".join(random.choices(string.digits, k=length))


def _server_config_for_port(port: int) -> ServerConfiguration:
    return ServerConfiguration(
        websocket_url=f"ws://localhost:{port}/showdown/websocket",
        authentication_url="https://play.pokemonshowdown.com/action.php?",
    )


def _random_chooser(player: AgentPlayer, battle: Any) -> Any:
    return player.choose_random_move(battle)


def _build_llm_chooser(
    model_name: str,
    config: AgentConfig,
) -> Callable[[AgentPlayer, Any], Any]:
    """Construct an LLM-backed move chooser for ``AgentPlayer``."""
    from pokeengine.player import battle_to_state_dict
    from pokellm.agent import LLMAgent
    from pokellm.clients import LLMClient

    agent = LLMAgent(config=config, client=LLMClient(config=config))

    async def chooser(player: AgentPlayer, battle: Any) -> Any:
        try:
            state = battle_to_state_dict(battle)
            order = await agent.turn(state)
            if order.action == "choose_move" and order.move_id:
                from poke_env.battle.move import Move

                normalized = order.move_id.lower().replace(" ", "").replace("-", "")
                for move in battle.available_moves:
                    if move.id == normalized:
                        return player.create_order(move)
                return player.create_order(Move("struggle", gen=9))
            if order.action == "choose_switch" and order.pokemon_name:
                from poke_env.battle.pokemon import Pokemon

                target = order.pokemon_name.lower()
                for mon in battle.available_switches:
                    if mon.species.lower() == target:
                        return player.create_order(mon)
                return player.create_order(Pokemon(species=target, gen=9))
        except Exception:
            logger.exception("LLM chooser %s failed; falling back to random", model_name)
        return player.choose_random_move(battle)

    return chooser


def build_chooser(
    model_name: str,
    config: AgentConfig | None,
) -> Callable[[AgentPlayer, Any], Any]:
    """Build the chooser for a given model name.

    - ``config=None`` → random
    - ``tier=mock`` → random
    - otherwise → LLM via pokellm
    """
    if config is None or config.tier.value == "mock":
        return _random_chooser
    return _build_llm_chooser(model_name, config)


def _find_showdown_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class BattleService:
    """High-level service: run a single battle end-to-end."""

    def __init__(
        self,
        *,
        showdown_dir: str = "server",
        showdown_port: int | None = None,
        models: dict[str, AgentConfig] | None = None,
    ) -> None:
        self.showdown_dir = showdown_dir
        self.showdown_port = showdown_port or _find_showdown_free_port()
        self.handle: ShowdownHandle | None = None
        self._models: dict[str, AgentConfig] = models or {}

    def start(self) -> ShowdownHandle:
        ensure_showdown(self.showdown_dir)
        if self.handle is None:
            self.handle = showdown_server(self.showdown_dir, port=self.showdown_port).__enter__()
        return self.handle

    def stop(self) -> None:
        if self.handle is not None:
            self.handle.stop()
            self.handle = None

    def chooser_for(self, model_name: str) -> Callable[[AgentPlayer, Any], Any]:
        return build_chooser(model_name, self._models.get(model_name))

    async def run_battle(
        self,
        *,
        battle_format: str,
        player1: str,
        player2: str,
        model1: str,
        model2: str,
        timeout: float = 240.0,
    ) -> dict[str, Any]:
        """Run one battle and return a result dict."""
        if self.handle is None:
            self.start()
        assert self.handle is not None
        port = self.handle.port
        server = _server_config_for_port(port)
        suffix = _random_suffix()
        a = AgentPlayer(
            account_configuration=AccountConfiguration(f"{player1}-{suffix}", None),
            server_configuration=server,
            battle_format=battle_format,
            max_concurrent_battles=1,
            choose_move_for_turn=self.chooser_for(model1),
        )
        b = AgentPlayer(
            account_configuration=AccountConfiguration(f"{player2}-{suffix}", None),
            server_configuration=server,
            battle_format=battle_format,
            max_concurrent_battles=1,
            choose_move_for_turn=self.chooser_for(model2),
        )
        t0 = time.monotonic()
        try:
            await asyncio.wait_for(a.battle_against(b, n_battles=1), timeout=timeout)
        except TimeoutError:
            return {"error": "battle timed out", "duration_s": time.monotonic() - t0}
        bid = next(iter(a._battle_winners.keys()), None)
        duration = time.monotonic() - t0
        if bid is None:
            return {"error": "battle did not produce a result", "duration_s": duration}
        return {
            "battle_id": bid,
            "winner": a._battle_winners.get(bid),
            "turns": a._battle_turns.get(bid, 0),
            "duration_s": duration,
            "format": battle_format,
            "events_count": len(a.events_for(bid)),
        }


__all__ = ["BattleService", "_random_chooser", "build_chooser"]
