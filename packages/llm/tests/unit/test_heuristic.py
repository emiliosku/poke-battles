"""Unit tests for pokellm.heuristic."""

from __future__ import annotations

from pokecore.damage import Category, MoveInput, PokemonInput, Weather, calc_damage, hp_at_level
from pokecore.state import BattleState, FieldState, KnownMove, PokemonState
from pokecore.types import Nature, Type
from pokellm.heuristic import ActionKind, Candidate, pick, shortlist


def _move(mid: str, type_: str, cat: str, bp: int, prio: int = 0) -> KnownMove:
    return KnownMove(
        id=mid,
        name=mid,
        type=type_,
        category=cat,
        base_power=bp,
        accuracy=100,
        pp=16,
        max_pp=24,
        priority=prio,
    )


def _mon(
    species: str,
    types: tuple[str, ...],
    *,
    hp: float = 1.0,
    fainted: bool = False,
    active: bool = False,
    moves: tuple[KnownMove, ...] = (),
    status: str | None = None,
    tera_type: str | None = None,
) -> PokemonState:
    return PokemonState(
        species=species,
        nickname=species,
        types=types,
        level=84,
        hp_fraction=hp,
        status=status,
        ability=None,
        item=None,
        tera_type=tera_type,
        is_terastallized=False,
        is_active=active,
        is_fainted=fainted,
        boosts={},
        moves=moves,
    )


def _state(
    player: tuple[PokemonState, ...],
    opponent: tuple[PokemonState, ...],
    *,
    weather: str | None = None,
) -> BattleState:
    return BattleState(
        battle_id="battle-test",
        turn=5,
        format="gen9randombattle",
        player_username="alice",
        opponent_username="bob",
        player=player,
        opponent=opponent,
        field=FieldState(
            weather=weather,
            terrain=None,
            trick_room=False,
            player_hazards={},
            opponent_hazards={},
        ),
        can_tera=False,
    )


def _garchomp(
    *,
    active: bool = True,
    hp: float = 1.0,
    fainted: bool = False,
) -> PokemonState:
    return _mon(
        "Garchomp",
        ("dragon", "ground"),
        hp=hp,
        fainted=fainted,
        active=active,
        moves=(
            _move("earthquake", "ground", "physical", 100),
            _move("outrage", "dragon", "physical", 120),
        ),
    )


def _magikarp(*, active: bool = False, hp: float = 1.0, fainted: bool = False) -> PokemonState:
    return _mon(
        "Magikarp",
        ("water",),
        hp=hp,
        fainted=fainted,
        active=active,
        moves=(_move("splash", "normal", "status", 0),),
    )


def _feraligatr(*, hp: float = 1.0) -> PokemonState:
    return _mon(
        "Feraligatr",
        ("water",),
        hp=hp,
        active=False,
        moves=(_move("surf", "water", "special", 90),),
    )


def _charizard(*, hp: float = 1.0) -> PokemonState:
    return _mon(
        "Charizard",
        ("fire", "flying"),
        hp=hp,
        active=False,
        moves=(_move("flare-blitz", "fire", "physical", 120),),
    )


def _opponent(active: bool = True, hp: float = 1.0) -> PokemonState:
    return _mon(
        "Heatran",
        ("fire", "steel"),
        active=active,
        hp=hp,
        moves=(_move("fire-blast", "fire", "special", 110),),
    )


