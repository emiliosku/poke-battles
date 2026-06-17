"""Unit tests for the battle service chooser builder."""

from __future__ import annotations

from pokeapi.services import _random_chooser, build_chooser
from pokellm.config import Tier


class TestBuildChooser:
    def test_none_config_returns_random(self) -> None:
        chooser = build_chooser("anything", None)
        assert chooser is _random_chooser

    def test_mock_tier_returns_random(self) -> None:
        from pokellm.config import AgentConfig

        cfg = AgentConfig(
            name="mock",
            provider="mock",
            model_id="mock/deterministic",
            tier=Tier.MOCK,
            supports_tools=False,
        )
        chooser = build_chooser("mock", cfg)
        assert chooser is _random_chooser

    def test_real_tier_returns_llm_chooser(self) -> None:
        from pokellm.config import AgentConfig

        cfg = AgentConfig(
            name="llama",
            provider="cerebras",
            model_id="cerebras/llama3.1-8b",
            tier=Tier.FREE,
        )
        chooser = build_chooser("llama", cfg)
        assert chooser is not _random_chooser
        assert callable(chooser)
