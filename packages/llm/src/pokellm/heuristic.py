"""Deterministic heuristic agent for poke-battles.

A fast, non-LLM baseline that scores each candidate action (move or switch)
using :func:`pokecore.damage.calc_damage` and the existing type-coverage
helpers. The output is a ranked :class:`Candidate` shortlist that the
LLM agent can either confirm or override (see Phase 4 — hybrid mode).

This module deliberately has zero poke-env and zero LLM dependencies.
Inputs are :class:`pokecore.state.BattleState`; outputs are pure dataclasses.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pokecore.damage import (
    Category,
    MoveInput,
    PokemonInput,
    Weather,
    calc_damage,
    hp_at_level,
)
from pokecore.state import BattleState, PokemonState
from pokecore.type_chart import (
    defensive_multiplier,
    offensive_coverage,
)
from pokecore.types import Nature, Stat, Type, TypePair
from pokellm.base_stats import get_base_stats

# Defaults for mons whose EV/IV/nature we can't see (Showdown doesn't expose
# them to the client). 84 / 252 / 31 / Hardy is the canonical random-battle
# assumption.
_DEFAULT_LEVEL = 84
_DEFAULT_IV = 31
_DEFAULT_EV = 252
_DEFAULT_NATURE = Nature.HARDY
_DEFAULT_BASE = 100  # used when the species isn't in the base-stats table


class ActionKind(StrEnum):
    MOVE = "move"
    SWITCH = "switch"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One ranked action considered by the heuristic."""

    kind: ActionKind
    target_id: str
    score: float
    justification: str
    expected_pct: float = 0.0
    ko_chance: dict[str, float] | None = None


def shortlist(state: BattleState, k: int = 3) -> list[Candidate]:
    """Return the top-``k`` candidate actions for ``state``."""
    active = _find_active(state.player)
    opp_active = _find_active(state.opponent)
    if active is None or opp_active is None:
        return []
    candidates = _score_moves(state, active, opp_active) + _score_switches(
        state, active, opp_active
    )
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:k]


def pick(state: BattleState) -> Candidate:
    """Return the top-scoring candidate for ``state``."""
    ranked = shortlist(state, k=1)
    if not ranked:
        raise ValueError("heuristic: no candidates for state (no active mon?)")
    return ranked[0]


# ----- Internals ---------------------------------------------------------


def _find_active(side: tuple[PokemonState, ...]) -> PokemonState | None:
    for mon in side:
        if mon.is_active and not mon.is_fainted:
            return mon
    # Fall back to first non-fainted bench member
    for mon in side:
        if not mon.is_fainted:
            return mon
    return None


def _to_pokemon_input(mon: PokemonState) -> PokemonInput:
    types: tuple[Type, ...] = tuple(_to_type(t) for t in mon.types) if mon.types else (Type.NORMAL,)
    # Use the inline base-stats table when we recognize the species; otherwise
    # fall back to a flat 100/100 baseline (which is what we had before).
    # The damage calc only takes atk/def/spa/spd, so we destructure only those.
    stats = get_base_stats(mon.species)
    if stats is not None:
        base_atk, base_def, base_spa, base_spd, _base_hp, _base_spe = stats
    else:
        base_atk = base_def = base_spa = base_spd = _DEFAULT_BASE
    return PokemonInput(
        types=types,
        level=_DEFAULT_LEVEL,
        base_atk=base_atk,
        base_spa=base_spa,
        base_def=base_def,
        base_spd=base_spd,
        nature=_DEFAULT_NATURE,
        ev_atk=_DEFAULT_EV,
        ev_spa=_DEFAULT_EV,
        ev_def=_DEFAULT_EV,
        ev_spd=_DEFAULT_EV,
        iv_atk=_DEFAULT_IV,
        iv_spa=_DEFAULT_IV,
        iv_def=_DEFAULT_IV,
        iv_spd=_DEFAULT_IV,
        boost_atk=mon.boosts.get("atk", 0),
        boost_spa=mon.boosts.get("spa", 0),
        boost_def=mon.boosts.get("def", 0),
        boost_spd=mon.boosts.get("spd", 0),
        ability=mon.ability or "",
        item=mon.item or "",
        is_terastallized=mon.is_terastallized,
        tera_type=_to_type(mon.tera_type) if mon.tera_type else None,
        is_fainted=mon.is_fainted,
        is_burned=(mon.status == "brn"),
    )


def _to_type(value: str | Type) -> Type:
    if isinstance(value, Type):
        return value
    try:
        return Type(str(value).lower())
    except ValueError:
        return Type.NORMAL


