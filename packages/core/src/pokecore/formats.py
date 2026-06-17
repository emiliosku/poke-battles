"""Pokémon Showdown battle formats.

Each :class:`Format` describes a legal battle mode: generation, rules, and
optionally which format string to send to ``/format`` on the Showdown protocol.

Re-exported from :mod:`pokecore`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pokecore.types import Generation


class FormatKind(StrEnum):
    SINGLES = "singles"
    DOUBLES = "doubles"
    TRIPLES = "triples"
    FREE_FOR_ALL = "ffa"


@dataclass(frozen=True, slots=True)
class Format:
    id: str
    name: str
    generation: Generation
    kind: FormatKind = FormatKind.SINGLES
    team_size: int = 6
    level: int = 100
    random_team: bool = False
    rules: frozenset[str] = field(default_factory=frozenset)
    banned_species: frozenset[str] = field(default_factory=frozenset)
    allowed_species: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.team_size <= 6:
            raise ValueError(f"team_size must be in [1, 6], got {self.team_size}")
        if not 1 <= self.level <= 100:
            raise ValueError(f"level must be in [1, 100], got {self.level}")

    @property
    def showdown_id(self) -> str:
        return self.id

    @property
    def is_random(self) -> bool:
        return self.random_team

    def is_species_legal(self, species_id: str) -> bool:
        if self.allowed_species is not None and species_id not in self.allowed_species:
            return False
        return species_id not in self.banned_species


GEN9_RANDOM_BATTLE = Format(
    id="gen9randombattle",
    name="Gen 9 Random Battle",
    generation=Generation.GEN9,
    kind=FormatKind.SINGLES,
    team_size=6,
    level=84,
    random_team=True,
    rules=frozenset({"Sleep Clause", "Species Clause", "OHKO Clause", "Evasion Clause"}),
)

GEN9_RATED_BATTLE = Format(
    id="gen9battle",
    name="Gen 9 Rated Battle",
    generation=Generation.GEN9,
    kind=FormatKind.SINGLES,
    team_size=6,
    level=100,
    random_team=False,
    rules=frozenset({"Sleep Clause", "Species Clause", "OHKO Clause", "Evasion Clause"}),
)

GEN9_OU = Format(
    id="gen9ou",
    name="Gen 9 OU",
    generation=Generation.GEN9,
    kind=FormatKind.SINGLES,
    team_size=6,
    level=100,
    random_team=False,
    rules=frozenset({"Sleep Clause", "Species Clause", "OHKO Clause", "Evasion Clause"}),
)

SUPPORTED_FORMATS: tuple[Format, ...] = (
    GEN9_RANDOM_BATTLE,
    GEN9_RATED_BATTLE,
    GEN9_OU,
)


def get_format(format_id: str) -> Format:
    for fmt in SUPPORTED_FORMATS:
        if fmt.id == format_id:
            return fmt
    raise KeyError(f"Unknown format: {format_id}")
