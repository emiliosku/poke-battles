"""Format legality validator for :class:`pokecore.Team`.

Phase 1: structural checks (team size, no duplicate species, no banned moves,
EV/IV ranges). Phase 3 will replace the species/move legality lookups with
data pulled from the Smogon image's ``data/mods/gen9`` folder.

Re-exported from :mod:`pokeengine`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from pokecore import Format, Team
from pokeengine.smogon_data import (
    valid_ability,
    valid_item,
    valid_move,
    valid_species,
)

MAX_MOVES = 4
MIN_MOVES = 1


def validate_team(
    team: Team, fmt: Format, *, known_species: Iterable[str] | None = None
) -> list[str]:
    """Return a list of legality error messages; empty list means legal."""
    errors: list[str] = []
    if len(team.pokemon) > fmt.team_size:
        errors.append(f"Team has {len(team.pokemon)} Pokemon but {fmt.id} allows {fmt.team_size}.")
    species_counts = Counter(p.species_id for p in team.pokemon)
    dups = [sid for sid, c in species_counts.items() if c > 1]
    if dups:
        errors.append(f"Duplicate species: {sorted(dups)}")
    if known_species is not None:
        legal = set(known_species)
        for pkmn in team.pokemon:
            if pkmn.species_id not in legal:
                errors.append(f"Unknown species: {pkmn.species_id!r}")
    for pkmn in team.pokemon:
        if not 1 <= pkmn.level <= fmt.level:
            errors.append(f"{pkmn.species_id}: level {pkmn.level} not in [1, {fmt.level}]")
        if not MIN_MOVES <= len(pkmn.moves) <= MAX_MOVES:
            errors.append(
                f"{pkmn.species_id}: {len(pkmn.moves)} moves not in [{MIN_MOVES}, {MAX_MOVES}]"
            )
        if pkmn.evs.total > 510:
            errors.append(f"{pkmn.species_id}: EV total {pkmn.evs.total} > 510")
        for stat, value in pkmn.evs.values.items():
            if value > 252:
                errors.append(f"{pkmn.species_id}: EV {stat.value}={value} > 252")
        for stat, value in pkmn.ivs.values.items():
            if value > 31:
                errors.append(f"{pkmn.species_id}: IV {stat.value}={value} > 31")
        if pkmn.tera_type is not None and fmt.generation.value < "gen9":
            errors.append(
                f"{pkmn.species_id}: tera type {pkmn.tera_type.value} not allowed in {fmt.generation.value}"
            )
        if not fmt.is_species_legal(pkmn.species_id):
            errors.append(f"{pkmn.species_id}: not legal in {fmt.id}")
        if not valid_species(pkmn.species_id):
            errors.append(f"{pkmn.species_id}: unknown species")
        if pkmn.item and not valid_item(pkmn.item):
            errors.append(f"{pkmn.species_id}: unknown item {pkmn.item}")
        if pkmn.ability and not valid_ability(pkmn.ability):
            errors.append(f"{pkmn.species_id}: unknown ability {pkmn.ability}")
        for move in pkmn.moves:
            if not valid_move(move.name):
                errors.append(f"{pkmn.species_id}: unknown move {move.name}")
    return errors


__all__ = ["validate_team"]
