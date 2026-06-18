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
    requires_team: bool = False
    active_slots: int = 1
    practice_supported: bool = True
    experimental: bool = False
    rules: frozenset[str] = field(default_factory=frozenset)
    banned_species: frozenset[str] = field(default_factory=frozenset)
    allowed_species: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.team_size <= 6:
            raise ValueError(f"team_size must be in [1, 6], got {self.team_size}")
        if not 1 <= self.level <= 100:
            raise ValueError(f"level must be in [1, 100], got {self.level}")
        if not 1 <= self.active_slots <= 3:
            raise ValueError(f"active_slots must be in [1, 3], got {self.active_slots}")

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
    requires_team=True,
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
    requires_team=True,
    rules=frozenset({"Sleep Clause", "Species Clause", "OHKO Clause", "Evasion Clause"}),
)

GEN9_UBERS = Format(
    id="gen9ubers",
    name="Gen 9 Ubers",
    generation=Generation.GEN9,
    kind=FormatKind.SINGLES,
    team_size=6,
    level=100,
    requires_team=True,
)

GEN9_UU = Format(
    id="gen9uu",
    name="Gen 9 UU",
    generation=Generation.GEN9,
    kind=FormatKind.SINGLES,
    team_size=6,
    level=100,
    requires_team=True,
)

GEN9_DOUBLES_OU = Format(
    id="gen9doublesou",
    name="Gen 9 Doubles OU",
    generation=Generation.GEN9,
    kind=FormatKind.DOUBLES,
    team_size=6,
    level=100,
    requires_team=True,
    active_slots=2,
)

GEN9_DOUBLES_UBERS = Format(
    id="gen9doublesubers",
    name="Gen 9 Doubles Ubers",
    generation=Generation.GEN9,
    kind=FormatKind.DOUBLES,
    team_size=6,
    level=100,
    requires_team=True,
    active_slots=2,
)

GEN9_RANDOM_DOUBLES_BATTLE = Format(
    id="gen9randomdoublesbattle",
    name="Gen 9 Random Doubles Battle",
    generation=Generation.GEN9,
    kind=FormatKind.DOUBLES,
    team_size=6,
    level=84,
    random_team=True,
    active_slots=2,
)

GEN9_VGC_2025_REG_I = Format(
    id="gen9vgc2025regi",
    name="Gen 9 VGC 2025 Reg I",
    generation=Generation.GEN9,
    kind=FormatKind.DOUBLES,
    team_size=6,
    level=50,
    requires_team=True,
    active_slots=2,
)

GEN9_NATIONAL_DEX = Format(
    id="gen9nationaldex",
    name="Gen 9 National Dex",
    generation=Generation.GEN9,
    kind=FormatKind.SINGLES,
    team_size=6,
    level=100,
    requires_team=True,
)

GEN9_NATIONAL_DEX_UBERS = Format(
    id="gen9nationaldexubers",
    name="Gen 9 National Dex Ubers",
    generation=Generation.GEN9,
    kind=FormatKind.SINGLES,
    team_size=6,
    level=100,
    requires_team=True,
)

GEN9_NATIONAL_DEX_DOUBLES = Format(
    id="gen9nationaldexdoubles",
    name="Gen 9 National Dex Doubles",
    generation=Generation.GEN9,
    kind=FormatKind.DOUBLES,
    team_size=6,
    level=100,
    requires_team=True,
    active_slots=2,
)

GEN9_NATIONAL_DEX_DOUBLES_UBERS = Format(
    id="gen9nationaldexdoublesubers",
    name="Gen 9 National Dex Doubles Ubers",
    generation=Generation.GEN9,
    kind=FormatKind.DOUBLES,
    team_size=6,
    level=100,
    requires_team=True,
    active_slots=2,
)

SUPPORTED_FORMATS: tuple[Format, ...] = (
    GEN9_RANDOM_BATTLE,
    GEN9_RANDOM_DOUBLES_BATTLE,
    GEN9_RATED_BATTLE,
    GEN9_OU,
    GEN9_UBERS,
    GEN9_UU,
    GEN9_DOUBLES_OU,
    GEN9_DOUBLES_UBERS,
    GEN9_VGC_2025_REG_I,
    GEN9_NATIONAL_DEX,
    GEN9_NATIONAL_DEX_UBERS,
    GEN9_NATIONAL_DEX_DOUBLES,
    GEN9_NATIONAL_DEX_DOUBLES_UBERS,
)


def get_format(format_id: str) -> Format:
    for fmt in SUPPORTED_FORMATS:
        if fmt.id == format_id:
            return fmt
    raise KeyError(f"Unknown format: {format_id}")
