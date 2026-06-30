"""Canonical battle state dataclasses.

This module is the single source of truth for "what the agent sees." It has
zero poke-env dependencies — the adapter from poke-env types lives in
:mod:`pokeengine.player.state_from_battle`. The LLM-facing formatter lives in
:mod:`pokellm.state_render`.

Re-exported from :mod:`pokecore`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class KnownMove:
    """One move known by a Pokémon in battle."""

    id: str
    name: str
    type: str
    category: str
    base_power: int
    accuracy: int
    pp: int
    max_pp: int
    priority: int = 0
    target: str = "normal"
    drain: float = 0.0
    recoil: float = 0.0
    healing: float = 0.0


@dataclass(frozen=True, slots=True)
class PokemonState:
    """A Pokémon's full battle snapshot."""

    species: str
    nickname: str
    types: tuple[str, ...]
    level: int
    hp_fraction: float
    status: str | None
    ability: str | None
    item: str | None
    tera_type: str | None
    is_terastallized: bool
    is_active: bool
    is_fainted: bool
    boosts: dict[str, int] = field(default_factory=dict)
    moves: tuple[KnownMove, ...] = ()


@dataclass(frozen=True, slots=True)
class FieldState:
    """The field state of a battle."""

    weather: str | None
    terrain: str | None
    trick_room: bool
    player_hazards: dict[str, int]
    opponent_hazards: dict[str, int]


@dataclass(frozen=True, slots=True)
class BattleState:
    """A single battle's full snapshot.

    ``player`` and ``opponent`` are the two sides, each a list of
    :class:`PokemonState` (active first when present). The bench is included so
    the agent can reason about switches.
    """

    battle_id: str
    turn: int
    format: str
    player_username: str
    opponent_username: str
    player: tuple[PokemonState, ...]
    opponent: tuple[PokemonState, ...]
    field: FieldState
    can_tera: bool = False


__all__ = [
    "BattleState",
    "FieldState",
    "KnownMove",
    "PokemonState",
]
