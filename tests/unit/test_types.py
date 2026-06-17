"""Unit tests for pokecore.types."""

from __future__ import annotations

import pytest

from pokecore.types import (
    NATURE_BOOSTS,
    NEUTRAL_NATURES,
    Boosts,
    Nature,
    NatureModifier,
    Stat,
    Type,
    TypePair,
    clamp,
)


class TestTypePair:
    def test_single_type(self) -> None:
        pair = TypePair(Type.FIRE)
        assert len(pair) == 1
        assert pair.primary == Type.FIRE
        assert pair.secondary is None
        assert str(pair) == "fire"

    def test_dual_type(self) -> None:
        pair = TypePair(Type.FIRE, Type.FLYING)
        assert len(pair) == 2
        assert Type.FIRE in pair
        assert Type.FLYING in pair
        assert Type.WATER not in pair
        assert str(pair) == "fire/flying"

    def test_iter(self) -> None:
        assert tuple(TypePair(Type.WATER)) == (Type.WATER,)
        assert tuple(TypePair(Type.FIRE, Type.FLYING)) == (Type.FIRE, Type.FLYING)


class TestBoosts:
    def test_default_zero(self) -> None:
        b = Boosts()
        assert b.atk == 0
        assert b.get(Stat.ATTACK) == 0
        assert b.get(Stat.HP) == 0

    def test_valid_range(self) -> None:
        b = Boosts(atk=6, def_=-6, spa=3)
        assert b.get(Stat.ATTACK) == 6
        assert b.get(Stat.DEFENSE) == -6
        assert b.get(Stat.SPECIAL_ATTACK) == 3

    @pytest.mark.parametrize("value", [-7, 7, 100, -100])
    def test_out_of_range(self, value: int) -> None:
        with pytest.raises(ValueError, match="out of range"):
            Boosts(atk=value)


class TestNatureModifier:
    def test_neutral_nature(self) -> None:
        for nature in NEUTRAL_NATURES:
            mod = NatureModifier.from_nature(nature)
            assert mod.increased is None
            assert mod.decreased is None
            assert mod.multiplier(Stat.ATTACK) == 1.0
            assert mod.multiplier(Stat.SPEED) == 1.0

    def test_boosting_nature(self) -> None:
        mod = NatureModifier.from_nature(Nature.JOLLY)
        assert mod.increased == Stat.SPEED
        assert mod.decreased == Stat.SPECIAL_ATTACK
        assert mod.multiplier(Stat.SPEED) == 1.1
        assert mod.multiplier(Stat.SPECIAL_ATTACK) == 0.9
        assert mod.multiplier(Stat.ATTACK) == 1.0

    def test_all_natures_have_boost(self) -> None:
        non_neutral = set(Nature) - NEUTRAL_NATURES
        assert non_neutral == set(NATURE_BOOSTS.keys())
        for nature in non_neutral:
            mod = NatureModifier.from_nature(nature)
            assert mod.increased is not None
            assert mod.decreased is not None
            assert mod.increased != mod.decreased


class TestClamp:
    @pytest.mark.parametrize(
        ("value", "low", "high", "expected"),
        [
            (5, 0, 10, 5),
            (-1, 0, 10, 0),
            (15, 0, 10, 10),
            (0, 0, 10, 0),
            (10, 0, 10, 10),
        ],
    )
    def test_clamp(self, value: int, low: int, high: int, expected: int) -> None:
        assert clamp(value, low, high) == expected
