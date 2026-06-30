"""The Pokémon LLM agent — meta-reasoner over a heuristic shortlist.

:class:`LLMAgent` glues together the LLM client, prompt rendering, memory,
and the deterministic :mod:`pokellm.heuristic` shortlist. The flow per
turn:

1. Format the state (default formatter handles ``BattleState`` and dict).
2. Build the heuristic's top-3 candidate actions.
3. Render the system + user prompt (with previous-turn plan scratchpad).
4. Call :meth:`LLMClient.decide_loop` — the LLM may call
   ``evaluate_candidate`` / ``propose_alternative`` / type-chart tools
   before finally calling ``choose_move`` or ``choose_switch``.
5. Persist the plan-for-next-turn scratchpad and update short-term memory.

The agent does NOT touch poke-env types directly — it consumes a state
value (typically :class:`pokecore.state.BattleState`) and returns a
:class:`LLMDecision`.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pokecore.state import BattleState
from pokellm.clients import LLMClient, LLMDecision
from pokellm.config import AgentConfig
from pokellm.heuristic import ActionKind, Candidate, shortlist
from pokellm.memory import Memory
from pokellm.prompts import (
    PROMPT_VERSION,
    render_system_prompt,
    render_user_prompt,
)
from pokellm.state_render import default_state_formatter

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
    """Drives a single battle using an :class:`LLMClient` + memory + heuristic shortlist."""

    config: AgentConfig
    client: LLMClient
    memory: Memory = field(default_factory=Memory)
    strategy_profile: str = "balanced"
    fallback_random: bool = True
    max_retries: int = 2
    max_iterations: int = 4
    _last_state: dict[str, Any] = field(default_factory=dict, init=False)
    _state_formatter: StateFormatter | None = field(default=None, init=False)
    _decision_to_order: DecisionToOrder | None = field(default=None, init=False)
    _last_plan: str = field(default="", init=False)

    def bind(self, *, state_formatter: StateFormatter, decision_to_order: DecisionToOrder) -> None:
        """Inject the state and order bridges (called by the player wrapper)."""
        self._state_formatter = state_formatter
        self._decision_to_order = decision_to_order

    async def decide(self, state: Any) -> LLMDecision:
        """Run one turn: format state → build shortlist → loop → return decision."""
        formatter = self._state_formatter or default_state_formatter
        state_str = formatter(state)
        candidates = self._compute_shortlist(state)
        shortlist_view = [_candidate_to_view(c) for c in candidates]
        system = render_system_prompt(profile=_profile_for(self.strategy_profile))
        user = render_user_prompt(
            state_str,
            shortlist_block=_format_shortlist_block(candidates),
            opponent_profile=self.memory.opponent.to_prompt_block(),
            short_term_memory=self.memory.short_term.to_prompt_block(),
            last_plan=self._last_plan,
        )
        decision = await self.client.decide_loop(
            system_prompt=system,
            user_prompt=user,
            tool_context={"shortlist_view": shortlist_view},
            max_iterations=self.max_iterations,
        )
        if decision.action == "choose_move" and decision.move_id:
            self.memory.note_action(f"Used move: {decision.move_id}")
        elif decision.action == "choose_switch" and decision.pokemon_name:
            self.memory.note_action(f"Switched to: {decision.pokemon_name}")
        # Persist the next-turn plan if the LLM provided one.
        plan = (decision.commentary or "").strip()
        if plan:
            self._last_plan = plan
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

    def _compute_shortlist(self, state: Any) -> list[Candidate]:
        if not isinstance(state, BattleState):
            return []
        try:
            return shortlist(state, k=3)
        except Exception as exc:
            logger.debug("shortlist failed: %s", exc)
            return []


def _format_shortlist_block(candidates: list[Candidate]) -> str:
    if not candidates:
        return "Heuristic shortlist: (none — rely on your own analysis)"
    lines = ["Heuristic shortlist (ranked):"]
    for index, c in enumerate(candidates, 1):
        verb = "use" if c.kind == ActionKind.MOVE else "switch to"
        lines.append(f"  {index}. {verb} {c.target_id} — score {c.score:.1f} ({c.justification})")
    return "\n".join(lines)


def _candidate_to_view(c: Candidate) -> dict[str, object]:
    return {
        "kind": c.kind.value,
        "target_id": c.target_id,
        "score": c.score,
        "justification": c.justification,
        "expected_pct": c.expected_pct,
        "ko_chance": dict(c.ko_chance) if c.ko_chance else None,
    }


def _profile_for(name: str) -> str:
    from pokellm.prompts import strategy_profile as _sp

    return _sp(name)


def _default_state_formatter(state: Any) -> str:
    return default_state_formatter(state)


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
