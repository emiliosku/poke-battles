"""Move chooser construction and per-battle chooser metrics."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from poke_env.battle.double_battle import DoubleBattle

from pokeengine.player import AgentPlayer

if TYPE_CHECKING:
    from pokellm.config import AgentConfig

logger = logging.getLogger(__name__)

# Per-model chooser stats. Each entry is a dict that the LLM/heuristic
# chooser increments as it's called. ``_pop_chooser_stats`` reads and clears
# these dicts after each battle so the bench harness can collect them.
agent_stats: dict[str, dict[str, int]] = {}
DecisionRecorder = Callable[[Any, str, str | None, str], None]


def _random_chooser(player: AgentPlayer, battle: Any) -> Any:
    return player.choose_random_move(battle)


def _heuristic_chooser(player: AgentPlayer, battle: Any) -> Any:
    """Heuristic-based chooser. Returns a poke-env BattleOrder."""
    from pokeengine.player import state_from_battle
    from pokellm.heuristic import ActionKind, pick

    h_stats = agent_stats.setdefault("heuristic", {"heuristic_calls": 0, "fallback_random": 0})
    h_stats.setdefault("heuristic_calls", 0)
    h_stats.setdefault("fallback_random", 0)
    if isinstance(battle, DoubleBattle):
        # The heuristic selects one action and has no target model; poke-env's
        # random chooser composes a complete legal order for both slots.
        h_stats["fallback_random"] += 1
        return player.choose_random_move(battle)
    state = state_from_battle(battle)
    if not state.player or not state.opponent:
        h_stats["fallback_random"] += 1
        return player.choose_random_move(battle)
    try:
        candidate = pick(state)
    except ValueError as exc:
        h_stats["fallback_random"] += 1
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
    on_rationale: DecisionRecorder | None = None,
) -> Callable[[AgentPlayer, Any], Any]:
    """Construct an LLM-backed move chooser for ``AgentPlayer``."""
    from pokeengine.player import state_from_battle
    from pokellm.agent import LLMAgent
    from pokellm.clients import LLMClient
    from pokellm.prompts import render_system_prompt, render_user_prompt
    from pokellm.state_render import format_battle_state

    agent = LLMAgent(config=config, client=LLMClient(config=config))
    stats: dict[str, int] = {"llm_calls": 0, "fallback_random": 0}
    agent_stats[model_name] = stats

    if not hybrid:

        async def legacy_chooser(player: AgentPlayer, battle: Any) -> Any:
            stats["llm_calls"] += 1
            if isinstance(battle, DoubleBattle):
                stats["fallback_random"] += 1
                return player.choose_random_move(battle)
            try:
                state = state_from_battle(battle)
                decision = await agent.client.decide(
                    system_prompt=render_system_prompt(),
                    user_prompt=render_user_prompt(format_battle_state(state)),
                )
                _record_rationale(
                    on_rationale,
                    battle,
                    decision.action,
                    decision.move_id or decision.pokemon_name,
                    decision.commentary,
                )
                order = _legacy_decision_to_order(decision)
            except Exception:
                logger.exception("LLM chooser %s failed; falling back to random", model_name)
                stats["fallback_random"] += 1
                return player.choose_random_move(battle)
            return _resolve_order(player, order, battle)

        return legacy_chooser

    async def chooser(player: AgentPlayer, battle: Any) -> Any:
        stats["llm_calls"] += 1
        if isinstance(battle, DoubleBattle):
            stats["fallback_random"] += 1
            return player.choose_random_move(battle)
        try:
            state = state_from_battle(battle)
            order = await agent.turn(state)
            _record_rationale(
                on_rationale,
                battle,
                order.action,
                order.move_id or order.pokemon_name,
                order.commentary,
            )
            if order.action == "choose_move" and order.move_id:
                from poke_env.battle.move import Move

                normalized = order.move_id.lower().replace(" ", "").replace("-", "")
                for move in battle.available_moves:
                    if move.id == normalized:
                        return player.create_order(move, terastallize=order.terastallize)
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
    terastallize: bool = False


def _legacy_decision_to_order(decision: Any) -> _Order:
    if decision.action == "choose_move" and decision.move_id:
        return _Order(
            action="choose_move",
            move_id=decision.move_id,
            terastallize=bool(getattr(decision, "terastallize", False)),
        )
    if decision.action == "choose_switch" and decision.pokemon_name:
        return _Order(action="choose_switch", pokemon_name=decision.pokemon_name)
    return _Order(action="__fallback__")


def _record_rationale(
    recorder: DecisionRecorder | None,
    battle: Any,
    action: str,
    target: str | None,
    commentary: str,
) -> None:
    if recorder is not None and commentary.strip():
        recorder(battle, action, target, commentary.strip())


def _resolve_order(player: AgentPlayer, order: _Order, battle: Any) -> Any:
    if order.action == "choose_move" and order.move_id:
        from poke_env.battle.move import Move

        normalized = order.move_id.lower().replace(" ", "").replace("-", "")
        for move in battle.available_moves:
            if move.id == normalized:
                return player.create_order(move, terastallize=order.terastallize)
        return player.create_order(Move("struggle", gen=9))
    if order.action == "choose_switch" and order.pokemon_name:
        from poke_env.battle.pokemon import Pokemon

        target = order.pokemon_name.lower()
        for mon in battle.available_switches:
            if mon.species.lower() == target:
                return player.create_order(mon)
        return player.create_order(Pokemon(species=target, gen=9))
    return player.choose_random_move(battle)


def _build_rl_chooser(model_name: str) -> Callable[[AgentPlayer, Any], Any]:
    """Construct an RL policy chooser with a random-move fallback."""
    import os

    from pokerl.inference import make_rl_chooser

    rl_stats: dict[str, int] = {"rl_calls": 0, "fallback_random": 0}
    agent_stats[model_name] = rl_stats
    model_path = os.environ.get("POKERL_MODEL_PATH")
    if not model_path:
        logger.error(
            "RL chooser %s requested but POKERL_MODEL_PATH is not set; "
            "all calls will fall back to random. Train a model first with "
            "`pokerl-train` and set POKERL_MODEL_PATH=/abs/path/to/final_model.zip`.",
            model_name,
        )

        async def unconfigured_chooser(player: AgentPlayer, battle: Any) -> Any:
            rl_stats["rl_calls"] += 1
            rl_stats["fallback_random"] += 1
            return player.choose_random_move(battle)

        return unconfigured_chooser

    try:
        chooser = make_rl_chooser(model_path, deterministic=True)
    except Exception:
        logger.exception(
            "RL chooser %s failed to load model from %s; falling back to random",
            model_name,
            model_path,
        )

        async def broken_chooser(player: AgentPlayer, battle: Any) -> Any:
            rl_stats["rl_calls"] += 1
            rl_stats["fallback_random"] += 1
            return player.choose_random_move(battle)

        return broken_chooser

    async def wrapped_chooser(player: AgentPlayer, battle: Any) -> Any:
        rl_stats["rl_calls"] += 1
        try:
            return await chooser(player, battle)
        except Exception:
            logger.exception("RL chooser %s failed; falling back to random", model_name)
            rl_stats["fallback_random"] += 1
            return player.choose_random_move(battle)

    return wrapped_chooser


def build_chooser(
    model_name: str,
    config: AgentConfig | None,
    *,
    on_rationale: DecisionRecorder | None = None,
) -> Callable[[AgentPlayer, Any], Any]:
    """Build the configured chooser, falling back to random as appropriate."""
    if model_name == "heuristic":
        return _heuristic_chooser
    if model_name == "rl" or (config is not None and config.mode == "rl"):
        return _build_rl_chooser(model_name)
    if config is None or config.tier.value == "mock":
        return _random_chooser
    if config.mode == "heuristic":
        return _heuristic_chooser
    if config.mode == "legacy":
        return _build_llm_chooser(model_name, config, hybrid=False, on_rationale=on_rationale)
    return _build_llm_chooser(model_name, config, hybrid=True, on_rationale=on_rationale)


def _pop_chooser_stats(model_names: list[str]) -> dict[str, dict[str, int]]:
    """Read and clear per-model chooser stats."""
    out: dict[str, dict[str, int]] = {}
    for name in model_names:
        stats = agent_stats.get(name)
        if stats is None:
            continue
        out[name] = dict(stats)
        stats.clear()
    return out
