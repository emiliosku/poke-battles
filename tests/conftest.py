"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import pytest

from pokecore import Type, TypePair
from pokecore.teams import TypeResolver


@pytest.fixture
def basic_type_resolver() -> TypeResolver:
    """A tiny type resolver for the most common species, used in tests."""

    def resolver(species_id: str) -> TypePair:
        table: dict[str, TypePair] = {
            "pikachu": TypePair(Type.ELECTRIC),
            "charizard": TypePair(Type.FIRE, Type.FLYING),
            "charizardmegax": TypePair(Type.FIRE, Type.DRAGON),
            "venusaur": TypePair(Type.GRASS, Type.POISON),
            "blastoise": TypePair(Type.WATER),
            "garchomp": TypePair(Type.DRAGON, Type.GROUND),
            "garchompmega": TypePair(Type.DRAGON, Type.GROUND),
            "dragapult": TypePair(Type.DRAGON, Type.GHOST),
            "iron valiant": TypePair(Type.FAIRY, Type.FIGHTING),
            "kingambit": TypePair(Type.DARK, Type.STEEL),
        }
        return table.get(species_id, TypePair(Type.NORMAL))

    return resolver
