"""Unit tests for pokecore.teams."""

from __future__ import annotations

import pytest

from pokeapi.routes.teams import _pokemon_to_preview
from pokecore.teams import (
    EVSpread,
    IVSpread,
    _parse_header,
    format_team,
    parse_team,
)
from pokecore.types import Nature, Stat, Type, TypePair

SAMPLE_PASTE = """\
Charizard-Mega-X @ Charizardite X
Ability: Tough Claws
Shiny: Yes
EVs: 252 Atk / 4 SpD / 252 Spe
Hasty Nature
- Dragon Dance
- Flare Blitz
- Roost
- Earthquake

Pikachu @ Light Ball
Ability: Static
Level: 50
EVs: 252 SpA / 4 SpD / 252 Spe
IVs: 31 HP / 30 Atk / 30 Def / 30 SpA / 30 SpD / 30 Spe
Timid Nature
- Thunder
- Surf
- Hidden Power Ice
- Volt Tackle
"""

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


def type_resolver(species_id: str) -> TypePair:
    table: dict[str, TypePair] = {
        "charizardmegax": TypePair(Type.FIRE, Type.DRAGON),
        "pikachu": TypePair(Type.ELECTRIC),
        "garchomp": TypePair(Type.DRAGON, Type.GROUND),
    }
    return table.get(species_id, TypePair(Type.NORMAL))


class TestEVSpread:
    def test_zero(self) -> None:
        spread = EVSpread.zero()
        assert spread.total == 0
        assert spread.values[Stat.HP] == 0

    def test_parse_single(self) -> None:
        spread = EVSpread.parse("252 Atk")
        assert spread.values[Stat.ATTACK] == 252
        assert spread.total == 252

    def test_parse_multiple(self) -> None:
        spread = EVSpread.parse("252 Atk / 4 SpD / 252 Spe")
        assert spread.values[Stat.ATTACK] == 252
        assert spread.values[Stat.SPECIAL_DEFENSE] == 4
        assert spread.values[Stat.SPEED] == 252
        assert spread.total == 508

    def test_parse_invalid_value(self) -> None:
        with pytest.raises(ValueError):
            EVSpread.parse("300 Atk")

    def test_parse_not_divisible_by_4(self) -> None:
        with pytest.raises(ValueError):
            EVSpread.parse("5 Atk")

    def test_parse_total_over_510(self) -> None:
        with pytest.raises(ValueError):
            EVSpread.parse("252 HP / 252 Atk / 4 Def / 4 SpD / 4 Spe")

    def test_parse_unknown_stat(self) -> None:
        with pytest.raises(ValueError):
            EVSpread.parse("252 Foo")


class TestIVSpread:
    def test_default_all_31(self) -> None:
        spread = IVSpread.default()
        for s in spread.values.values():
            assert s == 31

    def test_parse_zero_ivs(self) -> None:
        spread = IVSpread.parse("0 Atk")
        assert spread.values[Stat.ATTACK] == 0
        assert spread.values[Stat.DEFENSE] == 31

    def test_parse_hp_ivs(self) -> None:
        spread = IVSpread.parse("30 SpA / 30 SpD / 30 Spe")
        assert spread.values[Stat.SPECIAL_ATTACK] == 30
        assert spread.values[Stat.HP] == 31

    def test_parse_invalid(self) -> None:
        with pytest.raises(ValueError):
            IVSpread.parse("32 Atk")


class TestParseHeader:
    def test_simple_species(self) -> None:
        nickname, species, item = _parse_header("Garchomp")
        assert nickname is None
        assert species == "Garchomp"
        assert item is None

    def test_species_with_item(self) -> None:
        nickname, species, item = _parse_header("Garchomp @ Choice Scarf")
        assert species == "Garchomp"
        assert item == "Choice Scarf"

    def test_nickname_with_parens(self) -> None:
        nickname, species, item = _parse_header("Zardy (Charizard-Mega-X) @ Orb")
        assert nickname == "Zardy"
        assert species == "Charizard-Mega-X"
        assert item == "Orb"

    def test_species_form_no_nickname(self) -> None:
        nickname, species, item = _parse_header("Charizard-Mega-X")
        assert nickname is None
        assert species == "Charizard-Mega-X"


