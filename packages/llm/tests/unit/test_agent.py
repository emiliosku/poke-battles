"""Unit tests for pokellm.agent (without hitting a real LLM)."""

from __future__ import annotations

import pytest

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
        self.calls: list[tuple[str, str]] = []

    async def decide(self, *, system_prompt: str, user_prompt: str) -> LLMDecision:
        self.calls.append((system_prompt, user_prompt))
        return self.decision


@pytest.fixture
def cfg() -> AgentConfig:
    return AgentConfig(
        name="test",
        provider="cerebras",
        model_id="cerebras/llama3.1-8b",
        tier=Tier.FREE,
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
        sys, _ = client.calls[0]
        assert "Aggressive" in sys or "aggressive" in sys


class TestNormalize:
    def test_move_id(self) -> None:
        assert normalize_move_id("Thunder Punch") == "thunderpunch"
        assert normalize_move_id("U-turn") == "uturn"
        assert normalize_move_id("Will-O-Wisp") == "willowisp"

    def test_species(self) -> None:
        assert normalize_species("Pikachu") == "pikachu"
        assert normalize_species("Charizard-Mega-X") == "charizardmegax"
        assert normalize_species("Mr. Mime") == "mrmime"
