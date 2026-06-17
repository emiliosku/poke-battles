"""The Pokémon LLM agent.

:class:`LLMAgent` glues together the LLM client, prompt rendering, memory, and
the poke-env :class:`AgentPlayer` interface. It does NOT touch poke-env types
directly — instead it consumes a state dict (typically produced by
:func:`pokeengine.battle_to_state_dict`) and returns a :class:`LLMDecision`.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pokellm.clients import LLMClient, LLMDecision
from pokellm.config import AgentConfig
from pokellm.memory import Memory
from pokellm.prompts import PROMPT_VERSION, render_system_prompt, render_user_prompt

logger = logging.getLogger(__name__)

StateFormatter = Callable[[Any], str]
DecisionToOrder = Callable[[LLMDecision], "Order"]


@dataclass(frozen=True, slots=True)
class Order:
    """A normalized order: either a move id or a switch target, plus an order string."""

    action: str
    order: str
    move_id: str | None = None
    pokemon_name: str | None = None
    commentary: str = ""


@dataclass
class LLMAgent:
    """Drives a single battle using an :class:`LLMClient` + memory + prompts."""

    config: AgentConfig
    client: LLMClient
    memory: Memory = field(default_factory=Memory)
    strategy_profile: str = "balanced"
    fallback_random: bool = True
    max_retries: int = 2
    _last_state: dict[str, Any] = field(default_factory=dict, init=False)
    _state_formatter: StateFormatter | None = field(default=None, init=False)
    _decision_to_order: DecisionToOrder | None = field(default=None, init=False)

    def bind(self, *, state_formatter: StateFormatter, decision_to_order: DecisionToOrder) -> None:
        """Inject the state and order bridges (called by the player wrapper)."""
        self._state_formatter = state_formatter
        self._decision_to_order = decision_to_order

    async def decide(self, state: Any) -> LLMDecision:
        """Run one turn: format state → render prompt → call LLM → return decision."""
        formatter = self._state_formatter or _default_state_formatter
        state_str = formatter(state)
        system = render_system_prompt(profile=_profile_for(self.strategy_profile))
        user = render_user_prompt(
            state_str,
            opponent_profile=self.memory.opponent.to_prompt_block(),
            short_term_memory=self.memory.short_term.to_prompt_block(),
        )
        decision = await self.client.decide(system_prompt=system, user_prompt=user)
        if decision.action == "choose_move" and decision.move_id:
            self.memory.note_action(f"Used move: {decision.move_id}")
        elif decision.action == "choose_switch" and decision.pokemon_name:
            self.memory.note_action(f"Switched to: {decision.pokemon_name}")
        return decision

    async def turn(self, state: Any) -> Order:
        """Run a turn, returning a normalized :class:`Order`."""
        bridge = self._decision_to_order or _default_decision_to_order
        for attempt in range(self.max_retries + 1):
            decision = await self.decide(state)
            if decision.action in {"choose_move", "choose_switch"}:
                return bridge(decision)
            logger.warning("LLM returned %r; retrying (attempt %d)", decision.action, attempt + 1)
        if self.fallback_random:
            return Order(action="__fallback__", order="/choose default")
        raise RuntimeError(f"LLM agent {self.config.name!r} failed after retries")


def _profile_for(name: str) -> str:
    from pokellm.prompts import strategy_profile as _sp

    return _sp(name)


def _default_state_formatter(state: Any) -> str:
    if isinstance(state, str):
        return state
    if isinstance(state, dict):
        result: object = state.get("formatted", _stringify_dict(state))
        return str(result)
    return str(state)


def _stringify_dict(d: dict[str, Any]) -> str:
    text: str = "\n".join(f"{k}: {v}" for k, v in d.items())
    return text


def _default_decision_to_order(decision: LLMDecision) -> Order:
    if decision.action == "choose_move" and decision.move_id:
        return Order(
            action="choose_move",
            order=f"/choose move {decision.move_id}",
            move_id=decision.move_id,
            commentary=decision.commentary,
        )
    if decision.action == "choose_switch" and decision.pokemon_name:
        return Order(
            action="choose_switch",
            order=f"/choose switch {decision.pokemon_name}",
            pokemon_name=decision.pokemon_name,
            commentary=decision.commentary,
        )
    return Order(action="__fallback__", order="/choose default", commentary=decision.commentary)


_NORMALIZE = re.compile(r"[^a-z0-9]+")


def normalize_move_id(name: str) -> str:
    """Lowercase, strip spaces/hyphens, keep alphanumerics only."""
    return _NORMALIZE.sub("", name.lower())


def normalize_species(name: str) -> str:
    return _NORMALIZE.sub("", name.lower())


__all__ = [
    "PROMPT_VERSION",
    "LLMAgent",
    "Order",
    "normalize_move_id",
    "normalize_species",
]
