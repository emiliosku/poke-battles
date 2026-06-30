"""Unit tests for pokellm.tools."""

from __future__ import annotations

from pokecore import Type
from pokellm.tools import (
    CHOOSE_MOVE_TOOL,
    CHOOSE_SWITCH_TOOL,
    TOOLS,
    estimate_damage_tool,
    evaluate_switch_tool,
    lookup_type_chart_tool,
)


class TestToolSchemas:
    def test_all_tools_have_names(self) -> None:
        names = {t["name"] for t in TOOLS}
        assert names == {
            "choose_move",
            "choose_switch",
            "lookup_type_chart",
            "estimate_damage",
            "evaluate_switch",
            "evaluate_candidate",
            "propose_alternative",
        }

    def test_schemas_have_parameters(self) -> None:
        for t in TOOLS:
            assert "parameters" in t
            assert "type" in t["parameters"]
            assert t["parameters"]["type"] == "object"
            assert "properties" in t["parameters"]

    def test_choose_move_requires_move_name(self) -> None:
        assert "move_name" in CHOOSE_MOVE_TOOL["parameters"]["required"]

    def test_choose_switch_requires_pokemon_name(self) -> None:
        assert "pokemon_name" in CHOOSE_SWITCH_TOOL["parameters"]["required"]


class TestLookupTypeChart:
    def test_super_effective(self) -> None:
        assert lookup_type_chart_tool("water", "fire") == 2.0
        assert lookup_type_chart_tool("ground", "electric") == 2.0

    def test_immunity(self) -> None:
        assert lookup_type_chart_tool("normal", "ghost") == 0.0
        assert lookup_type_chart_tool("electric", "ground") == 0.0
        assert lookup_type_chart_tool("dragon", "fairy") == 0.0

    def test_resisted(self) -> None:
        assert lookup_type_chart_tool("fire", "fire") == 0.5

    def test_neutral(self) -> None:
        assert lookup_type_chart_tool("normal", "normal") == 1.0

    def test_dual_type_multiplies(self) -> None:
        result = lookup_type_chart_tool("water", "fire", "flying")
        assert result == 2.0

    def test_dual_type_quad(self) -> None:
        result = lookup_type_chart_tool("rock", "fire", "flying")
        assert result == 4.0

    def test_unknown_type_safe_default(self) -> None:
        assert lookup_type_chart_tool("unknown", "fire") == 1.0
        assert lookup_type_chart_tool("water", "unknown") == 1.0
        assert lookup_type_chart_tool("water", "fire", "unknown") == 2.0


class TestEstimateDamage:
    def test_basic_attack(self) -> None:
        r = estimate_damage_tool(80, "fire", ["fire"], "grass")
        pct = r["pct"]
        assert isinstance(pct, float)
        assert pct > 30.0
        assert "STAB" in str(r["note"])
        assert "super effective" in str(r["note"])

    def test_immune(self) -> None:
        r = estimate_damage_tool(80, "normal", ["normal"], "ghost")
        assert r["pct"] == 0.0
        assert r["note"] == "immune"

    def test_resisted(self) -> None:
        r = estimate_damage_tool(80, "fire", ["fire"], "water")
        assert "resisted" in str(r["note"])

    def test_pct_in_range(self) -> None:
        r = estimate_damage_tool(250, "fire", ["fire"], "grass")
        pct = r["pct"]
        assert isinstance(pct, float)
        assert 0.0 <= pct <= 100.0

    def test_unknown_type(self) -> None:
        r = estimate_damage_tool(80, "unknown", ["fire"], "fire")
        assert r["pct"] == 0.0


class TestEvaluateSwitch:
    def test_great_matchup(self) -> None:
        r = evaluate_switch_tool(["water"], ["fire", "ground"], 1.0)
        score = r["score"]
        assert isinstance(score, float)
        assert score > 30.0
        assert "SE" in str(r["note"])

    def test_immune(self) -> None:
        r = evaluate_switch_tool(["normal"], ["ghost"], 1.0)
        assert r["score"] == 0.0
        assert r["note"] == "immune to opponent's moves"

    def test_low_hp_lower_score(self) -> None:
        full = evaluate_switch_tool(["water"], ["fire"], 1.0)
        half = evaluate_switch_tool(["water"], ["fire"], 0.5)
        full_score = full["score"]
        half_score = half["score"]
        assert isinstance(full_score, float)
        assert isinstance(half_score, float)
        assert half_score < full_score

    def test_unknown_types(self) -> None:
        r = evaluate_switch_tool(["unknown"], ["fire"], 1.0)
        assert r["score"] == 0.0


class TestTypePairIntegration:
    def test_lookup_with_typepair(self) -> None:
        primary = Type.FIRE
        secondary = Type.FLYING
        assert primary is not None
        assert secondary is not None
        result = lookup_type_chart_tool("rock", primary.value, secondary.value)
        assert result == 4.0
