"""Unit tests for pokecore.formats."""

from __future__ import annotations

import pytest

from pokecore.formats import (
    GEN9_OU,
    GEN9_RANDOM_BATTLE,
    GEN9_RATED_BATTLE,
    SUPPORTED_FORMATS,
    Format,
    FormatKind,
    get_format,
)
from pokecore.types import Generation


class TestFormat:
    def test_gen9_randombattle(self) -> None:
        fmt = GEN9_RANDOM_BATTLE
        assert fmt.id == "gen9randombattle"
        assert fmt.generation == Generation.GEN9
        assert fmt.kind == FormatKind.SINGLES
        assert fmt.random_team is True
        assert fmt.level == 84

    def test_invalid_team_size(self) -> None:
        with pytest.raises(ValueError, match="team_size"):
            Format(id="x", name="x", generation=Generation.GEN9, team_size=7)

    def test_invalid_level(self) -> None:
        with pytest.raises(ValueError, match="level"):
            Format(id="x", name="x", generation=Generation.GEN9, level=0)

    def test_species_legal_no_bans(self) -> None:
        fmt = Format(id="x", name="x", generation=Generation.GEN9)
        assert fmt.is_species_legal("pikachu")

    def test_species_illegal_banned(self) -> None:
        fmt = Format(
            id="x",
            name="x",
            generation=Generation.GEN9,
            banned_species=frozenset({"pikachu"}),
        )
        assert not fmt.is_species_legal("pikachu")
        assert fmt.is_species_legal("charizard")

    def test_species_legal_allowed_only(self) -> None:
        fmt = Format(
            id="x",
            name="x",
            generation=Generation.GEN9,
            allowed_species=frozenset({"pikachu", "charizard"}),
        )
        assert fmt.is_species_legal("pikachu")
        assert not fmt.is_species_legal("mewtwo")


class TestGetFormat:
    def test_known(self) -> None:
        assert get_format("gen9randombattle") is GEN9_RANDOM_BATTLE
        assert get_format("gen9ou") is GEN9_OU
        assert get_format("gen9battle") is GEN9_RATED_BATTLE

    def test_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="Unknown format"):
            get_format("gen9invalid")

    def test_supported_formats_unique(self) -> None:
        ids = [f.id for f in SUPPORTED_FORMATS]
        assert len(ids) == len(set(ids))
