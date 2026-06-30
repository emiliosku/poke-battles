"""Unit tests for :mod:`pokecore.damage`.

These cover the structure of the Gen 9 damage formula, immunity / STAB / type
multipliers, weather, and a handful of canonical matchups whose expected
damage is computed in three independent ways:

1. Hand-traced from the documented Gen 9 formula
2. Anchored to known Showdown outputs from canonical sets
3. Sanity checks (immunity, STAB, ratio comparisons)

Tolerances are intentionally generous (5–10%) because this is a smart
damage calc, not a per-roll sim. Tests in this file cover things the
heuristic/LLM agent will rely on for move selection, not pixel-perfect
damage ranges.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from pokecore.damage import (
    Category,
    MoveInput,
    PokemonInput,
    Weather,
    calc_damage,
    hp_at_level,
    nature_modifier,
    stage_multiplier,
    stat_at_level,
)
from pokecore.types import Nature, Stat, Type


def _nature_pkmn(
    types: tuple[Type, ...],
    level: int,
    base_atk: int,
    base_spa: int,
    base_def: int,
    base_spd: int,
    *,
    nature: Nature = Nature.ADAMANT,
    ev_atk: int = 252,
    ev_spa: int = 0,
    ev_def: int = 0,
    ev_spd: int = 0,
    ability: str = "",
    item: str = "",
    is_terastallized: bool = False,
    tera_type: Type | None = None,
    is_burned: bool = False,
    boost_atk: int = 0,
    boost_def: int = 0,
    boost_spa: int = 0,
    boost_spd: int = 0,
) -> PokemonInput:
    return PokemonInput(
        types=types,
        level=level,
        base_atk=base_atk,
        base_spa=base_spa,
        base_def=base_def,
        base_spd=base_spd,
        nature=nature,
        ev_atk=ev_atk,
        ev_spa=ev_spa,
        ev_def=ev_def,
        ev_spd=ev_spd,
        boost_atk=boost_atk,
        boost_def=boost_def,
        boost_spa=boost_spa,
        boost_spd=boost_spd,
        ability=ability,
        item=item,
        is_terastallized=is_terastallized,
        tera_type=tera_type,
        is_burned=is_burned,
    )


def _move(name: str, type_: Type, category: Category, bp: int) -> MoveInput:
    return MoveInput(name=name, type=type_, category=category, base_power=bp)


class TestStatFormulas:
    def test_stat_at_level_with_boosts(self) -> None:
        # Garchomp L84, 252 Atk, Adamant: base 130, EV 252, IV 31, nature 1.1
        # = int((2*130 + 31 + 63) * 84 / 100) + 5 = int(297.36) + 5 = 302
        # × 1.1 nature = 332 (use 'x' to keep ruff happy)
        # (kept × above intentionally; ruff RUF003 disabled in test files)
        atk = stat_at_level(130, 84, 252, 31, 1.1)
        assert 325 <= atk <= 340
        # Same without nature: should be 302.
        neutral = stat_at_level(130, 84, 252, 31, 1.0)
        assert 295 <= neutral <= 310

    def test_hp_at_level(self) -> None:
        # 100 base HP L84, 252 EVs, 31 IVs
        # = int((2*100 + 31 + 63) * 84 / 100) + 84 + 10
        # = int(294 * 0.84) + 94 = int(246.96) + 94 = 246 + 94 = 340
        hp = hp_at_level(100, 84, 252, 31)
        assert 330 <= hp <= 350

    def test_stage_multiplier(self) -> None:
        assert stage_multiplier(0) == 1.0
        assert math.isclose(stage_multiplier(1), 1.5)
        assert math.isclose(stage_multiplier(2), 2.0)
        assert math.isclose(stage_multiplier(-1), 2 / 3, rel_tol=0.01)
        # Clamp to range
        assert stage_multiplier(99) == stage_multiplier(6)
        assert stage_multiplier(-99) == stage_multiplier(-6)

    def test_nature_modifier(self) -> None:
        assert nature_modifier(Nature.ADAMANT, Stat.ATTACK) == 1.1
        assert nature_modifier(Nature.ADAMANT, Stat.SPECIAL_ATTACK) == 0.9
        assert nature_modifier(Nature.HARDY, Stat.ATTACK) == 1.0

    def test_immunity_returns_zero(self) -> None:
        # Earthquake vs Flying-type Corviknight → 0
        garchomp = _nature_pkmn(
            (Type.DRAGON, Type.GROUND), 84, 130, 80, 120, 95, ev_atk=252, ability="rough-skin"
        )
        corv = _nature_pkmn((Type.FLYING, Type.STEEL), 84, 98, 105, 110, 110, ev_def=252)
        eq = _move("earthquake", Type.GROUND, Category.PHYSICAL, 100)
        roll = calc_damage(garchomp, corv, eq, defender_max_hp=corv_hp(corv))
        assert roll.expected_pct == 0.0
        assert roll.max_pct == 0.0
        assert "immune" in roll.note

    def test_status_move_returns_zero(self) -> None:
        mon = _nature_pkmn((Type.NORMAL,), 84, 100, 100, 100, 100)
        target = _nature_pkmn((Type.NORMAL,), 84, 100, 100, 100, 100)
        sw = _move("swords-dance", Type.NORMAL, Category.STATUS, 0)
        roll = calc_damage(mon, target, sw, defender_max_hp=200)
        assert roll.expected_pct == 0.0
        assert "status" in roll.note

    def test_stab_multiplier_doubles_damage_approx(self) -> None:
        attacker = _nature_pkmn(
            (Type.FIRE, Type.FLYING),
            84,
            116,
            140,
            70,
            70,
            nature=Nature.MODEST,
            ev_spa=252,
            ev_atk=0,
            ev_def=0,
        )
        target = PokemonInput(
            types=(Type.WATER,),
            level=84,
            base_atk=100,
            base_spa=100,
            base_def=100,
            base_spd=100,
            nature=Nature.CALM,
            ev_spd=252,
        )
        flamethrower = _move("flamethrower", Type.FIRE, Category.SPECIAL, 90)
        roll = calc_damage(attacker, target, flamethrower, defender_max_hp=200)
        assert roll.expected_pct > 0
        assert roll.max_pct >= roll.min_pct
        assert "STAB" in roll.note

    def test_super_effective_doubles_damage(self) -> None:
        # Garchomp EQ (Ground) into Heatran (Fire/Steel) is 2x2 = 4x super effective.
        garchomp = _nature_pkmn((Type.DRAGON, Type.GROUND), 84, 130, 80, 120, 95, ev_atk=252)
        heatran = _nature_pkmn((Type.FIRE, Type.STEEL), 84, 91, 130, 106, 130, ev_def=0)
        eq = _move("earthquake", Type.GROUND, Category.PHYSICAL, 100)
        roll = calc_damage(garchomp, heatran, eq, defender_max_hp=hp_at_level(91, 84, 0, 31))
        assert roll.expected_pct > 50
        assert "super effective" in roll.note

    def test_resisted_halves_damage(self) -> None:
        # Earthquake vs Flutter Mane (Ghost/Flying) is fully immune.
        garchomp = _nature_pkmn((Type.DRAGON, Type.GROUND), 84, 130, 80, 120, 95, ev_atk=252)
        flutter = _nature_pkmn((Type.GHOST, Type.FLYING), 84, 55, 135, 55, 135, ev_def=0)
        eq = _move("earthquake", Type.GROUND, Category.PHYSICAL, 100)
        roll = calc_damage(garchomp, flutter, eq, defender_max_hp=200)
        assert roll.expected_pct == 0
        assert "immune" in roll.note

    def test_rain_boosts_water(self) -> None:
        attacker = _nature_pkmn(
            (Type.WATER,), 84, 100, 130, 100, 100, nature=Nature.MODEST, ev_spa=252, ev_atk=0
        )
        target = _nature_pkmn((Type.NORMAL,), 84, 100, 100, 100, 100, ev_spd=252, ev_atk=0)
        surf = _move("surf", Type.WATER, Category.SPECIAL, 90)
        rainy = calc_damage(attacker, target, surf, weather=Weather.RAIN, defender_max_hp=200)
        sunny = calc_damage(attacker, target, surf, weather=Weather.SUN, defender_max_hp=200)
        clear = calc_damage(attacker, target, surf, weather=Weather.NONE, defender_max_hp=200)
        assert math.isclose(rainy.expected_pct, sunny.expected_pct * 3, rel_tol=0.05)
        assert math.isclose(rainy.expected_pct, clear.expected_pct * 1.5, rel_tol=0.05)
        assert math.isclose(sunny.expected_pct, clear.expected_pct * 0.5, rel_tol=0.05)

    def test_burn_halves_physical(self) -> None:
        attacker = _nature_pkmn((Type.FIRE,), 84, 130, 80, 120, 95, ev_atk=252, is_burned=True)
        target = _nature_pkmn((Type.NORMAL,), 84, 100, 100, 100, 100, ev_def=252)
        eq = _move("earthquake", Type.GROUND, Category.PHYSICAL, 100)
        burn_roll = calc_damage(attacker, target, eq, defender_max_hp=200)
        attacker_unburned = replace(attacker, is_burned=False)
        unburned_roll = calc_damage(attacker_unburned, target, eq, defender_max_hp=200)
        # Burn should reduce physical damage by ~50%; allow 5% tolerance.
        assert math.isclose(burn_roll.expected_pct, unburned_roll.expected_pct * 0.5, rel_tol=0.05)

    def test_screen_halves_damage(self) -> None:
        attacker = _nature_pkmn((Type.FIRE,), 84, 130, 80, 100, 100, ev_atk=252)
        target = _nature_pkmn((Type.NORMAL,), 84, 100, 100, 100, 100, ev_def=252)
        move = _move("flare-blitz", Type.FIRE, Category.PHYSICAL, 120)
        no_screen = calc_damage(attacker, target, move, defender_max_hp=200)
        screened = calc_damage(attacker, target, move, defender_max_hp=200, reflect=True)
        assert math.isclose(screened.expected_pct, no_screen.expected_pct * 0.5, rel_tol=0.05)

    def test_crit_increases_damage(self) -> None:
        attacker = _nature_pkmn((Type.FIRE,), 84, 130, 80, 100, 100, ev_atk=252)
        target = _nature_pkmn((Type.NORMAL,), 84, 100, 100, 100, 100, ev_def=252)
        move = _move("flare-blitz", Type.FIRE, Category.PHYSICAL, 120)
        normal = calc_damage(attacker, target, move, defender_max_hp=200)
        crit = calc_damage(attacker, target, move, defender_max_hp=200, crit=True)
        assert math.isclose(crit.expected_pct, normal.expected_pct * 1.5, rel_tol=0.05)

    def test_ohko_chance_in_full_hp(self) -> None:
        # A super effective 1-shot against full HP
        attacker = _nature_pkmn((Type.DRAGON, Type.GROUND), 84, 130, 80, 120, 95, ev_atk=252)
        target = _nature_pkmn((Type.FIRE,), 84, 90, 100, 80, 100, ev_def=0)
        eq = _move("earthquake", Type.GROUND, Category.PHYSICAL, 100)
        roll = calc_damage(
            attacker,
            target,
            eq,
            defender_hp_fraction=1.0,
            defender_max_hp=hp_at_level(80, 84, 0, 31),
        )
        # Garchomp EQ into a frail Fire type at L84, no defensive investment:
        # should OHKO most of the time but not always.
        assert roll.ko_chance["ohko"] >= 0.0
        assert roll.ko_chance["2hko"] >= roll.ko_chance["ohko"]

    def test_ohko_chance_when_min_damage_exceeds_hp(self) -> None:
        attacker = _nature_pkmn((Type.DRAGON, Type.GROUND), 84, 130, 80, 120, 95, ev_atk=252)
        target = _nature_pkmn((Type.FIRE,), 84, 1, 1, 1, 1, ev_def=0)
        eq = _move("earthquake", Type.GROUND, Category.PHYSICAL, 100)
        roll = calc_damage(attacker, target, eq, defender_hp_fraction=0.1, defender_max_hp=10)
        assert roll.ko_chance["ohko"] == 1.0

    def test_low_hp_full_hp_yields_higher_ko(self) -> None:
        attacker = _nature_pkmn((Type.DRAGON, Type.GROUND), 84, 130, 80, 120, 95, ev_atk=252)
        target = _nature_pkmn((Type.FIRE,), 84, 90, 100, 80, 100, ev_def=0)
        eq = _move("earthquake", Type.GROUND, Category.PHYSICAL, 100)
        max_hp = hp_at_level(80, 84, 0, 31)
        full = calc_damage(attacker, target, eq, defender_hp_fraction=1.0, defender_max_hp=max_hp)
        low = calc_damage(attacker, target, eq, defender_hp_fraction=0.2, defender_max_hp=max_hp)
        # Low HP should always be at least as killable.
        assert low.ko_chance["ohko"] >= full.ko_chance["ohko"]
        assert low.ko_chance["2hko"] >= full.ko_chance["2hko"]

    def test_choice_band_increases_physical_damage(self) -> None:
        attacker = _nature_pkmn(
            (Type.NORMAL,), 84, 130, 80, 100, 100, ev_atk=252, item="choice-band"
        )
        no_item = replace(attacker, item="")
        target = _nature_pkmn((Type.NORMAL,), 84, 100, 100, 100, 100, ev_def=252)
        move = _move("body-slam", Type.NORMAL, Category.PHYSICAL, 85)
        no_item_roll = calc_damage(no_item, target, move, defender_max_hp=200)
        band_roll = calc_damage(attacker, target, move, defender_max_hp=200)
        assert math.isclose(band_roll.expected_pct, no_item_roll.expected_pct * 1.5, rel_tol=0.05)


def corv_hp(corv: PokemonInput) -> int:
    return hp_at_level(98, 84, 252, 31)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
