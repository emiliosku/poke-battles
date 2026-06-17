"""Glicko-2 rating system.

A modern, robust rating algorithm that handles rating deviation (uncertainty) and
rating volatility (consistency). Standard for online game matchmaking.

Reference: http://www.glicko.net/glicko/glicko2.pdf

Re-exported from :mod:`pokecore`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace

SCALE: float = 173.7178
INITIAL_RATING: float = 1500.0
INITIAL_RD: float = 350.0
INITIAL_VOLATILITY: float = 0.06
TAU: float = 0.5
CONVERGENCE_TOLERANCE: float = 1e-6
MAX_ITERATIONS: int = 100


@dataclass(frozen=True, slots=True)
class GlickoRating:
    rating: float = INITIAL_RATING
    rd: float = INITIAL_RD
    vol: float = INITIAL_VOLATILITY

    def __post_init__(self) -> None:
        if self.rd <= 0:
            raise ValueError(f"Rating deviation must be > 0, got {self.rd}")
        if self.vol <= 0:
            raise ValueError(f"Volatility must be > 0, got {self.vol}")

    def to_glicko2(self) -> tuple[float, float]:
        return (self.rating - INITIAL_RATING) / SCALE, self.rd / SCALE

    @classmethod
    def from_glicko2(cls, mu: float, phi: float, vol: float) -> GlickoRating:
        return cls(rating=SCALE * mu + INITIAL_RATING, rd=SCALE * phi, vol=vol)


@dataclass(frozen=True, slots=True)
class MatchResult:
    """A single match result from one player's perspective."""

    opponent: GlickoRating
    score: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score must be in [0, 1], got {self.score}")


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _e(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _update_volatility(sigma: float, phi: float, v: float, delta: float, tau: float = TAU) -> float:
    """Illinois algorithm for the volatility update equation."""
    a = math.log(sigma * sigma)
    phi_sq = phi * phi
    delta_sq = delta * delta
    tau_sq = tau * tau

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta_sq - phi_sq - v - ex)
        den = 2.0 * (phi_sq + v + ex) ** 2
        return num / den - (x - a) / tau_sq

    a_bound = a
    if delta_sq > phi_sq + v:
        b_bound = math.log(delta_sq - phi_sq - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        b_bound = a - k * tau

    f_a = f(a_bound)
    f_b = f(b_bound)
    if f_a * f_b >= 0:
        return sigma

    iteration = 0
    while iteration < MAX_ITERATIONS and abs(b_bound - a_bound) > CONVERGENCE_TOLERANCE:
        c_bound = (a_bound + b_bound) / 2.0
        f_c = f(c_bound)
        if f_c * f_b <= 0:
            a_bound = c_bound
            f_a = f_c
        else:
            b_bound = c_bound
            f_b = f_c
        iteration += 1
    return math.exp((a_bound + b_bound) / 2.0)


def rate(rating: GlickoRating, matches: Iterable[MatchResult]) -> GlickoRating:
    """Update a single rating from a set of match results in a rating period."""
    matches = list(matches)
    if not matches:
        new_rd = math.sqrt(rating.rd * rating.rd + rating.vol * rating.vol)
        return replace(rating, rd=new_rd)

    mu, phi = rating.to_glicko2()
    v_inv = 0.0
    delta_acc = 0.0
    for match in matches:
        mu_j, phi_j = match.opponent.to_glicko2()
        g_j = _g(phi_j)
        e_j = _e(mu, mu_j, phi_j)
        v_inv += g_j * g_j * e_j * (1.0 - e_j)
        delta_acc += g_j * (match.score - e_j)

    if v_inv == 0.0:
        new_rd = math.sqrt(rating.rd * rating.rd + rating.vol * rating.vol)
        return replace(rating, rd=new_rd)

    v = 1.0 / v_inv
    delta = v * delta_acc
    new_vol = _update_volatility(rating.vol, phi, v, delta)
    phi_star = math.sqrt(phi * phi + new_vol * new_vol)
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    new_mu = mu + new_phi * new_phi * delta_acc
    return GlickoRating.from_glicko2(new_mu, new_phi, new_vol)


def rate_pair(
    player_a: GlickoRating,
    player_b: GlickoRating,
    score_a: float,
) -> tuple[GlickoRating, GlickoRating]:
    """Rate a head-to-head match. ``score_a`` is from A's perspective (1, 0.5, 0)."""
    if not 0.0 <= score_a <= 1.0:
        raise ValueError(f"score_a must be in [0, 1], got {score_a}")
    new_a = rate(player_a, [MatchResult(opponent=player_b, score=score_a)])
    new_b = rate(player_b, [MatchResult(opponent=player_a, score=1.0 - score_a)])
    return new_a, new_b


def expected_score(player: GlickoRating, opponent: GlickoRating) -> float:
    """Expected score in [0, 1] of ``player`` against ``opponent``."""
    mu, phi = player.to_glicko2()
    mu_j, phi_j = opponent.to_glicko2()
    return _e(mu, mu_j, phi_j)


def expected_pair(a: GlickoRating, b: GlickoRating) -> tuple[float, float]:
    """Expected scores for both players; sums to 1.0 (ignoring draws)."""
    e_a = expected_score(a, b)
    return e_a, 1.0 - e_a
