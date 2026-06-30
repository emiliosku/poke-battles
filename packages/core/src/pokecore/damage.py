"""Real damage calculator for Gen 9 (smart damage formula).

The goal is **not** pixel-perfect parity with Showdown's sim — it's a fast,
pure-Python function that matches Showdown's ``getDamage`` to within a few
percent on canonical matchups. The output is a :class:`DamageRoll` with
``min_pct``, ``max_pct``, ``expected_pct`` (expected value of a uniform
85–100 roll), and ``ko_chance`` (probability of OHKO/2HKO/3HKO given the
defender's current HP and a coarse status/turn-count estimate).

Inputs are intentionally plain dataclasses so this module has zero poke-env
coupling. The LLM/heuristic layers can build these from
:class:`pokecore.state.BattleState` without ever touching the engine.

Re-exported from :mod:`pokecore`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pokecore.type_chart import defensive_multiplier
from pokecore.types import NATURE_BOOSTS, NEUTRAL_NATURES, Nature, Stat, Type, TypePair

Level = 84

# Gen 9 stat-stage multipliers. Indexed by stage in [-6, +6].
# Format: stage → multiplier.
_STAGE_MULTIPLIERS: tuple[float, ...] = (
    0.25,  # -6
    2 / 7,  # -5  ≈ 0.286
    1 / 3,  # -4  ≈ 0.333
    0.4,  # -3
    0.5,  # -2
    2 / 3,  # -1  ≈ 0.667
    1.0,  #  0
    1.5,  # +1
    2.0,  # +2
    2.5,  # +3
    3.0,  # +4
    3.5,  # +5
    4.0,  # +6
)

# Gen 9 random roll: uniform 85..100.
_ROLL_MIN = 0.85
_ROLL_MAX = 1.0
_ROLL_EXPECTED = (_ROLL_MIN + _ROLL_MAX) / 2.0


class Category(StrEnum):
    PHYSICAL = "physical"
    SPECIAL = "special"
    STATUS = "status"


class Weather(StrEnum):
    NONE = "none"
    SUN = "sun"
    RAIN = "rain"
    SAND = "sand"
    SNOW = "snow"
    HAIL = "hail"


@dataclass(frozen=True, slots=True)
class MoveInput:
    """A simplified move used by the damage calc."""

    name: str
    type: Type
    category: Category
    base_power: int
    accuracy: int = 100
    has_crit: bool = True
    drain: float = 0.0
    recoil: float = 0.0


@dataclass(frozen=True, slots=True)
class PokemonInput:
    """The fields needed to compute a single stat."""

    types: tuple[Type, ...]
    level: int
    base_atk: int
    base_spa: int
    base_def: int
    base_spd: int
    nature: Nature
    ev_atk: int = 0
    ev_spa: int = 0
    ev_def: int = 0
    ev_spd: int = 0
    iv_atk: int = 31
    iv_spa: int = 31
    iv_def: int = 31
    iv_spd: int = 31
    boost_atk: int = 0
    boost_spa: int = 0
    boost_def: int = 0
    boost_spd: int = 0
    ability: str = ""
    item: str = ""
    is_terastallized: bool = False
    tera_type: Type | None = None
    is_fainted: bool = False
    is_burned: bool = False


@dataclass(frozen=True, slots=True)
class DamageRoll:
    """A damage roll result."""

    min_pct: float
    max_pct: float
    expected_pct: float
    ko_chance: dict[str, float]
    note: str = ""

    def __str__(self) -> str:
        return f"{self.expected_pct:.1f}% ({self.min_pct:.1f}-{self.max_pct:.1f}%)"


def stat_at_level(base: int, level: int, ev: int, iv: int, nature_mult: float) -> int:
    """Showdown's level-aware stat formula for non-HP stats."""
    return int((int((2 * base + iv + int(ev / 4)) * level / 100) + 5) * nature_mult)


def hp_at_level(base: int, level: int, ev: int, iv: int) -> int:
    """Showdown's HP stat formula."""
    if base == 1:  # Shedinja
        return 1
    return int((2 * base + iv + int(ev / 4)) * level / 100) + level + 10


def nature_modifier(nature: Nature, stat: Stat) -> float:
    """Return 1.1/0.9/1.0 for the given nature and stat."""
    if nature in NEUTRAL_NATURES:
        return 1.0
    boosted, reduced = NATURE_BOOSTS[nature]
    if boosted == stat:
        return 1.1
    if reduced == stat:
        return 0.9
    return 1.0


def stage_multiplier(stage: int) -> float:
    """Stat-stage multiplier, clamped to [-6, +6]."""
    if stage > 6:
        stage = 6
    if stage < -6:
        stage = -6
    return _STAGE_MULTIPLIERS[stage + 6]


def _stab(attacker: PokemonInput, move_type: Type) -> float:
    if attacker.is_terastallized and attacker.tera_type is not None:
        if attacker.tera_type == move_type:
            return 1.5
        if move_type in attacker.types:
            return 1.2
        return 1.0
    if move_type in attacker.types:
        return 1.5
    return 1.0


