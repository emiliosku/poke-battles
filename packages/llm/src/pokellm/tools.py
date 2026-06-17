"""Tool definitions sent to the LLM.

Five tools in two tiers:
- **Action tools** (always exposed): ``choose_move`` and ``choose_switch``.
- **Reasoning tools** (optional, recommended for small models):
  ``lookup_type_chart``, ``estimate_damage``, ``evaluate_switch``.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pokecore import (
    Type,
    TypePair,
    defensive_multiplier,
    offensive_coverage,
    type_multiplier,
)


class ToolName(StrEnum):
    CHOOSE_MOVE = "choose_move"
    CHOOSE_SWITCH = "choose_switch"
    LOOKUP_TYPE_CHART = "lookup_type_chart"
    ESTIMATE_DAMAGE = "estimate_damage"
    EVALUATE_SWITCH = "evaluate_switch"


CHOOSE_MOVE_TOOL: dict[str, Any] = {
    "name": ToolName.CHOOSE_MOVE.value,
    "description": "Selects and executes one of the available moves.",
    "parameters": {
        "type": "object",
        "properties": {
            "move_name": {
                "type": "string",
                "description": "Exact move id (e.g. 'thunderbolt'). Must match an available move.",
            },
            "terastallize": {
                "type": "boolean",
                "description": "Whether to Terastallize into the move's Tera type before attacking.",
                "default": False,
            },
            "commentary": {
                "type": "string",
                "description": "One short sentence of reasoning. Do not exceed 30 words.",
            },
        },
        "required": ["move_name", "commentary"],
    },
}


CHOOSE_SWITCH_TOOL: dict[str, Any] = {
    "name": ToolName.CHOOSE_SWITCH.value,
    "description": "Switches the active Pokémon to one of the available bench Pokémon.",
    "parameters": {
        "type": "object",
        "properties": {
            "pokemon_name": {
                "type": "string",
                "description": "Exact species name (e.g. 'Pikachu'). Must match an available switch.",
            },
            "commentary": {
                "type": "string",
                "description": "One short sentence of reasoning. Do not exceed 30 words.",
            },
        },
        "required": ["pokemon_name", "commentary"],
    },
}


LOOKUP_TYPE_CHART_TOOL: dict[str, Any] = {
    "name": "lookup_type_chart",
    "description": (
        "Returns the type-effectiveness multiplier of a move-type against a defender "
        "with the given types. Use this to reason about super-effective hits, "
        "resistances, and immunities. Values: 0.0=immune, 0.5=resisted, 1.0=neutral, "
        "2.0=super effective."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "move_type": {
                "type": "string",
                "description": "Type of the attacking move. One of the 18 types.",
            },
            "defender_primary": {
                "type": "string",
                "description": "Primary type of the defending Pokémon.",
            },
            "defender_secondary": {
                "type": "string",
                "description": "Optional secondary type of the defending Pokémon. Omit for mono-types.",
            },
        },
        "required": ["move_type", "defender_primary"],
    },
}


ESTIMATE_DAMAGE_TOOL: dict[str, Any] = {
    "name": "estimate_damage",
    "description": (
        "Rough damage estimate: returns the percent of defender HP the move deals, "
        "computed from base power, STAB, and type effectiveness. Accuracy is "
        "approximate (~25% error). Use to compare moves, not for exact calcs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "move_base_power": {"type": "integer", "minimum": 1, "maximum": 250},
            "move_type": {"type": "string", "description": "Type of the move."},
            "attacker_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Attacker Pokémon types (for STAB).",
            },
            "defender_primary": {"type": "string"},
            "defender_secondary": {"type": "string"},
        },
        "required": ["move_base_power", "move_type", "attacker_types", "defender_primary"],
    },
}


EVALUATE_SWITCH_TOOL: dict[str, Any] = {
    "name": "evaluate_switch",
    "description": (
        "Returns a heuristic score for switching to a candidate Pokémon given the "
        "current opponent. Higher is better. Considers: type matchup, HP, "
        "and speed bracket."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "candidate_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Types of the candidate Pokémon (1 or 2).",
            },
            "opponent_types": {
                "type": "array",
                "items": {"type": "string"},
            },
            "candidate_hp_fraction": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Current HP fraction of the candidate.",
            },
        },
        "required": ["candidate_types", "opponent_types", "candidate_hp_fraction"],
    },
}


TOOLS: tuple[dict[str, Any], ...] = (
    CHOOSE_MOVE_TOOL,
    CHOOSE_SWITCH_TOOL,
    LOOKUP_TYPE_CHART_TOOL,
    ESTIMATE_DAMAGE_TOOL,
    EVALUATE_SWITCH_TOOL,
)


def _parse_type(name: str) -> Type | None:
    try:
        return Type(name.lower())
    except ValueError:
        return None


def lookup_type_chart_tool(
    move_type: str, defender_primary: str, defender_secondary: str | None = None
) -> float:
    """Implementation of the ``lookup_type_chart`` tool.

    Returns the type-effectiveness multiplier (0.0, 0.5, 1.0, 2.0, or 4.0).
    Returns ``1.0`` for unknown inputs (safe default).
    """
    atk = _parse_type(move_type)
    pri = _parse_type(defender_primary)
    if atk is None or pri is None:
        return 1.0
    if defender_secondary:
        sec = _parse_type(defender_secondary)
        if sec is None:
            return type_multiplier(atk, pri)
        return defensive_multiplier(TypePair(pri, sec), atk)
    return type_multiplier(atk, pri)


def estimate_damage_tool(
    move_base_power: int,
    move_type: str,
    attacker_types: list[str],
    defender_primary: str,
    defender_secondary: str | None = None,
) -> dict[str, object]:
    """Implementation of the ``estimate_damage`` tool."""
    atk = _parse_type(move_type)
    pri = _parse_type(defender_primary)
    if atk is None or pri is None:
        return {"pct": 0.0, "note": "unknown type"}
    sec = _parse_type(defender_secondary) if defender_secondary else None
    defender = TypePair(pri, sec) if sec else TypePair(pri)
    eff = offensive_coverage([atk], defender)
    has_stab = any(_parse_type(t) == atk for t in attacker_types)
    stab = 1.5 if has_stab else 1.0
    raw = (move_base_power * stab * eff) / 5.0
    pct = max(0.0, min(100.0, raw))
    note = "STAB" if has_stab else "no STAB"
    if eff == 0.0:
        note = "immune"
    elif eff >= 2.0:
        note = f"{note} super effective ({eff:g}x)"
    elif eff <= 0.5:
        note = f"{note} resisted ({eff:g}x)"
    return {"pct": round(pct, 1), "note": note}


def evaluate_switch_tool(
    candidate_types: list[str],
    opponent_types: list[str],
    candidate_hp_fraction: float,
) -> dict[str, object]:
    """Implementation of the ``evaluate_switch`` tool."""
    cand_types_list = [_parse_type(t) for t in candidate_types]
    opp_types_list = [_parse_type(t) for t in opponent_types]
    cand_types: list[Type] = [t for t in cand_types_list if t is not None]
    opp_types: list[Type] = [t for t in opp_types_list if t is not None]
    if not cand_types or not opp_types:
        return {"score": 0.0, "note": "unknown types"}
    opp_pair = TypePair(opp_types[0], opp_types[1] if len(opp_types) > 1 else None)
    off = offensive_coverage(cand_types, opp_pair)
    incoming = max(defensive_multiplier(opp_pair, t) for t in cand_types)
    if incoming == 0.0:
        return {"score": 0.0, "note": "immune to opponent's moves"}
    raw = (off / incoming) * candidate_hp_fraction * 100.0
    score = max(0.0, min(100.0, raw))
    if off >= 2.0 and incoming <= 0.5:
        note = "great matchup: SE + resists"
    elif off >= 2.0:
        note = "good matchup: SE offensively"
    elif incoming <= 0.5:
        note = "good matchup: resists"
    else:
        note = "neutral matchup"
    return {"score": round(score, 1), "note": note}


__all__ = [
    "CHOOSE_MOVE_TOOL",
    "CHOOSE_SWITCH_TOOL",
    "ESTIMATE_DAMAGE_TOOL",
    "EVALUATE_SWITCH_TOOL",
    "LOOKUP_TYPE_CHART_TOOL",
    "TOOLS",
    "ToolName",
    "estimate_damage_tool",
    "evaluate_switch_tool",
    "lookup_type_chart_tool",
]
