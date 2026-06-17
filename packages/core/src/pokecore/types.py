"""Core domain types for the Pokémon battle engine.

Pure data definitions with no I/O. Re-exported from :mod:`pokecore`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum


class Type(StrEnum):
    NORMAL = "normal"
    FIRE = "fire"
    WATER = "water"
    ELECTRIC = "electric"
    GRASS = "grass"
    ICE = "ice"
    FIGHTING = "fighting"
    POISON = "poison"
    GROUND = "ground"
    FLYING = "flying"
    PSYCHIC = "psychic"
    BUG = "bug"
    ROCK = "rock"
    GHOST = "ghost"
    DRAGON = "dragon"
    DARK = "dark"
    STEEL = "steel"
    FAIRY = "fairy"
    TYPELESS = "typeless"


class Stat(StrEnum):
    HP = "hp"
    ATTACK = "atk"
    DEFENSE = "def"
    SPECIAL_ATTACK = "spa"
    SPECIAL_DEFENSE = "spd"
    SPEED = "spe"


class Status(StrEnum):
    HEALTHY = "healthy"
    BURN = "brn"
    FREEZE = "frz"
    PARALYSIS = "par"
    POISON = "psn"
    BAD_POISON = "tox"
    SLEEP = "slp"
    FAINT = "fnt"


class Category(StrEnum):
    PHYSICAL = "physical"
    SPECIAL = "special"
    STATUS = "status"


class Generation(StrEnum):
    GEN1 = "gen1"
    GEN2 = "gen2"
    GEN3 = "gen3"
    GEN4 = "gen4"
    GEN5 = "gen5"
    GEN6 = "gen6"
    GEN7 = "gen7"
    GEN8 = "gen8"
    GEN9 = "gen9"


class Nature(StrEnum):
    HARDY = "hardy"
    LONELY = "lonely"
    BRAVE = "brave"
    ADAMANT = "adamant"
    NAUGHTY = "naughty"
    BOLD = "bold"
    DOCILE = "docile"
    RELAXED = "relaxed"
    IMPISH = "impish"
    LAX = "lax"
    TIMID = "timid"
    HASTY = "hasty"
    SERIOUS = "serious"
    JOLLY = "jolly"
    NAIVE = "naive"
    MODEST = "modest"
    MILD = "mild"
    QUIET = "quiet"
    BASHFUL = "bashful"
    RASH = "rash"
    CALM = "calm"
    GENTLE = "gentle"
    SASSY = "sassy"
    CAREFUL = "careful"
    QUIRKY = "quirky"


NEUTRAL_NATURES: frozenset[Nature] = frozenset(
    {Nature.HARDY, Nature.DOCILE, Nature.SERIOUS, Nature.BASHFUL, Nature.QUIRKY}
)

NATURE_BOOSTS: dict[Nature, tuple[Stat, Stat]] = {
    Nature.LONELY: (Stat.ATTACK, Stat.DEFENSE),
    Nature.BRAVE: (Stat.ATTACK, Stat.SPEED),
    Nature.ADAMANT: (Stat.ATTACK, Stat.SPECIAL_ATTACK),
    Nature.NAUGHTY: (Stat.ATTACK, Stat.SPECIAL_DEFENSE),
    Nature.BOLD: (Stat.DEFENSE, Stat.ATTACK),
    Nature.RELAXED: (Stat.DEFENSE, Stat.SPEED),
    Nature.IMPISH: (Stat.DEFENSE, Stat.SPECIAL_ATTACK),
    Nature.LAX: (Stat.DEFENSE, Stat.SPECIAL_DEFENSE),
    Nature.TIMID: (Stat.SPEED, Stat.ATTACK),
    Nature.HASTY: (Stat.SPEED, Stat.DEFENSE),
    Nature.JOLLY: (Stat.SPEED, Stat.SPECIAL_ATTACK),
    Nature.NAIVE: (Stat.SPEED, Stat.SPECIAL_DEFENSE),
    Nature.MODEST: (Stat.SPECIAL_ATTACK, Stat.ATTACK),
    Nature.MILD: (Stat.SPECIAL_ATTACK, Stat.DEFENSE),
    Nature.QUIET: (Stat.SPECIAL_ATTACK, Stat.SPEED),
    Nature.RASH: (Stat.SPECIAL_ATTACK, Stat.SPECIAL_DEFENSE),
    Nature.CALM: (Stat.SPECIAL_DEFENSE, Stat.ATTACK),
    Nature.GENTLE: (Stat.SPECIAL_DEFENSE, Stat.DEFENSE),
    Nature.SASSY: (Stat.SPECIAL_DEFENSE, Stat.SPEED),
    Nature.CAREFUL: (Stat.SPECIAL_DEFENSE, Stat.SPECIAL_ATTACK),
}


@dataclass(frozen=True, slots=True)
class Boosts:
    """Stat boosts in the range -6..+6."""

    atk: int = 0
    def_: int = 0
    spa: int = 0
    spd: int = 0
    spe: int = 0
    accuracy: int = 0
    evasion: int = 0

    def __post_init__(self) -> None:
        for field in (self.atk, self.def_, self.spa, self.spd, self.spe):
            if not -6 <= field <= 6:
                raise ValueError(f"Stat boost {field} out of range [-6, 6]")

    def get(self, stat: Stat) -> int:
        return {
            Stat.ATTACK: self.atk,
            Stat.DEFENSE: self.def_,
            Stat.SPECIAL_ATTACK: self.spa,
            Stat.SPECIAL_DEFENSE: self.spd,
            Stat.SPEED: self.spe,
        }.get(stat, 0)


@dataclass(frozen=True, slots=True)
class NatureModifier:
    """Multiplier applied to a stat by a Pokémon's nature."""

    increased: Stat | None
    decreased: Stat | None

    @classmethod
    def from_nature(cls, nature: Nature) -> NatureModifier:
        if nature in NEUTRAL_NATURES:
            return cls(None, None)
        increased, decreased = NATURE_BOOSTS[nature]
        return cls(increased, decreased)

    def multiplier(self, stat: Stat) -> float:
        if stat == self.increased:
            return 1.1
        if stat == self.decreased:
            return 0.9
        return 1.0


@dataclass(frozen=True, slots=True)
class TypePair:
    """A Pokémon's typing (1 or 2 types)."""

    primary: Type
    secondary: Type | None = None

    def __iter__(self) -> Iterator[Type]:
        yield self.primary
        if self.secondary is not None:
            yield self.secondary

    def __contains__(self, item: object) -> bool:
        return item == self.primary or item == self.secondary

    def __len__(self) -> int:
        return 1 if self.secondary is None else 2

    def __str__(self) -> str:
        if self.secondary is None:
            return self.primary.value
        return f"{self.primary.value}/{self.secondary.value}"


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