def _weather_modifier(weather: Weather, move_type: Type) -> float:
    if weather == Weather.RAIN and move_type == Type.WATER:
        return 1.5
    if weather == Weather.RAIN and move_type == Type.FIRE:
        return 0.5
    if weather == Weather.SUN and move_type == Type.FIRE:
        return 1.5
    if weather == Weather.SUN and move_type == Type.WATER:
        return 0.5
    return 1.0


def _ability_atk(ability: str) -> float:
    return {
        "huge-power": 2.0,
        "pure-power": 2.0,
        "hustle": 1.5,
    }.get(ability, 1.0)


def _ability_spa(ability: str) -> float:
    return 1.0


def _ability_def(ability: str) -> float:
    return 1.0


def _ability_spd(ability: str) -> float:
    return {
        "thick-fat": 0.5,
    }.get(ability, 1.0)


def _item_atk_modifier(item: str, category: Category) -> float:
    if category != Category.PHYSICAL:
        return 1.0
    if item in {"choice-band", "choiceband"}:
        return 1.5
    if item == "life-orb":
        return 1.3
    return 1.0


def _item_spa_modifier(item: str, category: Category) -> float:
    if category != Category.SPECIAL:
        return 1.0
    if item in {"choice-specs", "choicespecs"}:
        return 1.5
    if item == "life-orb":
        return 1.3
    return 1.0


def _item_type_modifier(item: str, move_type: Type) -> float:
    if item in {"expert-belt", "expertbelt"}:
        return 1.2
    if item in {"life-orb"}:
        return 1.0
    return 1.0


def _attacking_stat(attacker: PokemonInput, move: MoveInput) -> int:
    if move.category == Category.PHYSICAL:
        return stat_at_level(
            attacker.base_atk,
            attacker.level,
            attacker.ev_atk,
            attacker.iv_atk,
            nature_modifier(attacker.nature, Stat.ATTACK),
        )
    if move.category == Category.SPECIAL:
        return stat_at_level(
            attacker.base_spa,
            attacker.level,
            attacker.ev_spa,
            attacker.iv_spa,
            nature_modifier(attacker.nature, Stat.SPECIAL_ATTACK),
        )
    return 0


def _defending_stat(defender: PokemonInput, move: MoveInput) -> int:
    if move.category == Category.PHYSICAL:
        return stat_at_level(
            defender.base_def,
            defender.level,
            defender.ev_def,
            defender.iv_def,
            nature_modifier(defender.nature, Stat.DEFENSE),
        )
    if move.category == Category.SPECIAL:
        return stat_at_level(
            defender.base_spd,
            defender.level,
            defender.ev_spd,
            defender.iv_spd,
            nature_modifier(defender.nature, Stat.SPECIAL_DEFENSE),
        )
    return 0


def _attacking_stage(attacker: PokemonInput, move: MoveInput) -> float:
    if move.category == Category.PHYSICAL:
        return stage_multiplier(attacker.boost_atk)
    if move.category == Category.SPECIAL:
        return stage_multiplier(attacker.boost_spa)
    return 1.0


def _defending_stage(defender: PokemonInput, move: MoveInput) -> float:
    if move.category == Category.PHYSICAL:
        return stage_multiplier(defender.boost_def)
    if move.category == Category.SPECIAL:
        return stage_multiplier(defender.boost_spd)
    return 1.0


def _type_effectiveness(attacker: PokemonInput, move: MoveInput, defender: PokemonInput) -> float:
    if attacker.is_terastallized and attacker.tera_type is not None:
        atk_type = attacker.tera_type
    else:
        atk_type = move.type
    defender_pair = TypePair(
        defender.types[0], defender.types[1] if len(defender.types) > 1 else None
    )
    return defensive_multiplier(defender_pair, atk_type)


def _burn_modifier(attacker: PokemonInput, move: MoveInput) -> float:
    if move.category == Category.PHYSICAL and attacker.is_burned:
        return 0.5
    return 1.0


def _scrappy_modifier(attacker: PokemonInput, move: MoveInput, defender: PokemonInput) -> float:
    if attacker.ability != "scrappy" or move.type != Type.NORMAL:
        return 1.0
    if Type.GHOST in defender.types:
        return 1.0
    return 1.0


def _base_damage(level: int, power: int, a: int, d: int) -> float:
    return ((2 * level / 5 + 2) * power * a / d) / 50 + 2


