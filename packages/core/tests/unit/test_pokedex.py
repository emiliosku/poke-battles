"""Tests for the lightweight Showdown Pokédex parser."""

from __future__ import annotations

from pathlib import Path

import pytest

import pokecore.pokedex as pokedex


@pytest.fixture
def pokedex_file(tmp_path: Path) -> Path:
    path = tmp_path / "pokedex.js"
    path.write_text(
        """const Pokedex = {
  charmander: {
    num: 4,
    name: "Charmander",
    types: ["Fire"],
    baseStats: { hp: 39, atk: 52, def: 43, spa: 60, spd: 50, spe: 65 },
    abilities: { 0: "Blaze", H: "Solar Power" },
  },
  bulbasaur:{
    name: "Bulbasaur",
    num: 1,
    types: ["Grass", "Poison"],
    baseStats: { hp: 45, atk: 49 },
    abilities: { 0: "Overgrow", H: "Chlorophyll" },
  },
  flabebe: {
    name: "Flab\\u00e9b\\u00e9",
    num: 669,
    types: ["Fairy"],
  },
  incomplete: { types: ["Normal"] },
};""",
        encoding="utf-8",
    )
    return path


def test_load_pokedex_parses_and_sorts_entries(pokedex_file: Path) -> None:
    entries = pokedex.load_pokedex(pokedex_file)

    assert [entry.species_id for entry in entries] == ["bulbasaur", "charmander", "flabebe"]
    assert entries[0].types == ("Grass", "Poison")
    assert entries[0].base_stats == {"hp": 45, "atk": 49}
    assert entries[1].abilities == {"0": "Blaze", "H": "Solar Power"}
    assert entries[2].name == "Flabébé"
    assert entries[2].base_stats == {}


def test_load_pokedex_returns_empty_for_missing_or_invalid_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.js"
    invalid = tmp_path / "invalid.js"
    invalid.write_text("const NotPokedex = {};", encoding="utf-8")

    assert pokedex.load_pokedex(missing) == ()
    assert pokedex.load_pokedex(invalid) == ()


def test_public_lookups_use_default_pokedex_path(
    monkeypatch: pytest.MonkeyPatch, pokedex_file: Path
) -> None:
    pokedex.load_pokedex.cache_clear()
    monkeypatch.setattr(pokedex, "_DEFAULT_PATH", pokedex_file)

    assert pokedex.species_ids() == ("bulbasaur", "charmander", "flabebe")
    assert pokedex.get("charmander") is not None
    assert pokedex.get("charmander").num == 4  # type: ignore[union-attr]
    assert pokedex.get("missing") is None

    pokedex.load_pokedex.cache_clear()
