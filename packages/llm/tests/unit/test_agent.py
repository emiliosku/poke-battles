"""Unit tests for pokellm.agent (without hitting a real LLM)."""

from __future__ import annotations

import pytest

from pokecore.state import BattleState, FieldState, KnownMove, PokemonState
from pokellm.agent import LLMAgent, normalize_move_id, normalize_species
from pokellm.clients import LLMDecision
from pokellm.config import AgentConfig, Tier


class FakeLLMClient:
    def __init__(self, decision: LLMDecision | None = None) -> None:
        self.decision = decision or LLMDecision(
            action="choose_move",
            move_id="thunderbolt",
            commentary="Test",
        )
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.loop_calls: list[tuple[str, str, dict[str, object] | None, int]] = []

    async def decide(self, *, system_prompt: str, user_prompt: str) -> LLMDecision:
        self.calls.append((system_prompt, user_prompt, {}))
        return self.decision

    async def decide_loop(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tool_context: dict[str, object] | None = None,
        max_iterations: int = 4,
    ) -> LLMDecision:
        self.loop_calls.append((system_prompt, user_prompt, tool_context, max_iterations))
        return self.decision


@pytest.fixture
def cfg() -> AgentConfig:
    return AgentConfig(
        name="test",
        provider="cerebras",
        model_id="cerebras/llama3.1-8b",
        tier=Tier.FREE,
    )


def _garchomp_battle() -> BattleState:
    active = PokemonState(
        species="Garchomp",
        nickname="Garchomp",
        types=("dragon", "ground"),
        level=84,
        hp_fraction=1.0,
        status=None,
        ability=None,
        item=None,
        tera_type=None,
        is_terastallized=False,
        is_active=True,
        is_fainted=False,
        boosts={},
        moves=(
            KnownMove(
                id="earthquake",
                name="Earthquake",
                type="ground",
                category="physical",
                base_power=100,
                accuracy=100,
                pp=16,
                max_pp=24,
            ),
        ),
    )
    opp = PokemonState(
        species="Heatran",
        nickname="Heatran",
        types=("fire", "steel"),
        level=84,
        hp_fraction=1.0,
        status=None,
        ability=None,
        item=None,
        tera_type=None,
        is_terastallized=False,
        is_active=True,
        is_fainted=False,
        boosts={},
        moves=(
            KnownMove(
                id="fireblast",
                name="Fire Blast",
                type="fire",
                category="special",
                base_power=110,
                accuracy=100,
                pp=8,
                max_pp=16,
            ),
        ),
    )
    return BattleState(
        battle_id="b1",
        turn=1,
        format="gen9randombattle",
        player_username="alice",
        opponent_username="bob",
        player=(active,),
        opponent=(opp,),
        field=FieldState(
            weather=None,
            terrain=None,
            trick_room=False,
            player_hazards={},
            opponent_hazards={},
        ),
        can_tera=False,
    )