def _to_move_input(mv_id: str, mv_type: str, mv_category: object, base_power: int) -> MoveInput:
    # poke-env exposes move category as either a string ("special") or a
    # MoveCategory enum. Normalize to the lowercase string.
    if mv_category is None:
        category = Category.STATUS
    else:
        cat_str = str(mv_category).split(".")[-1].split(" ")[0].lower()
        try:
            category = Category(cat_str)
        except ValueError:
            category = Category.STATUS
    return MoveInput(
        name=mv_id,
        type=_to_type(mv_type),
        category=category,
        base_power=base_power,
    )


def _max_hp(mon: PokemonState) -> int:
    stats = get_base_stats(mon.species)
    base_hp = stats[4] if stats is not None else _DEFAULT_BASE
    return max(1, hp_at_level(base_hp, _DEFAULT_LEVEL, _DEFAULT_EV, _DEFAULT_IV))


def _score_moves(
    state: BattleState,
    active: PokemonState,
    opp_active: PokemonState,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    attacker = _to_pokemon_input(active)
    defender = _to_pokemon_input(opp_active)
    weather = _to_weather(state.field.weather)
    for mv in active.moves:
        if not mv.id or mv.base_power <= 0:
            # Status move: small constant score, no damage contribution.
            candidates.append(
                Candidate(
                    kind=ActionKind.MOVE,
                    target_id=mv.id,
                    score=10.0,
                    justification=f"status move ({mv.type} {mv.category})",
                )
            )
            continue
        move = _to_move_input(mv.id, mv.type, mv.category, mv.base_power)
        roll = calc_damage(
            attacker,
            defender,
            move,
            weather=weather,
            defender_hp_fraction=opp_active.hp_fraction,
            defender_max_hp=_max_hp(opp_active),
        )
        score = roll.expected_pct
        note = roll.note or "neutral"
        # KO bonuses
        if roll.ko_chance.get("ohko", 0.0) >= 0.5:
            score += 25.0
            note = f"{note} likely OHKO"
        elif roll.ko_chance.get("2hko", 0.0) >= 0.5:
            score += 10.0
            note = f"{note} likely 2HKO"
        # Priority bonus
        if mv.priority > 0:
            score += mv.priority * 2.0
            note = f"{note} prio+{mv.priority}"
        # If active is low and a move can't KO, de-prioritize
        if active.hp_fraction < 0.25 and not roll.ko_chance.get("2hko", 0.0) >= 0.5:
            score -= 5.0
        candidates.append(
            Candidate(
                kind=ActionKind.MOVE,
                target_id=mv.id,
                score=score,
                justification=(
                    f"{mv.id}: {roll.expected_pct:.1f}% expected ({note}, "
                    f"ohko={roll.ko_chance.get('ohko', 0):.0%})"
                ),
                expected_pct=roll.expected_pct,
                ko_chance=dict(roll.ko_chance),
            )
        )
    return candidates


def _score_switches(
    state: BattleState,
    active: PokemonState,
    opp_active: PokemonState,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    if len(state.player) <= 1:
        return candidates
    opp_pair = TypePair(
        _to_type(opp_active.types[0]) if opp_active.types else Type.NORMAL,
        _to_type(opp_active.types[1]) if len(opp_active.types) > 1 else None,
    )
    for mon in state.player:
        if mon.is_active or mon.is_fainted:
            continue
        if mon.species == active.species:
            continue
        cand_types = tuple(_to_type(t) for t in mon.types) if mon.types else (Type.NORMAL,)
        off = offensive_coverage(list(cand_types), opp_pair)
        incoming = max(defensive_multiplier(opp_pair, t) for t in cand_types)
        if incoming == 0.0:
            score = 0.0
            note = "immune to opponent's moves"
        else:
            score = (off / incoming) * mon.hp_fraction * 100.0
            note = f"off={off:g}x in={incoming:g}x hp={mon.hp_fraction:.0%}"
        # Don't switch if active is healthy
        if active.hp_fraction > 0.5:
            score *= 0.4
        candidates.append(
            Candidate(
                kind=ActionKind.SWITCH,
                target_id=mon.species,
                score=score,
                justification=f"switch to {mon.species}: {note}",
            )
        )
    return candidates


def _to_weather(value: str | None) -> Weather:
    if value is None:
        return Weather.NONE
    try:
        return Weather(str(value).lower())
    except ValueError:
        return Weather.NONE


__all__ = [
    "ActionKind",
    "Candidate",
    "pick",
    "shortlist",
]
_ = (Stat,)
