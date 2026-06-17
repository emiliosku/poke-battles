"""Unit tests for pokeengine.format_validator."""

from __future__ import annotations

import pytest

import pokecore
from pokecore import (
    EVSpread,
    Format,
    Generation,
    IVSpread,
    MoveSlot,
    PokemonSet,
    Team,
    Type,
    TypePair,
    parse_team,
)
from pokeengine.format_validator import validate_team

GARCHOMP_TEAM = """\
Garchomp @ Choice Scarf
Ability: Rough Skin
EVs: 252 Atk / 4 SpD / 252 Spe
Jolly Nature
- Earthquake
- Outrage
- Stone Edge
- Stealth Rock
"""


def _build_team_with(level: int = 100, ev_total: int = 508, moves: int = 4) -> Team:
    pkmn = PokemonSet(
        nickname=None,
        species="Garchomp",
        species_id="garchomp",
        types=TypePair(Type.DRAGON, Type.GROUND),
        item="Choice Scarf",
        ability="Rough Skin",
        level=level,
        shiny=False,
        happiness=None,
        nature=pokecore.Nature.JOLLY,
        nature_modifier=pokecore.NatureModifier.from_nature(pokecore.Nature.JOLLY),
        tera_type=None,
        evs=EVSpread.zero(),
        ivs=IVSpread.default(),
        moves=tuple(MoveSlot(name=f"Move {i}") for i in range(moves)),
    )
    return Team(name="t", pokemon=(pkmn,), format="gen9randombattle")


class TestValidateTeam:
    def test_valid_team(self) -> None:
        team = parse_team(
            GARCHOMP_TEAM, type_resolver=lambda sid: TypePair(Type.DRAGON, Type.GROUND)
        )
        errors = validate_team(team, Format(id="gen9ou", name="OU", generation=Generation.GEN9))
        assert errors == []

    def test_too_many_moves_caught_at_construction(self) -> None:
        with pytest.raises(ValueError):
            _build_team_with(moves=5)

    def test_tera_type_blocked_pre_gen9(self) -> None:
        pkmn = PokemonSet(
            nickname=None,
            species="Garchomp",
            species_id="garchomp",
            types=TypePair(Type.DRAGON, Type.GROUND),
            item=None,
            ability="Rough Skin",
            level=100,
            shiny=False,
            happiness=None,
            nature=pokecore.Nature.JOLLY,
            nature_modifier=pokecore.NatureModifier.from_nature(pokecore.Nature.JOLLY),
            tera_type=Type.FIRE,
            evs=EVSpread.zero(),
            ivs=IVSpread.default(),
            moves=(MoveSlot(name="Earthquake"),),
        )
        team = Team(name="t", pokemon=(pkmn,), format="gen8ou")
        errors = validate_team(team, Format(id="gen8ou", name="OU", generation=Generation.GEN8))
        assert any("tera" in e for e in errors)

    def test_banned_species(self) -> None:
        team = parse_team(
            GARCHOMP_TEAM, type_resolver=lambda sid: TypePair(Type.DRAGON, Type.GROUND)
        )
        fmt = Format(
            id="gen9custom",
            name="x",
            generation=Generation.GEN9,
            banned_species=frozenset({"garchomp"}),
        )
        errors = validate_team(team, fmt)
        assert any("not legal" in e for e in errors)

    def test_known_species_filter(self) -> None:
        team = parse_team(
            GARCHOMP_TEAM, type_resolver=lambda sid: TypePair(Type.DRAGON, Type.GROUND)
        )
        errors = validate_team(
            team, Format(id="x", name="x", generation=Generation.GEN9), known_species=["pikachu"]
        )
        assert any("Unknown species" in e for e in errors)