class TestLLMAgent:
    async def test_choose_move_order(self, cfg: AgentConfig) -> None:
        client = FakeLLMClient()
        agent = LLMAgent(config=cfg, client=client)  # type: ignore[arg-type]
        order = await agent.turn({"formatted": "my active is Pikachu"})
        assert order.action == "choose_move"
        assert order.order == "/choose move thunderbolt"
        assert order.move_id == "thunderbolt"

    async def test_choose_switch_order(self, cfg: AgentConfig) -> None:
        client = FakeLLMClient(
            LLMDecision(action="choose_switch", pokemon_name="Charizard", commentary="pivot"),
        )
        agent = LLMAgent(config=cfg, client=client)  # type: ignore[arg-type]
        order = await agent.turn({"formatted": "..."})
        assert order.action == "choose_switch"
        assert order.order == "/choose switch Charizard"

    async def test_fallback_on_no_tool_call(self, cfg: AgentConfig) -> None:
        client = FakeLLMClient(LLMDecision(action="__no_tool_call__", commentary=""))
        agent = LLMAgent(config=cfg, client=client, fallback_random=True, max_retries=1)  # type: ignore[arg-type]
        order = await agent.turn({"formatted": "..."})
        assert order.action == "__fallback__"
        assert order.order == "/choose default"

    async def test_no_fallback_raises(self, cfg: AgentConfig) -> None:
        client = FakeLLMClient(LLMDecision(action="__no_tool_call__"))
        agent = LLMAgent(config=cfg, client=client, fallback_random=False, max_retries=0)  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="failed after retries"):
            await agent.turn({"formatted": "..."})

    async def test_records_action_in_memory(self, cfg: AgentConfig) -> None:
        client = FakeLLMClient()
        agent = LLMAgent(config=cfg, client=client)  # type: ignore[arg-type]
        await agent.turn({"formatted": "..."})
        assert "thunderbolt" in agent.memory.short_term.entries[0]

    async def test_prompt_includes_strategy_profile(self, cfg: AgentConfig) -> None:
        client = FakeLLMClient()
        agent = LLMAgent(config=cfg, client=client, strategy_profile="aggressive")  # type: ignore[arg-type]
        await agent.turn({"formatted": "..."})
        sys, _, _, _ = client.loop_calls[0]
        assert "Aggressive" in sys or "aggressive" in sys

    async def test_uses_decide_loop_with_shortlist(self, cfg: AgentConfig) -> None:
        client = FakeLLMClient()
        agent = LLMAgent(config=cfg, client=client)  # type: ignore[arg-type]
        battle = _garchomp_battle()
        await agent.turn(battle)
        assert len(client.loop_calls) == 1
        _, user, ctx, max_iter = client.loop_calls[0]
        assert "Heuristic shortlist" in user
        assert "earthquake" in user
        assert ctx is not None
        shortlist_view = ctx["shortlist_view"]
        assert shortlist_view, "shortlist view must not be empty for a real BattleState"
        first: dict[str, object] = shortlist_view[0]  # type: ignore[index]
        assert str(first["target_id"]) == "earthquake"
        assert max_iter == 4

    async def test_plan_scratchpad_persists_across_turns(self, cfg: AgentConfig) -> None:
        # Turn 1: LLM returns a plan in commentary. Turn 2: plan appears in the prompt.
        client = FakeLLMClient(
            LLMDecision(action="choose_move", move_id="earthquake", commentary="plan: scout turn 2")
        )
        agent = LLMAgent(config=cfg, client=client)  # type: ignore[arg-type]
        battle = _garchomp_battle()
        await agent.turn(battle)
        assert agent._last_plan == "plan: scout turn 2"
        await agent.turn(battle)
        _, user_2, _, _ = client.loop_calls[1]
        assert "scout turn 2" in user_2
        assert "Last plan" in user_2

    async def test_no_shortlist_for_dict_state(self, cfg: AgentConfig) -> None:
        # When state is a dict (legacy path) the shortlist is empty, but decide_loop
        # is still called and the prompt is rendered.
        client = FakeLLMClient()
        agent = LLMAgent(config=cfg, client=client)  # type: ignore[arg-type]
        await agent.turn({"formatted": "..."})
        _, user, ctx, _ = client.loop_calls[0]
        assert "Heuristic shortlist: (none" in user
        assert ctx == {"shortlist_view": []}


class TestNormalize:
    def test_move_id(self) -> None:
        assert normalize_move_id("Thunder Punch") == "thunderpunch"
        assert normalize_move_id("U-turn") == "uturn"
        assert normalize_move_id("Will-O-Wisp") == "willowisp"

    def test_species(self) -> None:
        assert normalize_species("Pikachu") == "pikachu"
        assert normalize_species("Charizard-Mega-X") == "charizardmegax"
        assert normalize_species("Mr. Mime") == "mrmime"