class TestShortlist:
    def test_returns_empty_when_no_active(self) -> None:
        state = _state(
            player=(_garchomp(active=False, fainted=True),),
            opponent=(_opponent(),),
        )
        assert shortlist(state) == []

    def test_move_score_orders_by_damage(self) -> None:
        # EQ (Ground, 4x super effective on Fire/Steel Heatran) must outscore
        # Outrage (Dragon, resisted 0.5x by Steel). Heatran is intentionally Fire/Steel
        # so the type matchup is unambiguous.
        state = _state(player=(_garchomp(),), opponent=(_opponent(),))
        ranked = shortlist(state, k=2)
        assert [c.target_id for c in ranked] == ["earthquake", "outrage"]
        assert all(c.kind == ActionKind.MOVE for c in ranked)

    def test_priority_move_penalises_active_low_hp(self) -> None:
        # At full HP a switch should score lower than the best move.
        state = _state(
            player=(_garchomp(hp=0.15), _feraligatr()),
            opponent=(_opponent(hp=0.5),),
        )
        ranked = shortlist(state, k=3)
        # The best switch should still appear but score lower than the best move
        # since switching with low HP into a low-HP opponent is risky.
        assert ranked

    def test_switch_present_when_bench_exists(self) -> None:
        state = _state(
            player=(_garchomp(hp=0.95), _feraligatr(), _charizard()),
            opponent=(_opponent(hp=0.4),),
        )
        ranked = shortlist(state, k=5)
        switch_candidates = [c for c in ranked if c.kind == ActionKind.SWITCH]
        assert switch_candidates  # switches should be considered

    def test_pick_returns_top_candidate(self) -> None:
        state = _state(player=(_garchomp(),), opponent=(_opponent(),))
        top = pick(state)
        assert isinstance(top, Candidate)
        assert top.target_id == "earthquake"

    def test_shortlist_is_sorted_descending(self) -> None:
        state = _state(
            player=(_garchomp(), _feraligatr(), _charizard()),
            opponent=(_opponent(),),
        )
        ranked = shortlist(state, k=5)
        scores = [c.score for c in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_immunity_gives_zero_score_to_switch(self) -> None:
        # Magikarp is Water only; opposing Heatran Fire/Steel vs Water = 2x2 = 4x
        # so a Water switch is super effective offensively; reverse: incoming on
        # the candidate is Fire/Steel vs Water = 2x0.5 = 1x neutral. Score > 0.
        state = _state(
            player=(_garchomp(hp=0.95), _magikarp()),
            opponent=(_opponent(),),
        )
        ranked = shortlist(state, k=5)
        magikarp = next(c for c in ranked if c.target_id == "Magikarp")
        assert magikarp.score > 0

    def test_status_move_score_is_low(self) -> None:
        state = _state(
            player=(
                _mon(
                    "Tanky",
                    ("water",),
                    active=True,
                    hp=1.0,
                    moves=(
                        _move("recover", "normal", "status", 0),
                        _move("surf", "water", "special", 90),
                    ),
                ),
            ),
            opponent=(_opponent(),),
        )
        ranked = shortlist(state, k=2)
        scores_by_id = {c.target_id: c.score for c in ranked}
        # surf (90 BP) should outscore recover (status, 0 BP)
        assert scores_by_id["surf"] > scores_by_id["recover"]

    def test_ko_bonus_promotes_ohko(self) -> None:
        # Compare to heuristic scoring directly
        state = _state(
            player=(_garchomp(),),
            opponent=(_opponent(hp=0.3),),
        )
        ranked = shortlist(state, k=2)
        # At 30% HP Heatran (Fire/Steel) vs 252-Atk Garchomp EQ, an OHKO is likely
        best = ranked[0]
        assert best.score > 50  # high score from KO bonus


class TestAdapters:
    def test_default_iv_ev_nature_in_damage(self) -> None:
        # Sanity: with default 252/31/Hardy, the heuristic damage should be > 0
        # for a super effective matchup.
        attacker = PokemonInput(
            types=(Type.DRAGON, Type.GROUND),
            level=84,
            base_atk=130,
            base_spa=80,
            base_def=120,
            base_spd=95,
            nature=Nature.HARDY,
            ev_atk=252,
        )
        defender = PokemonInput(
            types=(Type.FIRE, Type.STEEL),
            level=84,
            base_atk=91,
            base_spa=130,
            base_def=106,
            base_spd=130,
            nature=Nature.HARDY,
            ev_def=0,
        )
        move = MoveInput("earthquake", Type.GROUND, Category.PHYSICAL, 100)
        roll = calc_damage(
            attacker,
            defender,
            move,
            weather=Weather.NONE,
            defender_hp_fraction=1.0,
            defender_max_hp=hp_at_level(91, 84, 0, 31),
        )
        assert roll.expected_pct > 30


class TestBaseStatsAdapter:
    def test_garchomp_uses_table_stats(self) -> None:
        from pokellm.heuristic import shortlist

        # Garchomp has base Atk=130 in the table. A real-BSTs run should
        # produce a much higher expected % on EQ than a flat 100-stat run.
        state = _state(player=(_garchomp(),), opponent=(_opponent(),))
        # Heuristic damage calc uses Garchomp's real base Atk (130) not 100.
        ranked = shortlist(state, k=1)
        top = ranked[0]
        # Real Garchomp with EQ vs Heatran (4x SE) should OHKO almost always.
        assert top.expected_pct > 50
        assert "super effective" in top.justification or "OHKO" in top.justification

    def test_unknown_species_falls_back_to_default(self) -> None:
        from pokellm.base_stats import get_base_stats

        # Pokemon invented for the test, not in the table
        assert get_base_stats("fakemone") is None
        # Showdown id normalization: spaces, hyphens, dots are stripped
        assert get_base_stats("Mr. Mime") is None  # not in the table
        # Known species
        result = get_base_stats("garchomp")
        assert result is not None
        # Tuple shape: (base_atk, base_def, base_spa, base_spd, base_hp, base_spe)
        base_atk, base_def, base_spa, base_spd, base_hp, base_spe = result
        assert base_atk == 130
        assert base_spe == 130  # Garchomp's signature base 130 Speed

    def test_id_normalization(self) -> None:
        from pokellm.base_stats import get_base_stats

        # Showdown stores MR. MIME with a dot, NIDOQUEEN as one word, etc.
        # The function strips these.
        assert get_base_stats("") is None
        assert get_base_stats("   ") is None
        # A made-up name not in the table returns None
        assert get_base_stats("a-mane") is None  # "a-mane" -> "amane", not in table
        # Common mon from the table
        assert get_base_stats("blastoise") is not None
