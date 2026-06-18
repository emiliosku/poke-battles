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
    from pokeapi.orchestrator import BattleJob
    from pokellm.config import AgentConfig

from pokeapi.orchestrator import JobResult

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
        connection_manager: Any = None,
    ) -> None:
        self.showdown_dir = showdown_dir
        self.showdown_port = showdown_port or _find_showdown_free_port()
        self.handle: ShowdownHandle | None = None
        self._models: dict[str, AgentConfig] = models or {}
        self._manager = connection_manager

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
        team1_paste: str | None = None,
        team2_paste: str | None = None,
        timeout: float = 240.0,
    ) -> dict[str, Any]:
        """Run one battle and return a result dict."""
        if self.handle is None:
            self.start()
        assert self.handle is not None
        port = self.handle.port
        server = _server_config_for_port(port)
        suffix = _random_suffix()

        async def _broadcast_event(bt: str, ev: Any) -> None:
            if self._manager is not None:
                await self._manager.broadcast(bt, ev.to_dict())

        async def _broadcast_raw(bt: str, line: str) -> None:
            if self._manager is not None:
                await self._manager.broadcast_raw(bt, line)

        a = AgentPlayer(
            account_configuration=AccountConfiguration(f"{player1}-{suffix}", None),
            server_configuration=server,
            battle_format=battle_format,
            max_concurrent_battles=1,
            team=team1_paste,
            choose_move_for_turn=self.chooser_for(model1),
            on_event=_broadcast_event,
            on_raw_line=_broadcast_raw,
        )
        b = AgentPlayer(
            account_configuration=AccountConfiguration(f"{player2}-{suffix}", None),
            server_configuration=server,
            battle_format=battle_format,
            max_concurrent_battles=1,
            team=team2_paste,
            choose_move_for_turn=self.chooser_for(model2),
            on_event=_broadcast_event,
            on_raw_line=_broadcast_raw,
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
            "events": a.events_for(bid),
            "raw_log": a.raw_log_for(bid),
            "events_count": len(a.events_for(bid)),
        }


    async def run_simulation(
        self,
        *,
        mode: str,
        battle_format: str,
        team_a_id: int | None = None,
        team_b_id: int | None = None,
        team_a_paste: str | None = None,
        team_b_paste: str | None = None,
        models: list[str] | None = None,
        n_battles: int = 20,
    ) -> dict[str, Any]:
        """Run a simulation and return aggregate results."""
        models = models or ["random"]
        wins = 0
        losses = 0
        draws = 0

        if mode == "team_vs_team":
            if not models:
                models = ["random", "random"]
            model1 = models[0] if len(models) > 0 else "random"
            model2 = models[1] if len(models) > 1 else "random"
            for _ in range(n_battles):
                result = await self.run_battle(
                    battle_format=battle_format,
                    player1=f"sim-a-{_random_suffix()}",
                    player2=f"sim-b-{_random_suffix()}",
                    model1=model1,
                    model2=model2,
                    team1_paste=team_a_paste,
                    team2_paste=team_b_paste,
                )
                if "error" in result:
                    draws += 1
                elif result.get("winner", "").startswith("sim-a"):
                    wins += 1
                elif result.get("winner", "").startswith("sim-b"):
                    losses += 1
                else:
                    draws += 1
            total = wins + losses + draws
            return {
                "mode": mode,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "n_battles": n_battles,
                "win_rate": wins / total if total > 0 else 0.0,
            }

        if mode == "round_robin":
            results_map: dict[str, dict[str, Any]] = {}
            for i, m1 in enumerate(models):
                for m2 in models[i + 1:]:
                    m1_wins = 0
                    m2_wins = 0
                    for _ in range(n_battles):
                        result = await self.run_battle(
                            battle_format=battle_format,
                            player1=f"rr-{m1}-{_random_suffix()}",
                            player2=f"rr-{m2}-{_random_suffix()}",
                            model1=m1,
                            model2=m2,
                            team1_paste=None,
                            team2_paste=None,
                        )
                        if "error" in result:
                            draws += 1
                        elif result.get("winner", "").startswith(f"rr-{m1}"):
                            m1_wins += 1
                        elif result.get("winner", "").startswith(f"rr-{m2}"):
                            m2_wins += 1
                        else:
                            draws += 1
                    results_map.setdefault(m1, {"wins": 0, "losses": 0})
                    results_map.setdefault(m2, {"wins": 0, "losses": 0})
                    results_map[m1]["wins"] += m1_wins
                    results_map[m1]["losses"] += m2_wins
                    results_map[m2]["wins"] += m2_wins
                    results_map[m2]["losses"] += m1_wins
            return {
                "mode": mode,
                "results_map": results_map,
                "draws": draws,
                "n_battles": n_battles * len(models) * (len(models) - 1) // 2,
            }

        if mode == "ladder":
            entries: dict[str, dict[str, Any]] = {
                m: {"wins": 0, "losses": 0, "draws": 0, "rating": 1500, "rd": 350, "vol": 0.06}
                for m in models
            }
            for _ in range(n_battles):
                import random as _random

                m1, m2 = _random.sample(models, 2)
                result = await self.run_battle(
                    battle_format=battle_format,
                    player1=f"ladder-{m1}-{_random_suffix()}",
                    player2=f"ladder-{m2}-{_random_suffix()}",
                    model1=m1,
                    model2=m2,
                    team1_paste=None,
                    team2_paste=None,
                )
                if "error" in result:
                    entries[m1]["draws"] += 1
                    entries[m2]["draws"] += 1
                else:
                    w = result.get("winner", "")
                    if w.startswith(f"ladder-{m1}"):
                        entries[m1]["wins"] += 1
                        entries[m2]["losses"] += 1
                    elif w.startswith(f"ladder-{m2}"):
                        entries[m2]["wins"] += 1
                        entries[m1]["losses"] += 1
                    else:
                        entries[m1]["draws"] += 1
                        entries[m2]["draws"] += 1
            return {
                "mode": mode,
                "entries": entries,
                "n_battles": n_battles,
            }

        return {"mode": mode, "error": f"Unknown mode: {mode}"}

    async def run_job(self, job: BattleJob) -> JobResult:
        """Bridge from orchestrator BattleJob to BattleService.run_battle."""
        try:
            result = await self.run_battle(
                battle_format=job.format,
                player1=job.player1,
                player2=job.player2,
                model1=job.model1,
                model2=job.model2,
                team1_paste=job.team1_paste,
                team2_paste=job.team2_paste,
            )
            if "error" in result:
                return JobResult(
                    job_id=job.id,
                    battle_id=result.get("battle_id"),
                    winner=None,
                    turns=result.get("turns", 0),
                    duration_s=result.get("duration_s", 0.0),
                )
            return JobResult(
                job_id=job.id,
                battle_id=result.get("battle_id"),
                winner=result.get("winner"),
                turns=result.get("turns", 0),
                duration_s=result.get("duration_s", 0.0),
                events=result.get("events", ()),
                raw_log=result.get("raw_log", ""),
            )
        except Exception as exc:
            logger.exception("run_job failed: %s", exc)
            return JobResult(job_id=job.id, winner=None, turns=0, duration_s=0.0)


__all__ = ["BattleService", "_random_chooser", "build_chooser"]
