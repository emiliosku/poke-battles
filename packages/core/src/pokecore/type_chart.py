"""18×18 Pokémon type effectiveness matrix (Gen 6+, includes Fairy).

Defensive chart: given a defender's type(s) and an attacker's type, returns the
type-effectiveness multiplier. Immunity is 0.0, 4x = 4.0, neutral = 1.0.

Re-exported from :mod:`pokecore`.
"""

from __future__ import annotations

from typing import Final

from pokecore.types import Type, TypePair

_ORDER: Final[tuple[Type, ...]] = (
    Type.NORMAL,
    Type.FIRE,
    Type.WATER,
    Type.ELECTRIC,
    Type.GRASS,
    Type.ICE,
    Type.FIGHTING,
    Type.POISON,
    Type.GROUND,
    Type.FLYING,
    Type.PSYCHIC,
    Type.BUG,
    Type.ROCK,
    Type.GHOST,
    Type.DRAGON,
    Type.DARK,
    Type.STEEL,
    Type.FAIRY,
    Type.TYPELESS,
)

_ROW_TEMPLATE: Final[tuple[float, ...]] = (1.0,) * len(_ORDER)


def _row(
    *, two: tuple[Type, ...] = (), half: tuple[Type, ...] = (), zero: tuple[Type, ...] = ()
) -> dict[Type, float]:
    values: list[float] = list(_ROW_TEMPLATE)
    for t in two:
        values[_ORDER.index(t)] = 2.0
    for t in half:
        values[_ORDER.index(t)] = 0.5
    for t in zero:
        values[_ORDER.index(t)] = 0.0
    return dict(zip(_ORDER, values))


MULTIPLIERS: Final[dict[Type, dict[Type, float]]] = {
    Type.NORMAL: _row(half=(Type.ROCK, Type.STEEL), zero=(Type.GHOST,)),
    Type.FIRE: _row(
        two=(Type.WATER, Type.GROUND, Type.ROCK),
        half=(Type.FIRE, Type.GRASS, Type.ICE, Type.BUG, Type.STEEL, Type.FAIRY),
    ),
    Type.WATER: _row(
        two=(Type.GRASS, Type.ELECTRIC),
        half=(Type.FIRE, Type.WATER, Type.ICE, Type.STEEL),
    ),
    Type.ELECTRIC: _row(
        two=(Type.GROUND,),
        half=(Type.ELECTRIC, Type.FLYING, Type.STEEL),
    ),
    Type.GRASS: _row(
        two=(Type.FIRE, Type.ICE, Type.POISON, Type.FLYING, Type.BUG),
        half=(Type.WATER, Type.ELECTRIC, Type.GRASS, Type.GROUND),
    ),
    Type.ICE: _row(
        two=(Type.FIRE, Type.FIGHTING, Type.ROCK, Type.STEEL),
        half=(Type.ICE,),
    ),
    Type.FIGHTING: _row(
        two=(Type.FLYING, Type.PSYCHIC, Type.FAIRY),
        half=(Type.BUG, Type.ROCK, Type.DARK),
    ),
    Type.POISON: _row(
        two=(Type.GROUND, Type.PSYCHIC),
        half=(Type.GRASS, Type.FIGHTING, Type.POISON, Type.BUG, Type.FAIRY),
    ),
    Type.GROUND: _row(
        two=(Type.WATER, Type.ICE, Type.GRASS),
        half=(Type.POISON, Type.ROCK),
        zero=(Type.ELECTRIC,),
    ),
    Type.FLYING: _row(
        two=(Type.ELECTRIC, Type.ICE, Type.ROCK),
        half=(Type.GRASS, Type.FIGHTING, Type.BUG),
        zero=(Type.GROUND,),
    ),
    Type.PSYCHIC: _row(
        two=(Type.BUG, Type.GHOST, Type.DARK),
        half=(Type.FIGHTING, Type.PSYCHIC),
    ),
    Type.BUG: _row(
        two=(Type.FIRE, Type.FLYING, Type.ROCK),
        half=(Type.GRASS, Type.FIGHTING, Type.GROUND),
    ),
    Type.ROCK: _row(
        two=(Type.WATER, Type.GRASS, Type.FIGHTING, Type.GROUND, Type.STEEL),
        half=(Type.NORMAL, Type.FIRE, Type.POISON, Type.FLYING),
    ),
    Type.GHOST: _row(
        two=(Type.GHOST, Type.DARK),
        half=(Type.POISON, Type.BUG),
        zero=(Type.NORMAL, Type.FIGHTING),
    ),
    Type.DRAGON: _row(
        two=(Type.ICE, Type.DRAGON, Type.FAIRY),
        half=(Type.FIRE, Type.WATER, Type.ELECTRIC, Type.GRASS),
    ),
    Type.DARK: _row(
        two=(Type.FIGHTING, Type.BUG, Type.FAIRY),
        half=(Type.GHOST, Type.DARK),
        zero=(Type.PSYCHIC,),
    ),
    Type.STEEL: _row(
        two=(Type.FIRE, Type.FIGHTING, Type.GROUND),
        half=(
            Type.NORMAL,
            Type.GRASS,
            Type.ICE,
            Type.FLYING,
            Type.PSYCHIC,
            Type.BUG,
            Type.ROCK,
            Type.DRAGON,
            Type.STEEL,
            Type.FAIRY,
        ),
        zero=(Type.POISON,),
    ),
    Type.FAIRY: _row(
        two=(Type.POISON, Type.STEEL),
        half=(Type.FIGHTING, Type.BUG, Type.DARK),
        zero=(Type.DRAGON,),
    ),
    Type.TYPELESS: _row(),
}


