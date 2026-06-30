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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.ps_client.server_configuration import ServerConfiguration

from pokeapi.services.practice import PracticeActionController, decide_points
from pokecore.teams import normalize_team_paste_for_showdown
from pokeengine.events import Event, EventKind
from pokeengine.player import AgentPlayer
from pokeengine.runner import (
    ShowdownHandle,
    ensure_showdown,
    start_showdown,
)

if TYPE_CHECKING:
    from pokeapi.orchestrator import BattleJob
    from pokellm.config import AgentConfig

from pokeapi.orchestrator import JobResult

logger = logging.getLogger(__name__)

# Per-model chooser stats. Each entry is a dict that the LLM/heuristic
# chooser increments as it's called. ``run_battle`` reads and clears
# these dicts after each battle so the bench harness can collect them.
agent_stats: dict[str, dict[str, int]] = {}


def _random_suffix(length: int = 4) -> str:
    return "".join(random.choices(string.digits, k=length))


def _showdown_account_name(name: str, suffix: str, side: str) -> str:
    normalized = "".join(ch for ch in name.lower() if ch.isalnum()) or "player"
    account_suffix = f"{side}{suffix}"
    return f"{normalized[: 18 - len(account_suffix)]}{account_suffix}"


def _server_config_for_port(port: int) -> ServerConfiguration:
    return ServerConfiguration(
        websocket_url=f"ws://localhost:{port}/showdown/websocket",
        authentication_url="https://play.pokemonshowdown.com/action.php?",
    )


def _random_chooser(player: AgentPlayer, battle: Any) -> Any:
    return player.choose_random_move(battle)


def _heuristic_chooser(player: AgentPlayer, battle: Any) -> Any:
    """Heuristic-based chooser. Returns a poke-env BattleOrder."""
    from pokeengine.player import state_from_battle
    from pokellm.heuristic import ActionKind, pick

    h_stats = agent_stats.setdefault("heuristic", {"heuristic_calls": 0, "fallback_random": 0})
    h_stats.setdefault("heuristic_calls", 0)
    h_stats.setdefault("fallback_random", 0)
    state = state_from_battle(battle)
    if not state.player or not state.opponent:
        h_stats["fallback_random"] += 1
        return player.choose_random_move(battle)
    try:
        candidate = pick(state)
    except ValueError as exc:
        h_stats["fallback_random"] += 1
        # One-shot debug log: dump the state so we can see why pick is failing.
        if not h_stats.get("_logged_failure"):
            h_stats["_logged_failure"] = 1
            logger.warning(
                "heuristic pick failed: %s. state.player=%d state.opponent=%d "
                "active_player=%s active_opp=%s",
                exc,
                len(state.player),
                len(state.opponent),
                state.player[0].species if state.player else None,
                state.opponent[0].species if state.opponent else None,
            )
        return player.choose_random_move(battle)
    h_stats["heuristic_calls"] += 1
    if candidate.kind == ActionKind.MOVE:
        normalized = candidate.target_id.lower().replace(" ", "").replace("-", "")
        for move in battle.available_moves:
            if move.id == normalized:
                return player.create_order(move)
        return player.choose_random_move(battle)
    # Switch
    target = candidate.target_id.lower()
    for mon in battle.available_switches:
        if mon.species.lower() == target:
            return player.create_order(mon)
    return player.choose_random_move(battle)


