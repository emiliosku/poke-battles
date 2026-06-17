"""Pokémon battle engine — pure data, no I/O.

This package contains the pure-Python core: type chart, team parser, formats,
battle state, damage estimation, and the Glicko-2 rating system. It has zero
I/O dependencies and is safe to import anywhere.
"""

from __future__ import annotations

from pokecore import elo, formats, teams, type_chart, types
from pokecore.elo import GlickoRating, MatchResult, expected_pair, expected_score, rate, rate_pair
from pokecore.formats import (
    GEN9_OU,
    GEN9_RANDOM_BATTLE,
    GEN9_RATED_BATTLE,
    SUPPORTED_FORMATS,
    Format,
    FormatKind,
    get_format,
)
from pokecore.teams import (
    EVSpread,
    IVSpread,
    MoveSlot,
    PokemonSet,
    Team,
    TypeResolver,
    format_team,
    parse_team,
)
from pokecore.type_chart import (
    coverage_summary,
    defensive_multiplier,
    is_immune,
    offensive_coverage,
    resists,
    type_multiplier,
    weak_to,
)
from pokecore.types import (
    NATURE_BOOSTS,
    NEUTRAL_NATURES,
    Boosts,
    Category,
    Generation,
    Nature,
    NatureModifier,
    Stat,
    Status,
    Type,
    TypePair,
    clamp,
)

__all__ = [
    "GEN9_OU",
    "GEN9_RANDOM_BATTLE",
    "GEN9_RATED_BATTLE",
    "NATURE_BOOSTS",
    "NEUTRAL_NATURES",
    "SUPPORTED_FORMATS",
    "Boosts",
    "Category",
    "EVSpread",
    "Format",
    "FormatKind",
    "Generation",
    "GlickoRating",
    "IVSpread",
    "MatchResult",
    "MoveSlot",
    "Nature",
    "NatureModifier",
    "PokemonSet",
    "Stat",
    "Status",
    "Team",
    "Type",
    "TypePair",
    "TypeResolver",
    "clamp",
    "coverage_summary",
    "defensive_multiplier",
    "elo",
    "expected_pair",
    "expected_score",
    "format_team",
    "formats",
    "get_format",
    "is_immune",
    "offensive_coverage",
    "parse_team",
    "rate",
    "rate_pair",
    "resists",
    "teams",
    "type_chart",
    "type_multiplier",
    "types",
    "weak_to",
]
