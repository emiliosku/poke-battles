"""Unit tests for pokecore.type_chart."""

from __future__ import annotations

from pokecore.type_chart import (
    MULTIPLIERS,
    coverage_summary,
    defensive_multiplier,
    is_immune,
    offensive_coverage,
    resists,
    type_multiplier,
    weak_to,
)
from pokecore.types import Type, TypePair


class TestTypeMultiplier:
    def test_neutral(self) -> None:
        assert type_multiplier(Type.NORMAL, Type.NORMAL) == 1.0
        assert type_multiplier(Type.FIRE, Type.WATER) == 0.5
        assert type_multiplier(Type.WATER, Type.FIRE) == 2.0

    def test_immunity(self) -> None:
        assert type_multiplier(Type.NORMAL, Type.GHOST) == 0.0
        assert type_multiplier(Type.GHOST, Type.NORMAL) == 0.0
        assert type_multiplier(Type.ELECTRIC, Type.GROUND) == 0.0
        assert type_multiplier(Type.PSYCHIC, Type.DARK) == 0.0
        assert type_multiplier(Type.DRAGON, Type.FAIRY) == 0.0

    def test_resistances(self) -> None:
        assert type_multiplier(Type.FIRE, Type.FIRE) == 0.5
        assert type_multiplier(Type.WATER, Type.GRASS) == 0.5
        assert type_multiplier(Type.ELECTRIC, Type.ELECTRIC) == 0.5

    def test_typeless_is_neutral(self) -> None:
        for t in Type:
            if t == Type.TYPELESS:
                continue
            assert type_multiplier(Type.TYPELESS, t) == 1.0
            assert type_multiplier(t, Type.TYPELESS) == 1.0

    def test_matrix_is_symmetric_shape(self) -> None:
        assert len(MULTIPLIERS) == len(Type)
        for t in Type:
            assert t in MULTIPLIERS
            assert len(MULTIPLIERS[t]) == len(Type)

    def test_well_known_matchups(self) -> None:
        assert type_multiplier(Type.GROUND, Type.ELECTRIC) == 2.0
        assert type_multiplier(Type.FIGHTING, Type.DARK) == 2.0
        assert type_multiplier(Type.FAIRY, Type.DRAGON) == 2.0
        assert type_multiplier(Type.STEEL, Type.FAIRY) == 2.0
        assert type_multiplier(Type.ICE, Type.DRAGON) == 2.0
        assert type_multiplier(Type.GHOST, Type.GHOST) == 2.0


class TestDefensiveMultiplier:
    def test_mono_type(self) -> None:
        assert defensive_multiplier(TypePair(Type.GHOST), Type.NORMAL) == 0.0
        assert defensive_multiplier(TypePair(Type.FIRE), Type.WATER) == 2.0

    def test_dual_type_multiplies(self) -> None:
        pair = TypePair(Type.FIRE, Type.FLYING)
        assert defensive_multiplier(pair, Type.WATER) == 2.0
        assert defensive_multiplier(pair, Type.GROUND) == 0.0
        assert defensive_multiplier(pair, Type.ELECTRIC) == 2.0
        assert defensive_multiplier(pair, Type.ROCK) == 4.0
        assert defensive_multiplier(pair, Type.BUG) == 0.25

    def test_typeless_attack_is_neutral(self) -> None:
        assert defensive_multiplier(TypePair(Type.GHOST), Type.TYPELESS) == 1.0


class TestOffensiveCoverage:
    def test_empty_returns_neutral(self) -> None:
        assert offensive_coverage([], TypePair(Type.FIRE)) == 1.0

    def test_returns_max_multiplier(self) -> None:
        best = offensive_coverage([Type.WATER, Type.GROUND], TypePair(Type.FIRE))
        assert best == 2.0

    def test_immune_blocks_all(self) -> None:
        assert offensive_coverage([Type.NORMAL, Type.FIGHTING], TypePair(Type.GHOST)) == 0.0


class TestPredicates:
    def test_is_immune(self) -> None:
        assert is_immune(TypePair(Type.GHOST), Type.NORMAL)
        assert is_immune(TypePair(Type.GROUND), Type.ELECTRIC)
        assert not is_immune(TypePair(Type.FIRE), Type.WATER)

    def test_resists(self) -> None:
        assert resists(TypePair(Type.FIRE), Type.FIRE)
        assert not resists(TypePair(Type.FIRE), Type.WATER)
        assert not resists(TypePair(Type.GHOST), Type.NORMAL)

    def test_weak_to(self) -> None:
        assert weak_to(TypePair(Type.FIRE), Type.WATER)
        assert not weak_to(TypePair(Type.FIRE), Type.FIRE)
        assert not weak_to(TypePair(Type.GHOST), Type.NORMAL)


class TestCoverageSummary:
    def test_returns_best_and_worst(self) -> None:
        summary = coverage_summary([Type.WATER, Type.NORMAL], TypePair(Type.FIRE))
        assert summary["best"] == Type.WATER
        assert summary["worst"] == Type.NORMAL
        assert summary["multiplier"] == 2.0
        assert summary["is_neutral"] is False

    def test_immune_short_circuits(self) -> None:
        summary = coverage_summary([Type.NORMAL, Type.FIGHTING], TypePair(Type.GHOST))
        assert summary["multiplier"] == 0.0
        assert summary["is_neutral"] is False

    def test_neutral(self) -> None:
        summary = coverage_summary([Type.NORMAL], TypePair(Type.NORMAL))
        assert summary["is_neutral"] is True