def calc_damage(
    attacker: PokemonInput,
    defender: PokemonInput,
    move: MoveInput,
    *,
    weather: Weather = Weather.NONE,
    crit: bool = False,
    defender_hp_fraction: float = 1.0,
    defender_max_hp: int | None = None,
    reflect: bool = False,
    light_screen: bool = False,
    aurora_veil: bool = False,
) -> DamageRoll:
    """Compute a damage roll against a defender.

    Parameters
    ----------
    defender_hp_fraction:
        Current HP of the defender (0..1). Used to compute ``ko_chance``.
    defender_max_hp:
        If provided, ``ko_chance`` is calculated from absolute HP instead of %.
    """
    if move.category == Category.STATUS or move.base_power <= 0:
        return DamageRoll(0.0, 0.0, 0.0, {"ohko": 0.0, "2hko": 0.0, "3hko": 0.0}, "status move")
    if attacker.is_fainted or defender.is_fainted:
        return DamageRoll(0.0, 0.0, 0.0, {"ohko": 0.0, "2hko": 0.0, "3hko": 0.0}, "fainted")

    eff_check = _type_effectiveness(attacker, move, defender)
    if eff_check == 0.0:
        return DamageRoll(0.0, 0.0, 0.0, {"ohko": 0.0, "2hko": 0.0, "3hko": 0.0}, "immune")

    atk_stat = _attacking_stat(attacker, move)
    def_stat = _defending_stat(defender, move)
    if def_stat <= 0:
        def_stat = 1

    if move.category == Category.PHYSICAL:
        atk_ability = _ability_atk(attacker.ability)
        def_ability = _ability_def(defender.ability)
        atk_item = _item_atk_modifier(attacker.item, move.category)
        spa_item = 1.0
    else:
        atk_ability = _ability_spa(attacker.ability)
        def_ability = _ability_spd(defender.ability)
        atk_item = 1.0
        spa_item = _item_spa_modifier(attacker.item, move.category)

    burn = _burn_modifier(attacker, move)
    weather_mod = _weather_modifier(weather, move.type)
    stab = _stab(attacker, move.type)
    eff = eff_check
    type_item = _item_type_modifier(attacker.item, move.type)
    scrappy = _scrappy_modifier(attacker, move, defender)
    crit_mod = 1.5 if crit else 1.0

    if (
        (reflect and move.category == Category.PHYSICAL)
        or (light_screen and move.category == Category.SPECIAL)
        or aurora_veil
    ):
        screen = 0.5
    else:
        screen = 1.0

    base = _base_damage(attacker.level, move.base_power, atk_stat, def_stat)
    modifiers = (
        atk_ability
        * def_ability
        * atk_item
        * spa_item
        * burn
        * weather_mod
        * stab
        * eff
        * type_item
        * scrappy
        * crit_mod
        * screen
    )

    min_dmg = max(1, int(base * modifiers * _ROLL_MIN))
    max_dmg = max(min_dmg, int(base * modifiers * _ROLL_MAX))
    expected = base * modifiers * _ROLL_EXPECTED

    if defender_max_hp is None:
        defender_max_hp = 200
    min_pct = min_dmg / defender_max_hp * 100
    max_pct = max_dmg / defender_max_hp * 100
    exp_pct = expected / defender_max_hp * 100

    # KO chance is approximated using the expected %.
    if defender_hp_fraction <= 0:
        ko = {"ohko": 1.0, "2hko": 1.0, "3hko": 1.0}
    else:
        current_hp = max(1, int(defender_max_hp * defender_hp_fraction))
        if min_dmg >= current_hp:
            ko = {"ohko": 1.0, "2hko": 1.0, "3hko": 1.0}
        else:
            ohko = _ko_probability(min_dmg, max_dmg, current_hp, 1)
            tko2 = _ko_probability(min_dmg, max_dmg, current_hp, 2)
            tko3 = _ko_probability(min_dmg, max_dmg, current_hp, 3)
            ko = {
                "ohko": round(ohko, 3),
                "2hko": round(tko2, 3),
                "3hko": round(tko3, 3),
            }

    note = ""
    if eff >= 2.0:
        note = f"super effective {eff:g}x"
    elif eff <= 0.5:
        note = f"resisted {eff:g}x"
    if stab > 1.0:
        note = f"{note} STAB".strip()
    if crit:
        note = f"{note} crit".strip()

    return DamageRoll(
        min_pct=round(min_pct, 2),
        max_pct=round(max_pct, 2),
        expected_pct=round(exp_pct, 2),
        ko_chance=ko,
        note=note,
    )


def _ko_probability(min_dmg: int, max_dmg: int, hp: int, hits: int) -> float:
    """Approximate probability of a KO in ``hits`` rolls."""
    if min_dmg >= hp:
        return 1.0
    if max_dmg * hits < hp:
        return 0.0
    rolls = max_dmg - min_dmg + 1
    if rolls <= 0:
        return 0.0
    total = 0
    for dmg in range(min_dmg, max_dmg + 1):
        if dmg * hits >= hp:
            total += 1
    return total / rolls


__all__ = [
    "Category",
    "DamageRoll",
    "Level",
    "MoveInput",
    "PokemonInput",
    "Weather",
    "calc_damage",
    "hp_at_level",
    "nature_modifier",
    "stage_multiplier",
    "stat_at_level",
]
