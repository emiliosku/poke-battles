"""Unit tests for pokecore.teams."""

from __future__ import annotations

import os

import pytest

from pokeapi.routes.teams import _pokemon_to_preview
from pokecore.sprite_status import CDN, FOLDER_EXT, _probe
from pokecore.teams import (
    EVSpread,
    IVSpread,
    _parse_header,
    format_team,
    normalize_team_paste_for_showdown,
    parse_team,
    sprite_id,
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

    def test_parse_wildcard_value_one(self) -> None:
        spread = EVSpread.parse("1 Atk")
        assert spread.values[Stat.ATTACK] == 1
        assert spread.total == 1

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
        assert preview.sprite_id == "charizard-megax"
        assert preview.item == "Charizardite X"
        assert preview.ability == "Tough Claws"
        assert preview.types == ["fire", "dragon"]
        assert preview.moves == ["Dragon Dance", "Flare Blitz", "Roost", "Earthquake"]

    def test_pokemon_without_item(self) -> None:
        paste = "Pikachu\nAbility: Static\nHardy Nature\n- Thunder\n"
        team = parse_team(paste, type_resolver=type_resolver)
        preview = _pokemon_to_preview(team.pokemon[0])
        assert preview.species == "Pikachu"
        assert preview.sprite_id == "pikachu"
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
        assert preview.sprite_id == "garchomp"


class TestSpriteSlug:
    """The sprite_id is what hits the Showdown CDN; it must lower-case
    the species, keep the form-separating dashes, and strip dots /
    spaces / apostrophes / accented characters. Regression tests for
    the slug that broke Mega/regional/Galar/etc. sprites."""

    def test_base_species(self) -> None:
        assert sprite_id("Pikachu") == "pikachu"
        assert sprite_id("Garchomp") == "garchomp"
        assert sprite_id("Mewtwo") == "mewtwo"

    def test_mega_keeps_dash(self) -> None:
        assert sprite_id("Charizard-Mega-X") == "charizard-megax"
        assert sprite_id("Charizard-Mega-Y") == "charizard-megay"
        assert sprite_id("Aerodactyl-Mega") == "aerodactyl-mega"
        assert sprite_id("Blaziken-Mega") == "blaziken-mega"
        assert sprite_id("Mewtwo-Mega-X") == "mewtwo-megax"

    def test_regional_forms(self) -> None:
        assert sprite_id("Slowking-Galar") == "slowking-galar"
        assert sprite_id("Weezing-Galar") == "weezing-galar"
        # Mr. Mime-Galar shares its base form's sprite on the CDN; the
        # override table collapses the slug to the base form.
        assert sprite_id("Mr. Mime-Galar") == "mrmime"
        assert sprite_id("Zoroark-Hisui") == "zoroark-hisui"
        assert sprite_id("Wooper-Paldea") == "wooper-paldea"
        assert sprite_id("Vulpix-Alola") == "vulpix-alola"

    def test_dotted_names_become_dashed(self) -> None:
        assert sprite_id("Mr. Mime") == "mr-mime"
        assert sprite_id("Mime Jr.") == "mime-jr"
        assert sprite_id("Tapu Lele") == "tapu-lele"

    def test_apostrophes_and_accents_stripped(self) -> None:
        # Farfetch'd has an apostrophe in the species name.
        assert sprite_id("Farfetch'd") == "farfetchd"
        # Flabébé has an accented é; the slug folds it to plain e so the
        # CDN gets a real ASCII path (``flabebe``, not ``flabb``).
        assert sprite_id("Flabébé") == "flabebe"

    def test_unique_megas(self) -> None:
        # Mega forms of the same base have distinct slugs.
        assert sprite_id("Charizard-Mega-X") != sprite_id("Charizard-Mega-Y")
        # And the slash on Mewtwo-Mega-X becomes nothing.
        assert sprite_id("Mewtwo-Mega-X") == "mewtwo-megax"

    def test_species_id_and_sprite_id_diverge_for_forms(self) -> None:
        # Regression: species_id strips dashes (used as flat lookup key),
        # sprite_id keeps them (used as CDN slug). They must NOT collapse
        # into the same string for form-distinguishing species.
        # Mr. Mime-Galar is excluded: the CDN reuses the base form's
        # sprite, so its slug intentionally collapses to the base form.
        from pokecore.teams import _normalize_species_id

        for species in [
            "Charizard-Mega-X",
            "Slowking-Galar",
            "Aerodactyl-Mega",
        ]:
            sid = _normalize_species_id(species)
            spid = sprite_id(species)
            assert sid != spid, f"{species}: expected sid={sid!r} != sprite_id={spid!r}"
            assert "-" in spid, f"{species}: expected sprite_id to keep the form dash"

    def test_cdn_slug_overrides(self) -> None:
        # Each entry was probed against the live Showdown CDN to confirm
        # the override actually points at an image (vs the default
        # slug which 404s). Keep this list in sync with
        # ``pokecore.teams._CDN_SLUG_OVERRIDES``.
        overrides = {
            "Basculin-Blue-Striped": "basculin-bluestriped",
            "Basculin-White-Striped": "basculin-whitestriped",
            "Darmanitan-Galar-Zen": "darmanitan-galar",
            "Dudunsparce-Three-Segment": "dudunsparce",
            "Farfetch'd-Galar": "sirfetchd",
            "Mr. Mime-Galar": "mrmime",
            "Necrozma-Dawn-Wings": "necrozma-dawnwings",
            "Necrozma-Dusk-Mane": "necrozma-duskmane",
            "Ogerpon-Cornerstone-Tera": "ogerpon-cornerstone",
            "Ogerpon-Hearthflame-Tera": "ogerpon-hearthflame",
            "Ogerpon-Teal-Tera": "ogerpon-teal",
            "Ogerpon-Wellspring-Tera": "ogerpon-wellspring",
            "Oricorio-Pom-Pom": "oricorio-pompom",
            "Pichu-Spiky-eared": "pichu-spikyeared",
            "Pikachu-Rock-Star": "pikachu-rockstar",
            "Toxtricity-Low-Key": "toxtricity-lowkey",
            "Toxtricity-Low-Key-Gmax": "toxtricity-lowkey",
            "Urshifu-Rapid-Strike": "urshifu-rapidstrike",
            "Urshifu-Rapid-Strike-Gmax": "urshifu-rapidstrike",
            "Tauros-Paldea-Aqua": "tauros-paldea",
            "Tauros-Paldea-Blaze": "tauros-paldea",
            "Tauros-Paldea-Combat": "tauros-paldea",
        }
        for species, expected in overrides.items():
            assert sprite_id(species) == expected, (
                f"{species}: expected {expected!r}, got {sprite_id(species)!r}"
            )

        # Live CDN guard: every override value must resolve to a real
        # sprite on at least one (folder, ext) combination. Catches
        # overrides that point at a slug Showdown has since dropped or
        # renamed, and the dead-slug half of the original oricorio-pom-pom
        # bug. It does NOT catch the "wrong species' slug" half of that
        # bug — ``oricorio-pau`` 200s on the CDN, so the original
        # override would have passed this probe while still rendering
        # the Psychic form's art for the Electric form. That class of
        # error still relies on the human-curated ``overrides`` dict
        # above and the focused per-form tests in
        # test_practice_service. Gated on POKE_BATTLES_RUN_SPRITE_PROBE=1
        # to keep default CI offline; mirrors the live-probe gate on
        # test_sprite_status_reports_slug_results in the api tests.
        if os.environ.get("POKE_BATTLES_RUN_SPRITE_PROBE") != "1":
            pytest.skip("set POKE_BATTLES_RUN_SPRITE_PROBE=1 to hit the live CDN")

        for slug in set(overrides.values()):
            assert any(_probe(f"{CDN}/{folder}/{slug}.{ext}") for folder, ext in FOLDER_EXT), (
                f"{slug!r} 404s in every (folder, ext) — override points at a dead slug"
            )


class TestNormalizeTeamPasteForShowdown:
    """Regression tests for the poke-env 0.15.0 ``from_showdown`` bug.

    poke-env's ``TeambuilderPokemon.from_showdown`` only sets ``mon.species``
    when the header has the ``Nickname (Species) @ Item`` form. A plain
    ``Species @ Item`` header leaves ``mon.species`` as ``None``, which
    produces a packed team with an empty species field and breaks the
    variant display on the client (team preview, switch buttons, sprite
    URLs, LLM switch matcher). ``normalize_team_paste_for_showdown``
    rewrites the header into ``Species (Species) @ Item`` form to make
    poke-env's parser extract the species correctly.
    """

    def test_none_passthrough(self) -> None:
        assert normalize_team_paste_for_showdown(None) is None

    def test_empty_passthrough(self) -> None:
        assert normalize_team_paste_for_showdown("") == ""

    def test_whitespace_only_passthrough(self) -> None:
        assert normalize_team_paste_for_showdown("   \n  \n") == "   \n  \n"

    def test_no_pokemon_blocks_unchanged(self) -> None:
        paste = "=== My Team ===\n// generated by showdown"
        assert normalize_team_paste_for_showdown(paste) == paste

    def test_base_species_header_wrapped(self) -> None:
        result = normalize_team_paste_for_showdown(
            "Pikachu @ Light Ball\nAbility: Static\n- Thunderbolt"
        )
        assert result is not None
        assert result.startswith("Pikachu (Pikachu) @ Light Ball")

    def test_regional_variant_wrapped(self) -> None:
        result = normalize_team_paste_for_showdown(
            "Slowking-Galar @ Assault Vest\nAbility: Regenerator\n- Psychic"
        )
        assert result is not None
        assert result.startswith("Slowking-Galar (Slowking-Galar) @ Assault Vest")

    def test_hisui_variant_wrapped(self) -> None:
        result = normalize_team_paste_for_showdown(
            "Typhlosion-Hisui @ Choice Specs\nAbility: Blaze\n- Eruption"
        )
        assert result is not None
        assert result.startswith("Typhlosion-Hisui (Typhlosion-Hisui) @ Choice Specs")

    def test_pom_pom_variant_wrapped(self) -> None:
        result = normalize_team_paste_for_showdown(
            "Oricorio-Pom-Pom @ Heavy-Duty Boots\nAbility: Dancer\n- Revelation Dance"
        )
        assert result is not None
        assert result.startswith("Oricorio-Pom-Pom (Oricorio-Pom-Pom) @ Heavy-Duty Boots")

    def test_mega_variant_wrapped(self) -> None:
        result = normalize_team_paste_for_showdown(
            "Aerodactyl-Mega @ Aerodactylite\nAbility: Tough Claws\n- Stone Edge"
        )
        assert result is not None
        assert result.startswith("Aerodactyl-Mega (Aerodactyl-Mega) @ Aerodactylite")

    def test_already_wrapped_idempotent(self) -> None:
        once = normalize_team_paste_for_showdown(
            "Pikachu @ Light Ball\nAbility: Static\n- Thunderbolt"
        )
        twice = normalize_team_paste_for_showdown(once)
        assert once == twice

    def test_idempotent_for_double_wrapped_input(self) -> None:
        already = "Charizard (Charizard) @ Leftovers\nAbility: Blaze\n- Flamethrower"
        result = normalize_team_paste_for_showdown(already)
        assert result == already

    def test_nickname_preserved(self) -> None:
        paste = "Big Blue (Garchomp) @ Choice Scarf\nAbility: Rough Skin\n- Earthquake"
        result = normalize_team_paste_for_showdown(paste)
        assert result == paste

    def test_nickname_with_variant_species_preserved(self) -> None:
        paste = "Mr. Mime (Mr. Mime-Galar) @ Leftovers\nAbility: Vital Spirit\n- Psychic"
        result = normalize_team_paste_for_showdown(paste)
        assert result == paste

    def test_gender_marker_preserved(self) -> None:
        result = normalize_team_paste_for_showdown(
            "Tauros (M) @ Leftovers\nAbility: Intimidate\n- Body Slam"
        )
        assert result is not None
        assert result.startswith("Tauros (Tauros) (M) @ Leftovers")

    def test_female_marker_preserved(self) -> None:
        result = normalize_team_paste_for_showdown(
            "Tauros (F) @ Leftovers\nAbility: Intimidate\n- Body Slam"
        )
        assert result is not None
        assert result.startswith("Tauros (Tauros) (F) @ Leftovers")

    def test_header_without_item_wrapped(self) -> None:
        result = normalize_team_paste_for_showdown("Pikachu")
        assert result == "Pikachu (Pikachu)"

    def test_header_with_gender_no_item_wrapped(self) -> None:
        result = normalize_team_paste_for_showdown("Pikachu (M)")
        assert result == "Pikachu (Pikachu) (M)"

    def test_full_team_normalized(self) -> None:
        paste = (
            "Typhlosion-Hisui @ Choice Specs\n"
            "Ability: Blaze\n"
            "Timid Nature\n"
            "- Eruption\n"
            "\n"
            "Slowking-Galar @ Assault Vest\n"
            "Ability: Regenerator\n"
            "- Psychic"
        )
        result = normalize_team_paste_for_showdown(paste)
        assert result is not None
        lines = result.split("\n")
        assert lines[0] == "Typhlosion-Hisui (Typhlosion-Hisui) @ Choice Specs"
        assert lines[1] == "Ability: Blaze"
        assert lines[2] == "Timid Nature"
        assert lines[3] == "- Eruption"
        assert lines[4] == ""
        assert lines[5] == "Slowking-Galar (Slowking-Galar) @ Assault Vest"
        assert lines[6] == "Ability: Regenerator"
        assert lines[7] == "- Psychic"

    def test_blank_line_within_block_does_not_split_mon(self) -> None:
        """Regression: a stray blank line between two non-move lines of a
        Pokémon block (e.g. between EVs and Nature) must NOT be treated
        as a block separator. Otherwise the next non-blank line gets
        wrapped as a new header, which poke-env tries to parse as a
        species name and produces a malformed packed team that Showdown
        silently rejects — breaking every battle that uses a non-random
        team with such a paste."""
        paste = (
            "Garchomp @ Choice Scarf\n"
            "Ability: Rough Skin\n"
            "EVs: 252 Atk / 4 SpD / 252 Spe\n"
            "\n"
            "Jolly Nature\n"
            "- Earthquake\n"
            "- Outrage\n"
        )
        result = normalize_team_paste_for_showdown(paste)
        assert result is not None
        assert "Jolly Nature (Jolly Nature)" not in result
        assert "EVs: 252 Atk / 4 SpD / 252 Spe (EVs:" not in result
        assert "Jolly Nature\n" in result
        assert "EVs: 252 Atk / 4 SpD / 252 Spe\n" in result
        # End-to-end: the packed team must still pack to a single mon.
        pytest.importorskip("poke_env")
        from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder

        packed = ConstantTeambuilder(result).packed_team
        mons = ConstantTeambuilder(result)._mons
        assert len(mons) == 1
        assert mons[0].species == "Garchomp"
        assert mons[0].nature == "Jolly"
        assert "Garchomp" in packed
        assert "Jolly" in packed

    def test_blank_line_before_first_move_does_not_split_mon(self) -> None:
        """A blank line between Ability and the first move line is also
        common in Showdown exports and must not be treated as a
        separator."""
        paste = (
            "Pikachu @ Light Ball\n"
            "Ability: Static\n"
            "\n"
            "EVs: 252 SpA / 252 Spe\n"
            "Timid Nature\n"
            "- Thunderbolt\n"
        )
        result = normalize_team_paste_for_showdown(paste)
        assert result is not None
        assert "Timid Nature (Timid Nature)" not in result
        assert "EVs: 252 SpA / 252 Spe (EVs:" not in result
        assert "Ability: Static" in result
        assert "EVs: 252 SpA / 252 Spe" in result

    def test_multi_blank_lines_within_block_preserved(self) -> None:
        """Multiple consecutive blank lines within a block must not
        cause any wrapping after the first one (they're all stray
        whitespace until a real move line appears)."""
        paste = "Pikachu @ Light Ball\nAbility: Static\n\n\n\nTimid Nature\n- Thunderbolt\n"
        result = normalize_team_paste_for_showdown(paste)
        assert result is not None
        assert "Timid Nature (Timid Nature)" not in result
        assert "Timid Nature\n" in result

    def test_blank_line_between_blocks_still_splits(self) -> None:
        """Blank lines between blocks (i.e. after a move line) must
        still be treated as block separators so the next mon's header
        gets wrapped."""
        paste = (
            "Pikachu @ Light Ball\n"
            "Ability: Static\n"
            "- Thunderbolt\n"
            "\n"
            "Charizard @ Choice Specs\n"
            "Ability: Blaze\n"
            "- Flamethrower\n"
        )
        result = normalize_team_paste_for_showdown(paste)
        assert result is not None
        lines = result.split("\n")
        assert lines[0] == "Pikachu (Pikachu) @ Light Ball"
        assert lines[2] == "- Thunderbolt"
        assert lines[3] == ""
        assert lines[4] == "Charizard (Charizard) @ Choice Specs"
        assert lines[5] == "Ability: Blaze"
        assert lines[6] == "- Flamethrower"

    def test_poke_env_handles_blank_line_within_block(self) -> None:
        """End-to-end regression: a real Showdown paste with a blank
        line inside a block must pack to the same mon list as the
        clean paste."""
        pytest.importorskip("poke_env")
        from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder

        clean = (
            "Garchomp @ Choice Scarf\n"
            "Ability: Rough Skin\n"
            "EVs: 252 Atk / 4 SpD / 252 Spe\n"
            "Jolly Nature\n"
            "- Earthquake\n"
            "- Outrage\n"
            "- Stone Edge\n"
            "- Stealth Rock\n"
        )
        with_blank = clean.replace("4 SpD / 252 Spe\n", "4 SpD / 252 Spe\n\n")
        normalized = normalize_team_paste_for_showdown(with_blank)
        assert normalized is not None
        mons = ConstantTeambuilder(normalized)._mons
        assert len(mons) == 1
        assert mons[0].species == "Garchomp"
        assert mons[0].nature == "Jolly"
        assert mons[0].moves == ["Earthquake", "Outrage", "Stone Edge", "Stealth Rock"]

    def test_team_name_and_comments_preserved(self) -> None:
        paste = (
            "=== My Team ===\n"
            "// generated by showdown\n"
            "\n"
            "Typhlosion-Hisui @ Choice Specs\n"
            "Ability: Blaze\n"
            "- Eruption"
        )
        result = normalize_team_paste_for_showdown(paste)
        assert result is not None
        lines = result.split("\n")
        assert lines[0] == "=== My Team ==="
        assert lines[1] == "// generated by showdown"
        assert lines[3] == "Typhlosion-Hisui (Typhlosion-Hisui) @ Choice Specs"

    def test_poke_env_picks_up_species(self) -> None:
        """End-to-end: parse a variant header through poke-env and confirm
        the species field is now populated (the original bug)."""
        pytest.importorskip("poke_env")
        from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder

        original = "Typhlosion-Hisui @ Choice Specs\nAbility: Blaze\nTimid Nature\n- Eruption"
        before = ConstantTeambuilder(original)._mons[0]
        assert before.species is None
        assert before.nickname == "Typhlosion-Hisui"

        normalized = normalize_team_paste_for_showdown(original)
        assert normalized is not None
        after = ConstantTeambuilder(normalized)._mons[0]
        assert after.species == "Typhlosion-Hisui"
        assert after.nickname == "Typhlosion-Hisui"

    def test_poke_env_slowking_galar_species(self) -> None:
        pytest.importorskip("poke_env")
        from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder

        original = "Slowking-Galar @ Assault Vest\nAbility: Regenerator\n- Psychic"
        before = ConstantTeambuilder(original)._mons[0]
        assert before.species is None

        normalized = normalize_team_paste_for_showdown(original)
        assert normalized is not None
        after = ConstantTeambuilder(normalized)._mons[0]
        assert after.species == "Slowking-Galar"

    def test_poke_env_oricorio_pom_pom_species(self) -> None:
        pytest.importorskip("poke_env")
        from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder

        original = "Oricorio-Pom-Pom @ Heavy-Duty Boots\nAbility: Dancer\n- Revelation Dance"
        before = ConstantTeambuilder(original)._mons[0]
        assert before.species is None

        normalized = normalize_team_paste_for_showdown(original)
        assert normalized is not None
        after = ConstantTeambuilder(normalized)._mons[0]
        assert after.species == "Oricorio-Pom-Pom"

    def test_poke_env_mega_species(self) -> None:
        pytest.importorskip("poke_env")
        from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder

        original = "Aerodactyl-Mega @ Aerodactylite\nAbility: Tough Claws\n- Stone Edge"
        before = ConstantTeambuilder(original)._mons[0]
        assert before.species is None

        normalized = normalize_team_paste_for_showdown(original)
        assert normalized is not None
        after = ConstantTeambuilder(normalized)._mons[0]
        assert after.species == "Aerodactyl-Mega"