def _build_llm_chooser(
    model_name: str,
    config: AgentConfig,
    *,
    hybrid: bool = True,
) -> Callable[[AgentPlayer, Any], Any]:
    """Construct an LLM-backed move chooser for ``AgentPlayer``.

    When ``hybrid=True`` (the default) the agent sees the heuristic's
    top-3 candidate actions as part of the prompt and can use the
    multi-turn tool loop. When ``hybrid=False`` it falls back to the
    pre-Phase-4 single-shot behaviour for A/B comparison.
    """
    from pokeengine.player import state_from_battle
    from pokellm.agent import LLMAgent
    from pokellm.clients import LLMClient
    from pokellm.prompts import (
        render_system_prompt as _render_system_prompt,
    )
    from pokellm.prompts import (
        render_user_prompt as _render_user_prompt,
    )
    from pokellm.state_render import format_battle_state as _format_battle_state

    agent = LLMAgent(config=config, client=LLMClient(config=config))
    # Per-battle chooser-call counter, closed over by the returned callable.
    # Read by ``run_battle`` after the battle ends via ``agent._stats``.
    stats: dict[str, int] = {
        "llm_calls": 0,
        "fallback_random": 0,
    }
    agent_stats[model_name] = stats

    if not hybrid:
        # Legacy single-shot mode: keep the system/user prompts compatible
        # with the pre-Phase-4 layout. We still pass a state_str but the
        # agent's decide_loop won't be exercised.
        async def legacy_chooser(player: AgentPlayer, battle: Any) -> Any:
            stats["llm_calls"] += 1
            try:
                state = state_from_battle(battle)
                state_str = _format_battle_state(state)
                system = _render_system_prompt()
                user = _render_user_prompt(state_str)
                decision = await agent.client.decide(system_prompt=system, user_prompt=user)
                order = _legacy_decision_to_order(decision)
            except Exception:
                logger.exception("LLM chooser %s failed; falling back to random", model_name)
                stats["fallback_random"] += 1
                return player.choose_random_move(battle)
            return _resolve_order(player, order, battle)

        return legacy_chooser

    async def chooser(player: AgentPlayer, battle: Any) -> Any:
        stats["llm_calls"] += 1
        try:
            state = state_from_battle(battle)
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
            stats["fallback_random"] += 1
        return player.choose_random_move(battle)

    return chooser


@dataclass(frozen=True, slots=True)
class _Order:
    action: str
    move_id: str | None = None
    pokemon_name: str | None = None


def _legacy_decision_to_order(decision: Any) -> _Order:
    if decision.action == "choose_move" and decision.move_id:
        return _Order(action="choose_move", move_id=decision.move_id)
    if decision.action == "choose_switch" and decision.pokemon_name:
        return _Order(action="choose_switch", pokemon_name=decision.pokemon_name)
    return _Order(action="__fallback__")


def _resolve_order(player: AgentPlayer, order: _Order, battle: Any) -> Any:
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
    return player.choose_random_move(battle)


def build_chooser(
    model_name: str,
    config: AgentConfig | None,
) -> Callable[[AgentPlayer, Any], Any]:
    """Build the chooser for a given model name.

    Resolution order:

    - ``model_name == "heuristic"`` or ``config.mode == "heuristic"`` →
      deterministic heuristic baseline.
    - ``config is None`` or ``tier=mock`` → random.
    - ``config.mode == "legacy"`` → single-shot LLM (pre-Phase-4 behaviour).
    - ``config.mode == "hybrid"`` (default) → meta-reasoner over the
      heuristic's shortlist.
    """
    if model_name == "heuristic":
        return _heuristic_chooser
    if config is None or config.tier.value == "mock":
        return _random_chooser
    if config.mode == "heuristic":
        return _heuristic_chooser
    if config.mode == "legacy":
        return _build_llm_chooser(model_name, config, hybrid=False)
    return _build_llm_chooser(model_name, config, hybrid=True)


def _winner_from_events(events: list[Any]) -> str | None:
    for event in reversed(events):
        if getattr(event.kind, "value", event.kind) == "battle_end":
            if event.detail and event.detail != "tie":
                return str(event.detail)
            return None
    return None


