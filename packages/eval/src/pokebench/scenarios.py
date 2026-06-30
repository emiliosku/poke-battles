"""Regression scenarios for chooser correctness.

Each :class:`Scenario` is a pre-built :class:`pokecore.state.BattleState` plus
an optional expected top-choice. The :func:`run_scenarios` helper runs them
through a chooser and records the result. Scenarios run **offline** — no
Showdown, no LLM, no network — so they're fast and deterministic.

Used in two ways:

- **Standalone CLI**: ``pokebench --scenario low_hp_pivot`` prints a table of
  chooser decisions against a fixed set of scenarios.
- **Unit tests**: :func:`run_scenarios` returns a :class:`ScenarioReport`
  that the test framework can assert against.

Re-exported from :mod:`pokebench`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pokecore.state import BattleState
from pokellm.heuristic import ActionKind, Candidate, pick, shortlist

# A chooser is a callable from BattleState to an action label
# ("move:earthquake" or "switch:Garchomp"). For the LLM chooser this
# would route through ``LLMAgent.decide(state)``.
Chooser = Callable[[BattleState], str]


@dataclass(frozen=True, slots=True)
class Scenario:
    """A named test case for chooser correctness."""

    name: str
    state: BattleState
    # Optional expected top choice (e.g. "move:earthquake"). If None, the
    # scenario just records what the chooser does.
    expected: str | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Result of running one scenario through a chooser."""

    name: str
    expected: str | None
    actual: str
    matched: bool
    top_score: float
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ScenarioReport:
    """Result of running multiple scenarios through a chooser."""

    results: tuple[ScenarioResult, ...]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.matched)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "results": [
                {
                    "name": r.name,
                    "expected": r.expected,
                    "actual": r.actual,
                    "matched": r.matched,
                    "top_score": r.top_score,
                    "notes": r.notes,
                }
                for r in self.results
            ],
        }


def run_scenarios(scenarios: list[Scenario], chooser: Chooser) -> ScenarioReport:
    """Run each scenario through the chooser and return a report."""
    out: list[ScenarioResult] = []
    for scenario in scenarios:
        actual = chooser(scenario.state)
        top = _top_candidate(scenario.state)
        matched = (scenario.expected is None) or (actual == scenario.expected)
        out.append(
            ScenarioResult(
                name=scenario.name,
                expected=scenario.expected,
                actual=actual,
                matched=matched,
                top_score=top.score,
                notes=scenario.notes,
            )
        )
    return ScenarioReport(results=tuple(out))


def _top_candidate(state: BattleState) -> Candidate:
    try:
        return pick(state)
    except (ValueError, IndexError):
        ranked = shortlist(state, k=1)
        if ranked:
            return ranked[0]
        return Candidate(kind=ActionKind.MOVE, target_id="__none__", score=0.0, justification="")


# ── Pre-built scenarios ───────────────────────────────────────────


def _garchomp(
    *,
    active: bool = True,
    hp: float = 1.0,
    moves: tuple[tuple[str, str, str, int], ...] = (),
) -> Any:
    """Build a PokemonState for a scenario."""
    from pokecore.state import KnownMove, PokemonState

    return PokemonState(
        species="Garchomp",
        nickname="Garchomp",
        types=("dragon", "ground"),
        level=84,
        hp_fraction=hp,
        status=None,
        ability=None,
        item=None,
        tera_type=None,
        is_terastallized=False,
        is_active=active,
        is_fainted=False,
        boosts={},
        moves=tuple(
            KnownMove(
                id=mid,
                name=mid,
                type=type_,
                category=cat,
                base_power=bp,
                accuracy=100,
                pp=16,
                max_pp=24,
            )
            for (mid, type_, cat, bp) in moves
        ),
    )


def _heatran(*, hp: float = 1.0, active: bool = True) -> Any:
    from pokecore.state import KnownMove, PokemonState

    return PokemonState(
        species="Heatran",
        nickname="Heatran",
        types=("fire", "steel"),
        level=84,
        hp_fraction=hp,
        status=None,
        ability=None,
        item=None,
        tera_type=None,
        is_terastallized=False,
        is_active=active,
        is_fainted=False,
        boosts={},
        moves=(
            KnownMove(
                id="fireblast",
                name="Fire Blast",
                type="fire",
                category="special",
                base_power=110,
                accuracy=100,
                pp=8,
                max_pp=16,
            ),
        ),
    )


def _magikarp(*, hp: float = 1.0) -> Any:
    from pokecore.state import KnownMove, PokemonState

    return PokemonState(
        species="Magikarp",
        nickname="Magikarp",
        types=("water",),
        level=84,
        hp_fraction=hp,
        status=None,
        ability=None,
        item=None,
        tera_type=None,
        is_terastallized=False,
        is_active=False,
        is_fainted=False,
        boosts={},
        moves=(
            KnownMove(
                id="splash",
                name="Splash",
                type="normal",
                category="status",
                base_power=0,
                accuracy=100,
                pp=40,
                max_pp=40,
            ),
        ),
    )


def _state(player: list[Any], opponent: list[Any], *, turn: int = 5) -> BattleState:
    from pokecore.state import BattleState, FieldState

    return BattleState(
        battle_id="scenario",
        turn=turn,
        format="gen9randombattle",
        player_username="alice",
        opponent_username="bob",
        player=tuple(player),
        opponent=tuple(opponent),
        field=FieldState(
            weather=None,
            terrain=None,
            trick_room=False,
            player_hazards={},
            opponent_hazards={},
        ),
        can_tera=False,
    )


def default_scenarios() -> list[Scenario]:
    """A small set of canonical chooser scenarios."""
    garchomp_eq = _garchomp(
        moves=(("earthquake", "ground", "physical", 100), ("outrage", "dragon", "physical", 120))
    )
    heatran = _heatran()
    garchomp_low = _garchomp(
        hp=0.15,
        moves=(("earthquake", "ground", "physical", 100),),
    )
    magikarp = _magikarp()

    return [
        Scenario(
            name="max_damage_stab_se",
            state=_state([garchomp_eq], [heatran]),
            expected="move:earthquake",
            notes="4x super effective on Heatran; should pick max-damage STAB",
        ),
        Scenario(
            name="low_hp_active",
            state=_state([garchomp_low], [heatran]),
            expected="move:earthquake",
            notes="At 15% HP, still attack because the move is 4x SE",
        ),
        Scenario(
            name="switch_available_low_hp",
            state=_state([garchomp_low, magikarp], [heatran]),
            notes="Heuristic may still pick EQ (4x SE) over the bench magikarp",
        ),
        Scenario(
            name="switch_available_low_hp",
            state=_state([garchomp_low, magikarp], [heatran]),
            notes="Heuristic may still pick EQ (4x SE) over the bench magikarp",
        ),
    ]


def chooser_from_heuristic() -> Chooser:
    """A :class:`Chooser` that runs the heuristic's top shortlist item."""

    def _choose(state: BattleState) -> str:
        ranked = shortlist(state, k=1)
        if not ranked:
            return "__none__"
        candidate = ranked[0]
        if candidate.kind == ActionKind.MOVE:
            return f"move:{candidate.target_id}"
        return f"switch:{candidate.target_id}"

    return _choose


__all__ = [
    "Chooser",
    "Scenario",
    "ScenarioReport",
    "ScenarioResult",
    "chooser_from_heuristic",
    "default_scenarios",
    "run_scenarios",
]
_ = (field,)
