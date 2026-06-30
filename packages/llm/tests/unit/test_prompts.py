"""Unit tests for pokellm.prompts."""

from __future__ import annotations

from pokellm.prompts import (
    PROMPT_VERSION,
    render_system_prompt,
    render_user_prompt,
    strategy_profile,
)


class TestSystemPrompt:
    def test_includes_rules(self) -> None:
        s = render_system_prompt()
        assert "choose_move" in s
        assert "choose_switch" in s
        assert "Pokémon Showdown" in s or "Pokemon Showdown" in s

    def test_includes_profile(self) -> None:
        s = render_system_prompt(profile="aggressive")
        assert "Strategy profile" in s
        assert "aggressive" in s.lower() or "Aggressive" in s

    def test_includes_extras(self) -> None:
        s = render_system_prompt(extras={"Format notes": "no legendaries"})
        assert "Format notes" in s
        assert "no legendaries" in s


class TestUserPrompt:
    def test_renders_state(self) -> None:
        s = render_user_prompt("My active: Pikachu at 100% HP")
        assert "My active: Pikachu at 100% HP" in s

    def test_includes_memory_blocks(self) -> None:
        s = render_user_prompt(
            "state",
            opponent_profile="sees Charizard",
            short_term_memory="last turn used tackle",
        )
        assert "Charizard" in s
        assert "tackle" in s

    def test_defaults(self) -> None:
        s = render_user_prompt("state")
        assert "no prior data" in s.lower() or "Opponent profile" in s
        assert "none yet" in s.lower() or "recent actions" in s


class TestStrategyProfile:
    def test_known_profiles(self) -> None:
        for name in ("aggressive", "stall", "hazard_stack", "setup_sweeper", "balanced"):
            assert strategy_profile(name)
            assert len(strategy_profile(name)) > 20

    def test_unknown_falls_back_to_balanced(self) -> None:
        assert strategy_profile("unknown") == strategy_profile("balanced")

    def test_prompt_version(self) -> None:
        assert PROMPT_VERSION == "v2"