def _pop_chooser_stats(model_names: list[str]) -> dict[str, dict[str, int]]:
    """Read and clear per-model chooser stats. Returns a fresh dict."""
    out: dict[str, dict[str, int]] = {}
    for name in model_names:
        stats = agent_stats.get(name)
        if stats is None:
            continue
        out[name] = dict(stats)
        stats.clear()
    # Heuristic uses a fixed name; surface it under each model that used it.
    if (
        "heuristic" in agent_stats
        and agent_stats["heuristic"]
        and any(n not in out for n in model_names)
    ):
        pass  # only attach if a chooser actually wrote to it
    return out


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
            self.handle = start_showdown(self.showdown_dir, port=self.showdown_port)
        return self.handle

    def stop(self) -> None:
        if self.handle is not None:
            self.handle.stop()
            self.handle = None

    def chooser_for(self, model_name: str) -> Callable[[AgentPlayer, Any], Any]:
        return build_chooser(model_name, self._models.get(model_name))

    def websocket_url(self) -> str | None:
        if self.handle is None:
            return None
        return f"ws://localhost:{self.handle.port}/showdown/websocket"

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

        a_name = _showdown_account_name(player1, suffix, "a")
        b_name = _showdown_account_name(player2, suffix, "b")
        a = AgentPlayer(
            account_configuration=AccountConfiguration(a_name, None),
            server_configuration=server,
            battle_format=battle_format,
            max_concurrent_battles=1,
            team=normalize_team_paste_for_showdown(team1_paste),
            choose_move_for_turn=self.chooser_for(model1),
            on_event=_broadcast_event,
            on_raw_line=_broadcast_raw,
        )
        b = AgentPlayer(
            account_configuration=AccountConfiguration(b_name, None),
            server_configuration=server,
            battle_format=battle_format,
            max_concurrent_battles=1,
            team=normalize_team_paste_for_showdown(team2_paste),
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
        events = a.events_for(bid)
        winner = a._battle_winners.get(bid) or _winner_from_events(events)
        if winner == a_name:
            winner_side = "p1"
        elif winner == b_name:
            winner_side = "p2"
        else:
            winner_side = "tie"
        return {
            "battle_id": bid,
            "winner": winner,
            "winner_side": winner_side,
            "turns": a._battle_turns.get(bid, 0),
            "duration_s": duration,
            "format": battle_format,
            "events": events,
            "raw_log": a.raw_log_for(bid),
            "events_count": len(events),
            "chooser_stats": _pop_chooser_stats([model1, model2]),
        }

    async def run_practice_battle(
        self,
        *,
        app_battle_id: str,
        battle_format: str,
        player: str,
        ai_player: str,
        ai_model: str,
        action_controller: PracticeActionController,
        player_team_paste: str | None = None,
        ai_team_paste: str | None = None,
        total_timer_s: int | None = None,
        timeout: float = 240.0,
    ) -> dict[str, Any]:
        """Run one user-vs-AI practice battle without rating side effects."""
        if self.handle is None:
            self.start()
        assert self.handle is not None
        server = _server_config_for_port(self.handle.port)
        suffix = _random_suffix()
        player_username = _showdown_account_name(player, suffix, "a")
        ai_username = _showdown_account_name(ai_player, suffix, "b")

        async def _broadcast_event(_bt: str, ev: Any) -> None:
            if self._manager is not None:
                await self._manager.broadcast(app_battle_id, ev.to_dict())

        async def _broadcast_raw(_bt: str, line: str) -> None:
            if self._manager is not None:
                await self._manager.broadcast_raw(app_battle_id, line)

        async def _human_chooser(_player: AgentPlayer, battle: Any) -> Any:
            return await action_controller.request_choice(app_battle_id, battle)

        def _human_teampreview(battle: Any) -> Any:
            return action_controller.request_team_preview(app_battle_id, battle)

        human = AgentPlayer(
            account_configuration=AccountConfiguration(player_username, None),
            server_configuration=server,
            battle_format=battle_format,
            max_concurrent_battles=1,
            team=normalize_team_paste_for_showdown(player_team_paste),
            choose_move_for_turn=_human_chooser,
            on_event=_broadcast_event,
            on_raw_line=_broadcast_raw,
        )
        human.teampreview = _human_teampreview  # type: ignore[method-assign]
        ai = AgentPlayer(
            account_configuration=AccountConfiguration(ai_username, None),
            server_configuration=server,
            battle_format=battle_format,
            max_concurrent_battles=1,
            team=normalize_team_paste_for_showdown(ai_team_paste),
            choose_move_for_turn=self.chooser_for(ai_model),
            on_event=_broadcast_event,
            on_raw_line=_broadcast_raw,
        )
        t0 = time.monotonic()
        battle_task = asyncio.create_task(human.battle_against(ai, n_battles=1))
        battle_timeout = total_timer_s if total_timer_s is not None else timeout
        timed_out_by_points = False
        try:
            await asyncio.wait_for(battle_task, timeout=battle_timeout)
        except TimeoutError:
            timed_out_by_points = total_timer_s is not None
            battle_task.cancel()
            try:
                await battle_task
            except (asyncio.CancelledError, Exception):
                pass
            if not timed_out_by_points:
                return {"error": "practice battle timed out", "duration_s": time.monotonic() - t0}
        bid = next(iter(human._events.keys()), None) or next(
            iter(human._battle_winners.keys()), None
        )
        duration = time.monotonic() - t0
        if bid is None:
            return {"error": "practice battle did not start", "duration_s": duration}
        events = human.events_for(bid)
        raw_log = human.raw_log_for(bid)
        turns = human._battle_turns.get(bid, 0)
        winner = human._battle_winners.get(bid) or _winner_from_events(events)
        result_status = "finished"
        summary: dict[str, Any] = {}
        if action_controller.user_timed_out(app_battle_id):
            result_status = "user_timeout_loss"
            winner = ai_username
            events.append(
                Event(
                    kind=EventKind.MESSAGE,
                    turn=turns,
                    detail="User move timer expired; practice battle forfeited.",
                )
            )
        elif timed_out_by_points:
            ai_bid = next(iter(ai._events.keys()), bid)
            decision = decide_points(
                player_name=player_username,
                ai_name=ai_username,
                player_raw_log=raw_log,
                ai_raw_log=ai.raw_log_for(ai_bid),
            )
            result_status = "timed_out_draw" if decision.winner is None else "timed_out_points"
            winner = decision.winner
            summary = {
                "point_decision_reason": decision.reason,
                "player_score": {
                    "remaining": decision.player_score.remaining,
                    "hp_percent_total": decision.player_score.hp_percent_total,
                },
                "ai_score": {
                    "remaining": decision.ai_score.remaining,
                    "hp_percent_total": decision.ai_score.hp_percent_total,
                },
            }
            events.append(
                Event(
                    kind=EventKind.MESSAGE,
                    turn=turns,
                    detail=f"Practice timer expired; result decided by {decision.reason}.",
                    raw=summary,
                )
            )
        return {
            "battle_id": bid,
            "winner": winner,
            "turns": turns,
            "duration_s": duration,
            "format": battle_format,
            "events": events,
            "raw_log": raw_log,
            "events_count": len(events),
            "status": result_status,
            "summary": summary,
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
        progress_callback: Callable[[int, int, int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Run a simulation and return aggregate results.

        ``progress_callback`` is invoked after each battle with
        ``(battles_done, wins, losses, draws)``. For ``round_robin`` and
        ``ladder`` modes, ``wins``/``losses`` are summed across all
        models in the running tally.
        """
        models = models or ["random"]
        wins = 0
        losses = 0
        draws = 0

        def _emit(battles_done: int) -> None:
            if progress_callback is not None:
                progress_callback(battles_done, wins, losses, draws)

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
                else:
                    side = result.get("winner_side")
                    if side == "p1":
                        wins += 1
                    elif side == "p2":
                        losses += 1
                    else:
                        draws += 1
                _emit(wins + losses + draws)
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
                for m2 in models[i + 1 :]:
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
                        else:
                            side = result.get("winner_side")
                            if side == "p1":
                                m1_wins += 1
                                wins += 1
                            elif side == "p2":
                                m2_wins += 1
                                losses += 1
                            else:
                                draws += 1
                        _emit(wins + losses + draws)
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
                    draws += 2
                else:
                    side = result.get("winner_side")
                    if side == "p1":
                        entries[m1]["wins"] += 1
                        entries[m2]["losses"] += 1
                        wins += 1
                        losses += 1
                    elif side == "p2":
                        entries[m2]["wins"] += 1
                        entries[m1]["losses"] += 1
                        wins += 1
                        losses += 1
                    else:
                        entries[m1]["draws"] += 1
                        entries[m2]["draws"] += 1
                        draws += 2
                _emit(wins + losses + draws)
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
