"""Unit tests for pokecore.elo (Glicko-2)."""

from __future__ import annotations

import pytest

from pokecore.elo import (
    GlickoRating,
    MatchResult,
    expected_pair,
    expected_score,
    rate,
    rate_pair,
)


class TestGlickoRating:
    def test_defaults(self) -> None:
        r = GlickoRating()
        assert r.rating == 1500.0
        assert r.rd == 350.0
        assert r.vol == 0.06

    def test_invalid_rd(self) -> None:
        with pytest.raises(ValueError, match="Rating deviation"):
            GlickoRating(rd=0.0)

    def test_invalid_vol(self) -> None:
        with pytest.raises(ValueError, match="Volatility"):
            GlickoRating(vol=0.0)

    def test_round_trip_glicko2(self) -> None:
        for r in (GlickoRating(), GlickoRating(rating=1700, rd=80, vol=0.05)):
            mu, phi = r.to_glicko2()
            r2 = GlickoRating.from_glicko2(mu, phi, r.vol)
            assert r2.rating == pytest.approx(r.rating, abs=1e-9)
            assert r2.rd == pytest.approx(r.rd, abs=1e-9)


class TestRate:
    def test_no_matches_increases_rd(self) -> None:
        r = GlickoRating(rating=1500, rd=100, vol=0.06)
        new = rate(r, [])
        assert new.rd > r.rd
        assert new.rating == r.rating

    def test_win_increases_rating(self) -> None:
        player = GlickoRating(rating=1500, rd=100)
        opponent = GlickoRating(rating=1700, rd=100)
        new = rate(player, [MatchResult(opponent=opponent, score=1.0)])
        assert new.rating > player.rating

    def test_loss_decreases_rating(self) -> None:
        player = GlickoRating(rating=1500, rd=100)
        opponent = GlickoRating(rating=1700, rd=100)
        new = rate(player, [MatchResult(opponent=opponent, score=0.0)])
        assert new.rating < player.rating

    def test_draw_moves_toward_opponent(self) -> None:
        player = GlickoRating(rating=1500, rd=100)
        opponent = GlickoRating(rating=1700, rd=100)
        new = rate(player, [MatchResult(opponent=opponent, score=0.5)])
        assert player.rating < new.rating < opponent.rating

    def test_rd_decreases_with_more_matches(self) -> None:
        player = GlickoRating(rating=1500, rd=200)
        opponents = [GlickoRating(rating=1500, rd=100) for _ in range(5)]
        new = rate(player, [MatchResult(opponent=o, score=0.5) for o in opponents])
        assert new.rd < player.rd

    def test_invalid_score(self) -> None:
        with pytest.raises(ValueError, match="Score must be in"):
            MatchResult(GlickoRating(), 1.5)


class TestRatePair:
    def test_conservation(self) -> None:
        a = GlickoRating(rating=1500, rd=100)
        b = GlickoRating(rating=1600, rd=80)
        new_a, new_b = rate_pair(a, b, 1.0)
        assert new_a.rating > a.rating
        assert new_b.rating < b.rating

    def test_invalid_score(self) -> None:
        a, b = GlickoRating(), GlickoRating()
        with pytest.raises(ValueError, match="score_a"):
            rate_pair(a, b, -0.1)


class TestExpectedScore:
    def test_equal_players(self) -> None:
        a = GlickoRating()
        b = GlickoRating()
        e_a, e_b = expected_pair(a, b)
        assert e_a == pytest.approx(0.5, abs=1e-9)
        assert e_b == pytest.approx(0.5, abs=1e-9)

    def test_higher_rated_is_favored(self) -> None:
        a = GlickoRating(rating=1700, rd=50)
        b = GlickoRating(rating=1500, rd=50)
        e_a, e_b = expected_pair(a, b)
        assert e_a > 0.5
        assert e_b < 0.5
        assert e_a + e_b == pytest.approx(1.0, abs=1e-9)

    def test_higher_uncertainty_pulls_toward_half(self) -> None:
        certain = GlickoRating(rating=1500, rd=30)
        uncertain = GlickoRating(rating=1700, rd=350)
        e_certain_vs_uncertain = expected_score(certain, uncertain)
        e_certain_vs_certain = expected_score(certain, GlickoRating(rating=1700, rd=30))
        assert e_certain_vs_uncertain > e_certain_vs_certain
        assert e_certain_vs_uncertain < 0.5
        assert abs(e_certain_vs_uncertain - 0.5) < abs(e_certain_vs_certain - 0.5)