class TestParsePokemonBlock:
    def test_garchomp(self) -> None:
        team = parse_team(GARCHOMP_TEAM, type_resolver=type_resolver)
        assert len(team.pokemon) == 1
        pkmn = team.pokemon[0]
        assert pkmn.species == "Garchomp"
        assert pkmn.species_id == "garchomp"
        assert pkmn.types == TypePair(Type.DRAGON, Type.GROUND)
        assert pkmn.item == "Choice Scarf"
        assert pkmn.ability == "Rough Skin"
        assert pkmn.level == 100
        assert pkmn.nature == Nature.JOLLY
        from pokecore.types import Stat as _Stat

        assert pkmn.nature_modifier.increased == _Stat.SPEED
        assert pkmn.tera_type is None
        assert len(pkmn.moves) == 4

    def test_full_sample(self) -> None:
        team = parse_team(SAMPLE_PASTE, type_resolver=type_resolver)
        assert len(team.pokemon) == 2
        charizard = team.pokemon[0]
        assert charizard.species == "Charizard-Mega-X"
        assert charizard.shiny is True
        assert charizard.nature == Nature.HASTY
        assert charizard.ability == "Tough Claws"
        assert charizard.item == "Charizardite X"
        from pokecore.types import Stat as _Stat

        assert charizard.nature_modifier.increased == _Stat.SPEED
        assert charizard.nature_modifier.decreased == _Stat.DEFENSE
        pikachu = team.pokemon[1]
        assert pikachu.level == 50
        assert pikachu.ivs.values[Stat.ATTACK] == 30
        assert pikachu.ivs.values[Stat.HP] == 31
        assert {m.name for m in pikachu.moves} == {
            "Thunder",
            "Surf",
            "Hidden Power Ice",
            "Volt Tackle",
        }

    def test_missing_ability_raises(self) -> None:
        paste = "Pikachu @ Light Ball\nTimid Nature\n- Thunder\n"
        with pytest.raises(ValueError, match="missing Ability"):
            parse_team(paste, type_resolver=type_resolver)

    def test_missing_nature_raises(self) -> None:
        paste = "Pikachu @ Light Ball\nAbility: Static\n- Thunder\n"
        with pytest.raises(ValueError, match="missing Nature"):
            parse_team(paste, type_resolver=type_resolver)

    def test_too_many_moves_raises(self) -> None:
        paste = (
            "Pikachu @ Light Ball\n"
            "Ability: Static\n"
            "Timid Nature\n"
            "- Move 1\n- Move 2\n- Move 3\n- Move 4\n- Move 5\n"
        )
        with pytest.raises(ValueError, match="Move count"):
            parse_team(paste, type_resolver=type_resolver)

    def test_tera_type(self) -> None:
        paste = (
            "Pikachu @ Light Ball\nAbility: Static\nTera Type: Electric\nTimid Nature\n- Thunder\n"
        )
        team = parse_team(paste, type_resolver=type_resolver)
        assert team.pokemon[0].tera_type == Type.ELECTRIC


class TestParseTeam:
    def test_empty_paste_raises(self) -> None:
        with pytest.raises(ValueError, match="Empty team paste"):
            parse_team("", type_resolver=type_resolver)

    def test_comments_and_headers_ignored(self) -> None:
        paste = "// generated by example tool\n=== My Team ===\n\n" + GARCHOMP_TEAM
        team = parse_team(paste, name="My Team", type_resolver=type_resolver)
        assert len(team.pokemon) == 1
        assert team.name == "My Team"

    def test_duplicate_species_raises(self) -> None:
        paste = GARCHOMP_TEAM + "\n" + GARCHOMP_TEAM
        with pytest.raises(ValueError, match="Duplicate species"):
            parse_team(paste, type_resolver=type_resolver)

    def test_team_name(self) -> None:
        team = parse_team(
            SAMPLE_PASTE, name="My Team", format="gen9ou", type_resolver=type_resolver
        )
        assert team.name == "My Team"
        assert team.format == "gen9ou"
        assert len(team.pokemon) == 2


class TestRoundTrip:
    def test_format_then_parse(self) -> None:
        team = parse_team(SAMPLE_PASTE, name="Test", type_resolver=type_resolver)
        serialized = format_team(team)
        reparsed = parse_team(serialized, name="Test", type_resolver=type_resolver)
        assert reparsed.name == team.name
        assert len(reparsed.pokemon) == len(team.pokemon)
        for original, new in zip(team.pokemon, reparsed.pokemon):
            assert original.species == new.species
            assert original.item == new.item
            assert original.ability == new.ability
            assert original.nature == new.nature
            assert original.level == new.level
            assert original.shiny == new.shiny
            assert [m.name for m in original.moves] == [m.name for m in new.moves]


class TestPokemonToPreview:
    def test_full_pokemon_maps_to_preview(self) -> None:
        team = parse_team(SAMPLE_PASTE, type_resolver=type_resolver)
        charizard = team.pokemon[0]
        preview = _pokemon_to_preview(charizard)
        assert preview.species == "Charizard-Mega-X"
        assert preview.species_id == "charizardmegax"
        assert preview.item == "Charizardite X"
        assert preview.ability == "Tough Claws"
        assert preview.types == ["fire", "dragon"]
        assert preview.moves == ["Dragon Dance", "Flare Blitz", "Roost", "Earthquake"]

    def test_pokemon_without_item(self) -> None:
        paste = "Pikachu\nAbility: Static\nHardy Nature\n- Thunder\n"
        team = parse_team(paste, type_resolver=type_resolver)
        preview = _pokemon_to_preview(team.pokemon[0])
        assert preview.species == "Pikachu"
        assert preview.item is None
        assert preview.moves == ["Thunder"]

    def test_nickname_preserved(self) -> None:
        paste = (
            "Big Blue (Garchomp) @ Choice Scarf\nAbility: Rough Skin\nHardy Nature\n- Earthquake\n"
        )
        team = parse_team(paste, type_resolver=type_resolver)
        preview = _pokemon_to_preview(team.pokemon[0])
        assert preview.nickname == "Big Blue"
        assert preview.species == "Garchomp"