def type_multiplier(attacker: Type, defender: Type) -> float:
    """Return the offensive multiplier of ``attacker`` vs ``defender``."""
    if attacker == Type.TYPELESS or defender == Type.TYPELESS:
        return 1.0
    return MULTIPLIERS[defender][attacker]


def defensive_multiplier(defender: TypePair, attacker: Type) -> float:
    """Return the type effectiveness of an ``attacker``'s move vs a defender."""
    if attacker == Type.TYPELESS:
        return 1.0
    multiplier = type_multiplier(attacker, defender.primary)
    if defender.secondary is not None:
        multiplier *= type_multiplier(attacker, defender.secondary)
    return multiplier


def offensive_coverage(attacker_types: list[Type], defender: TypePair) -> float:
    """Return the best type-coverage multiplier an attacker with given types can hit for."""
    if not attacker_types:
        return 1.0
    return max(defensive_multiplier(defender, t) for t in attacker_types)


def is_immune(defender: TypePair, attacker: Type) -> bool:
    return defensive_multiplier(defender, attacker) == 0.0


def resists(defender: TypePair, attacker: Type) -> bool:
    return 0.0 < defensive_multiplier(defender, attacker) < 1.0


def weak_to(defender: TypePair, attacker: Type) -> bool:
    return defensive_multiplier(defender, attacker) > 1.0


def coverage_summary(attacker_types: list[Type], defender: TypePair) -> dict[str, object]:
    """Summarize the type matchup between an attacking moveset and a defender."""
    best: Type | None = None
    best_value = 0.0
    worst: Type | None = None
    worst_value = float("inf")
    neutral = True
    for t in attacker_types:
        m = defensive_multiplier(defender, t)
        if m == 0.0:
            return {"best": None, "worst": None, "multiplier": 0.0, "is_neutral": False}
        if m > best_value:
            best_value = m
            best = t
        if m < worst_value:
            worst_value = m
            worst = t
        if m != 1.0:
            neutral = False
    return {
        "best": best,
        "worst": worst,
        "multiplier": best_value,
        "is_neutral": neutral,
    }
